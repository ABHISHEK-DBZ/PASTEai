from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.models import FieldType, Product, ProductField, ReviewStatus, ProductStatus
from app.trust_model import (
    AGREEMENT,
    EXTRACTION_STRENGTH,
    SOURCE_AUTHORITY,
    ConfidenceFactors,
    RoutingDecision,
    cap_inferred_confidence,
    compute_confidence,
    determine_routing,
)
from app.vlm import VLMError, extract_text_fallback, get_vlm_client

logger = logging.getLogger("paste.pipeline")


# --- Unit normalization ---
UNIT_ALIASES = {
    "voltage": {"v", "volt", "volts", "voltage"},
    "current": {"a", "amp", "amps", "ampere", "amperes", "current"},
    "power": {"w", "watt", "watts", "kw", "kilowatt", "kilowatts"},
    "frequency": {"hz", "hertz", "khz", "mhz"},
    "temperature": {"c", "celsius", "°c", "f", "fahrenheit", "°f", "k", "kelvin"},
    "pressure": {"bar", "psi", "pa", "kpa", "mpa"},
    "dimension": {"mm", "cm", "m", "in", "inch", "inches"},
    "weight": {"kg", "g", "lb", "lbs", "ounce", "oz"},
    "ip_rating": {"ip", "ip_rating", "ingress_protection"},
}


def normalize_unit(attribute_key: str, raw_unit: str) -> tuple[str, str]:
    """Return (canonical_key, canonical_unit)."""
    key_lower = attribute_key.lower()
    unit_lower = raw_unit.lower().strip()

    # If the key is already a canonical attribute, map it to its known physical unit
    canonical_key = canonicalize_attribute(attribute_key)
    if canonical_key in ATTRIBUTE_ALIASES:
        # voltage_rating -> V, weight -> kg, power_rating -> W, etc.
        unit_for_attr = {
            "voltage_rating": "V", "current_rating": "A", "power_rating": "W",
            "frequency_rating": "Hz", "temperature_range": "°C", "weight": "kg",
            "dimensions": "mm", "ip_rating": "IP",
        }.get(canonical_key)
        if unit_for_attr:
            return canonical_key, unit_for_attr
        return canonical_key, unit_lower or ""

    # Generic substring/alias scan for non-canonical keys
    for canonical, aliases in UNIT_ALIASES.items():
        if any(alias in key_lower for alias in aliases) or unit_lower in aliases:
            return canonical, CANONICAL_UNITS[canonical]

    return canonical_key, unit_lower or ""


# --- Alias mapping ---
ATTRIBUTE_ALIASES = {
    "voltage_rating": ["voltage", "rated_voltage", "operating_voltage", "input_voltage", "supply_voltage"],
    "current_rating": ["current", "rated_current", "operating_current", "input_current", "max_current"],
    "power_rating": ["power", "rated_power", "power_consumption", "max_power"],
    "frequency_rating": ["frequency", "operating_frequency", "line_frequency"],
    "ip_rating": ["ip_rating", "ip_code", "ingress_protection", "protection_class"],
    "temperature_range": ["temperature_range", "operating_temperature", "ambient_temperature", "temp_range"],
    "dimensions": ["dimensions", "size", "length_width_height", "lwh", "measurements"],
    "weight": ["weight", "mass", "net_weight"],
    "material": ["material", "housing_material", "body_material", "enclosure_material"],
    "certifications": ["certifications", "approvals", "compliance", "standards", "marks"],
    "part_number": ["part_number", "part_no", "model_number", "model", "sku", "product_code"],
    "manufacturer": ["manufacturer", "brand", "maker", "vendor", "supplier"],
    "series": ["series", "family", "range", "product_line"],
    "description": ["description", "product_description", "short_description", "summary"],
}


def canonicalize_attribute(key: str) -> str:
    """Map attribute to canonical key."""
    key_lower = key.lower().strip().replace(" ", "_").replace("-", "_")
    for canonical, aliases in ATTRIBUTE_ALIASES.items():
        if key_lower == canonical or key_lower in aliases:
            return canonical
    return key_lower


# --- Physical constraints (subset for MVP) ---
PHYSICAL_CONSTRAINTS = {
    "voltage_rating": {"min": 0, "max": 100000, "unit": "V"},  # ponytail: industrial ratings top ~35kV; 100kV ceiling catches absurd extractions
    "current_rating": {"min": 0, "max": 10000, "unit": "A"},
    "power_rating": {"min": 0, "max": 1000000, "unit": "W"},
    "frequency_rating": {"min": 0, "max": 1000000000, "unit": "Hz"},
    "temperature_range": {"enum": ["-40 to 85°C", "-20 to 70°C", "0 to 50°C", "-40 to 125°C"]},
    "ip_rating": {"enum": ["IP20", "IP40", "IP44", "IP54", "IP55", "IP65", "IP66", "IP67", "IP68", "IP69K"]},
}


