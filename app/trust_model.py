from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.models import FieldType


class RoutingDecision(str, Enum):
    AUTO_APPROVE = "auto_approve"
    BORDERLINE_REVIEW = "borderline_review"
    FORCED_REVIEW = "forced_review"
    DISPUTE = "dispute"
    CONSTRAINT_VIOLATION = "constraint_violation"
    UNKNOWN_REFUSAL = "unknown_refusal"


@dataclass(frozen=True)
class ConfidenceFactors:
    extraction_strength: float
    source_authority: float
    agreement: float

    def compute(self) -> float:
        return round(self.extraction_strength * self.source_authority * self.agreement, 4)


# Trust model constants (single source of truth)
EXTRACTION_STRENGTH = {
    "corroborated": 1.0,      # 2 independent passes agree
    "near_match": 0.8,        # passes nearly agree
    "single_pass": 0.5,       # only one pass succeeded
    "disagree": 0.4,          # passes disagree → forced review
}

SOURCE_AUTHORITY = {
    "manufacturer": 1.0,      # official manufacturer doc
    "distributor": 0.7,       # distributor / catalog
    "sibling_sku": 0.5,       # inferred from sibling SKU
    "model_predicted": 0.3,   # model predicted
}

AGREEMENT = {
    "corroborated": 1.0,      # ≥2 independent sources agree
    "single": 0.7,            # single source
}


def compute_confidence(factors: ConfidenceFactors) -> float:
    """Compute confidence = extraction_strength × source_authority × agreement."""
    return factors.compute()


def determine_routing(
    field_type: FieldType,
    confidence: float,
    extraction_strength: Optional[float],
    constraint_violation: bool,
    is_dispute: bool,
    auto_approve_threshold: float = 0.90,
    inferred_cap: float = 0.70,
    forced_review_threshold: float = 0.50,
) -> RoutingDecision:
    """
    Routing rules evaluated in order (first match wins):
    1. UNKNOWN → never published
    2. Conflicting sources → DISPUTE
    3. extraction_strength < 0.5 (disagree) → forced human review
    4. INFERRED → capped at inferred_cap, never auto-export
    5. Physical constraint violation → forced review
    6. confidence >= auto_approve_threshold → auto-approve
    7. Else → borderline review
    """
    # Rule 1: UNKNOWN fields never published
    if field_type == FieldType.UNKNOWN:
        return RoutingDecision.UNKNOWN_REFUSAL

    # Rule 2: Conflicting sources (checked before low-strength so a value
    # disagreement surfaces as a DISPUTE, not a generic forced review).
    if is_dispute:
        return RoutingDecision.DISPUTE

    # Rule 3: Disagreement between passes → forced review
    if extraction_strength is not None and extraction_strength < forced_review_threshold:
        return RoutingDecision.FORCED_REVIEW

    # Rule 4: INFERRED capped, never auto-export
    if field_type == FieldType.INFERRED:
        return RoutingDecision.FORCED_REVIEW  # INFERRED always goes to review queue

    # Rule 5: Physical constraint violation
    if constraint_violation:
        return RoutingDecision.CONSTRAINT_VIOLATION

    # Rule 6: High confidence → auto-approve
    if confidence >= auto_approve_threshold:
        return RoutingDecision.AUTO_APPROVE

    # Rule 7: Everything else → borderline review
    return RoutingDecision.BORDERLINE_REVIEW


def cap_inferred_confidence(confidence: float, field_type: FieldType, cap: float = 0.70) -> float:
    """Cap INFERRED confidence at cap (default 0.70)."""
    if field_type == FieldType.INFERRED and confidence > cap:
        return cap
    return confidence


def get_extraction_strength(pass1_result: dict, pass2_result: dict) -> tuple[float, bool]:
    """
    Compare two extraction passes by their attribute *values* (ignoring per-field
    metadata such as bbox/confidence that legitimately differ between runs).
    Returns (extraction_strength, is_dispute).
    """
    attrs1 = pass1_result.get("attributes", {}) or {}
    attrs2 = pass2_result.get("attributes", {}) or {}

    def values(attrs: dict) -> dict[str, str]:
        out = {}
        for k, v in attrs.items():
            if isinstance(v, dict):
                out[k] = str(v.get("value"))
            else:
                out[k] = str(v)
        return out

    v1, v2 = values(attrs1), values(attrs2)
    keys1, keys2 = set(v1), set(v2)

    if not attrs1 or not attrs2:
        # One or both passes produced nothing - weak signal, not a dispute.
        return EXTRACTION_STRENGTH["single_pass"], False

    if keys1 != keys2:
        # Partial key overlap (one pass found extra attributes) → near match.
        if keys1 & keys2:
            return EXTRACTION_STRENGTH["near_match"], False
        # Disjoint attribute sets.
        return EXTRACTION_STRENGTH["disagree"], True

    mismatches = sum(1 for k in keys1 if v1[k] != v2[k])
    if mismatches == 0:
        return EXTRACTION_STRENGTH["corroborated"], False
    # Same attribute present in both passes with a different value = genuine dispute.
    return EXTRACTION_STRENGTH["disagree"], True