def validate_constraints(attribute_key: str, value: str, unit: str) -> tuple[bool, dict | None]:
    """Check physical constraints. Returns (violation, constraints_dict)."""
    canonical_key = canonicalize_attribute(attribute_key)
    constraints = PHYSICAL_CONSTRAINTS.get(canonical_key)

    if not constraints:
        return False, None

    # Enum check
    if "enum" in constraints:
        if value not in constraints["enum"]:
            return True, constraints

    # Numeric range check
    try:
        num_val = float(re.sub(r"[^\d.-]", "", value))
        if "min" in constraints and num_val < constraints["min"]:
            return True, constraints
        if "max" in constraints and num_val > constraints["max"]:
            return True, constraints
    except ValueError:
        pass

    return False, constraints


# --- Normalization pipeline ---
@dataclass
class NormalizedField:
    attribute_key: str
    attribute_label: str
    value: str | None
    unit: str
    field_type: FieldType
    confidence: float
    extraction_strength: float
    source_authority: float
    agreement: float
    sources: list[dict]
    reason_chain: list[str]
    constraint_violation: bool
    physical_constraints: dict | None


def normalize_extraction(raw_extraction: dict, source_authority: float = 1.0) -> list[NormalizedField]:
    """Convert raw VLM extraction to normalized fields with confidence factors."""
    fields = []
    attributes = raw_extraction.get("attributes", {})

    for attr_key, attr_data in attributes.items():
        if not isinstance(attr_data, dict):
            continue

        value = attr_data.get("value")
        if value is None:
            continue

        canonical_key = canonicalize_attribute(attr_key)
        canonical_unit = normalize_unit(canonical_key, attr_data.get("unit", ""))[1]

        # Determine field type from extraction
        extraction_strength = attr_data.get("extraction_strength", 0.5)
        is_corroborated = attr_data.get("corroborated", False)
        has_conflict = "conflict" in attr_data

        if has_conflict:
            # The two passes disagreed on this field's value → surface as a dispute.
            field_type = FieldType.DISPUTE
            agreement = AGREEMENT["single"]
            extraction_strength = EXTRACTION_STRENGTH["disagree"]
        elif is_corroborated:
            field_type = FieldType.PROVED
            agreement = AGREEMENT["corroborated"]
        else:
            field_type = FieldType.PROVED  # Single pass but from manufacturer doc
            agreement = AGREEMENT["single"]

        confidence_factors = ConfidenceFactors(
            extraction_strength=extraction_strength,
            source_authority=source_authority,
            agreement=agreement,
        )
        confidence = compute_confidence(confidence_factors)

        # Build sources
        sources = [{
            "ref": f"page_{attr_data.get('source_page', 1)}",
            "authority": source_authority,
            "agreement": "disputed" if has_conflict else ("corroborated" if is_corroborated else "single"),
            "bbox": attr_data.get("bbox"),
        }]
        if has_conflict:
            sources[0]["pass1"] = attr_data.get("value")
            sources[0]["pass2"] = attr_data.get("conflict", {}).get("pass2")

        # Check constraints
        constraint_violation, constraints = validate_constraints(canonical_key, str(value), canonical_unit)

        reason = (
            "Extracted from manufacturer datasheet - two passes disagreed; needs review"
            if has_conflict
            else f"Extracted from manufacturer datasheet (pass {'corroborated' if is_corroborated else 'single'})"
        )

        fields.append(NormalizedField(
            attribute_key=canonical_key,
            attribute_label=attr_key.replace("_", " ").title(),
            value=str(value),
            unit=canonical_unit,
            field_type=field_type,
            confidence=confidence,
            extraction_strength=extraction_strength,
            source_authority=source_authority,
            agreement=agreement,
            sources=sources,
            reason_chain=[reason],
            constraint_violation=constraint_violation,
            physical_constraints=constraints,
        ))

    return fields


# --- Inference from sibling SKUs ---
async def infer_from_siblings(
    product: Product,
    existing_fields: list[NormalizedField],
    session,  # AsyncSession
) -> list[NormalizedField]:
    """Infer missing attributes from sibling SKUs in the same series."""
    from sqlalchemy import select
    from app.models import SKURelationship, ProductField

    if not product.part_number or not product.manufacturer:
        return []

    # Find sibling relationships
    stmt = select(SKURelationship).where(
        (SKURelationship.sku_a == product.part_number) | (SKURelationship.sku_b == product.part_number)
    )
    result = await session.execute(stmt)
    relationships = result.scalars().all()

    if not relationships:
        return []

    # Get existing attribute keys to avoid duplicates
    existing_keys = {f.attribute_key for f in existing_fields}
    inferred = []

    for rel in relationships:
        sibling_sku = rel.sku_b if rel.sku_a == product.part_number else rel.sku_a

        # Get sibling's fields
        stmt2 = select(ProductField).join(Product).where(
            Product.part_number == sibling_sku,
            ProductField.field_type.in_([FieldType.PROVED, FieldType.HUMAN]),
        )
        result2 = await session.execute(stmt2)
        sibling_fields = result2.scalars().all()

        for sf in sibling_fields:
            if sf.attribute_key in existing_keys:
                continue

            # Infer with lower confidence
            confidence_factors = ConfidenceFactors(
                extraction_strength=0.5,  # inferred
                source_authority=SOURCE_AUTHORITY["sibling_sku"],
                agreement=AGREEMENT["single"],
            )
            confidence = cap_inferred_confidence(
                compute_confidence(confidence_factors),
                FieldType.INFERRED,
            )

            inferred.append(NormalizedField(
                attribute_key=sf.attribute_key,
                attribute_label=sf.attribute_label or sf.attribute_key.replace("_", " ").title(),
                value=sf.value,
                unit=sf.unit or "",
                field_type=FieldType.INFERRED,
                confidence=confidence,
                extraction_strength=0.5,
                source_authority=SOURCE_AUTHORITY["sibling_sku"],
                agreement=AGREEMENT["single"],
                sources=[{
                    "ref": f"sibling_sku:{sibling_sku}",
                    "authority": SOURCE_AUTHORITY["sibling_sku"],
                    "agreement": "inferred",
                }],
                reason_chain=[f"Inferred from sibling SKU {sibling_sku} (relationship: {rel.relationship_type})"],
                constraint_violation=False,
                physical_constraints=None,
            ))
            existing_keys.add(sf.attribute_key)

    return inferred


# --- Main pipeline ---
async def process_product(product_id: str, file_path: Path, session) -> Product:
    """Full pipeline: extract → normalize → infer → route → persist."""
    from sqlalchemy import select

    # Load product
    stmt = select(Product).where(Product.id == product_id)
    result = await session.execute(stmt)
    product = result.scalar_one_or_none()
    if not product:
        raise ValueError(f"Product {product_id} not found")

    product.status = ProductStatus.PROCESSING
    await session.flush()

    # 1. Extract
    vlm = get_vlm_client()
    if vlm.is_available():
        try:
            merged = vlm.extract_from_document(file_path, product.part_number)["merged"]
        except VLMError:
            # Fallback to rule-based
            merged = extract_text_fallback(file_path)
    else:
        # No VLM model present → rule-based extraction (structured PDFs)
        merged = extract_text_fallback(file_path)

    # 2. Normalize
    normalized = normalize_extraction(merged, source_authority=1.0)  # manufacturer doc

    # 3. Infer from siblings
    inferred = await infer_from_siblings(product, normalized, session)
    all_fields = normalized + inferred

    if not all_fields:
        # Nothing was extracted - never present an empty product as "exported".
        logger.warning("No attributes extracted for product %s", product.id)
        product.status = ProductStatus.FAILED
        product.confidence_distribution = {"auto_approve": 0, "borderline": 0, "forced_review": 0, "dispute": 0, "unknown": 1}
        await session.flush()
        return product

    # 4. Route each field and persist
    confidence_dist = {"auto_approve": 0, "borderline": 0, "forced_review": 0, "dispute": 0, "unknown": 0}

    for nf in all_fields:
        # Determine routing
        routing = determine_routing(
            field_type=nf.field_type,
            confidence=nf.confidence,
            extraction_strength=nf.extraction_strength,
            constraint_violation=nf.constraint_violation,
            is_dispute=nf.field_type == FieldType.DISPUTE,
            auto_approve_threshold=settings.confidence_auto_approve,
            inferred_cap=settings.confidence_inferred_cap,
            forced_review_threshold=settings.confidence_forced_review,
        )

        # Cap INFERRED confidence
        final_confidence = cap_inferred_confidence(nf.confidence, nf.field_type)

        # Create ProductField
        pf = ProductField(
            product_id=product.id,
            attribute_key=nf.attribute_key,
            attribute_label=nf.attribute_label,
            value=nf.value,
            unit=nf.unit,
            field_type=nf.field_type,
            confidence=final_confidence,
            extraction_strength=nf.extraction_strength,
            source_authority=nf.source_authority,
            agreement=nf.agreement,
            sources=nf.sources,
            reason_chain=nf.reason_chain,
            physical_constraints=nf.physical_constraints,
            constraint_violation=nf.constraint_violation,
            review_status=ReviewStatus.PENDING,
        )
        session.add(pf)

        # Update distribution (constraint violations route to forced human review)
        if routing == RoutingDecision.AUTO_APPROVE:
            confidence_dist["auto_approve"] += 1
        elif routing in (RoutingDecision.FORCED_REVIEW, RoutingDecision.CONSTRAINT_VIOLATION):
            confidence_dist["forced_review"] += 1
        elif routing == RoutingDecision.BORDERLINE_REVIEW:
            confidence_dist["borderline"] += 1
        elif routing == RoutingDecision.DISPUTE:
            confidence_dist["dispute"] += 1
        elif routing == RoutingDecision.UNKNOWN_REFUSAL:
            confidence_dist["unknown"] += 1

    # 5. Update product status
    if confidence_dist["forced_review"] > 0 or confidence_dist["dispute"] > 0 or confidence_dist["borderline"] > 0:
        product.status = ProductStatus.REVIEW
    else:
        product.status = ProductStatus.EXPORTED
        product.completed_at = datetime.now(timezone.utc)

    product.confidence_distribution = confidence_dist
    await session.flush()

    return product


# --- Export ---
def export_json_ld(product: Product) -> dict:
    """Export product as JSON-LD (schema.org Product + custom provenance)."""
    fields_data = []
    for f in product.fields:
        field_data = {
            "@type": "ProductAttribute",
            "name": f.attribute_label or f.attribute_key,
            "value": f.value,
            "unitText": f.unit,
            "paste:fieldType": f.field_type.value,
            "paste:confidence": f.confidence,
            "paste:sources": f.sources,
            "paste:reasonChain": f.reason_chain,
        }
        if f.physical_constraints:
            field_data["paste:constraints"] = f.physical_constraints
        if f.constraint_violation:
            field_data["paste:constraintViolation"] = True
        fields_data.append(field_data)

    return {
        "@context": {
            "schema": "https://schema.org/",
            "paste": "https://paste.example.org/vocab#",
        },
        "@type": "schema:Product",
        "schema:productID": product.part_number,
        "schema:manufacturer": {"@type": "schema:Organization", "schema:name": product.manufacturer},
        "schema:name": product.source_filename,
        "paste:confidenceDistribution": product.confidence_distribution,
        "paste:fields": fields_data,
        "paste:processedAt": datetime.now(timezone.utc).isoformat(),
    }


def export_gs1_csv(product: Product) -> str:
    """Export product as GS1-compliant CSV row."""
    import csv
    import io

    # GS1 core attributes + PASTE extensions
    fieldnames = [
        "GTIN", "Product_Name", "Manufacturer", "Brand", "Category",
        "Voltage_Rating", "Current_Rating", "Power_Rating", "Frequency_Rating",
        "IP_Rating", "Temperature_Range", "Dimensions", "Weight", "Material",
        "Certifications", "Description",
        "PASTE_Field_Type", "PASTE_Confidence", "PASTE_Sources", "PASTE_Reason_Chain",
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    # Map fields to GS1 columns
    field_map = {}
    for f in product.fields:
        field_map[f.attribute_key] = f

    row = {
        "GTIN": "",  # Would come from barcode/GTIN field
        "Product_Name": field_map.get("description", {}).value if "description" in field_map else product.source_filename,
        "Manufacturer": product.manufacturer or "",
        "Brand": "",
        "Category": product.category or "",
        "Voltage_Rating": field_map.get("voltage_rating", {}).value if "voltage_rating" in field_map else "",
        "Current_Rating": field_map.get("current_rating", {}).value if "current_rating" in field_map else "",
        "Power_Rating": field_map.get("power_rating", {}).value if "power_rating" in field_map else "",
        "Frequency_Rating": field_map.get("frequency_rating", {}).value if "frequency_rating" in field_map else "",
        "IP_Rating": field_map.get("ip_rating", {}).value if "ip_rating" in field_map else "",
        "Temperature_Range": field_map.get("temperature_range", {}).value if "temperature_range" in field_map else "",
        "Dimensions": field_map.get("dimensions", {}).value if "dimensions" in field_map else "",
        "Weight": field_map.get("weight", {}).value if "weight" in field_map else "",
        "Material": field_map.get("material", {}).value if "material" in field_map else "",
        "Certifications": field_map.get("certifications", {}).value if "certifications" in field_map else "",
        "Description": field_map.get("description", {}).value if "description" in field_map else "",
        "PASTE_Field_Type": ";".join(f"{k}:{v.field_type.value}" for k, v in field_map.items()),
        "PASTE_Confidence": ";".join(f"{k}:{v.confidence}" for k, v in field_map.items()),
        "PASTE_Sources": ";".join(f"{k}:{len(v.sources)}" for k, v in field_map.items()),
        "PASTE_Reason_Chain": ";".join(f"{k}:{'|'.join(v.reason_chain)}" for k, v in field_map.items()),
    }

    writer.writerow(row)
    return output.getvalue()