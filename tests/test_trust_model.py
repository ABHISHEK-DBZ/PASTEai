"""Self-check for PASTE trust model — the core product intelligence.

Run: uv run --with pytest pytest tests/test_trust_model.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.trust_model import (
    compute_confidence, ConfidenceFactors, determine_routing, RoutingDecision,
    cap_inferred_confidence, get_extraction_strength,
)
from app.models import FieldType
from app.pipeline import normalize_extraction, validate_constraints, canonicalize_attribute, normalize_unit


def test_confidence_formula():
    # confidence = strength * authority * agreement
    f = ConfidenceFactors(extraction_strength=1.0, source_authority=1.0, agreement=1.0)
    assert compute_confidence(f) == 1.0
    f2 = ConfidenceFactors(extraction_strength=0.4, source_authority=0.7, agreement=1.0)
    assert abs(compute_confidence(f2) - 0.28) < 1e-9


def test_routing_auto_approve():
    d = determine_routing(FieldType.PROVED, 0.97, 1.0, False, False)
    assert d == RoutingDecision.AUTO_APPROVE


def test_routing_forced_review_on_disagree():
    d = determine_routing(FieldType.PROVED, 0.90, 0.4, False, False)
    assert d == RoutingDecision.FORCED_REVIEW


def test_routing_inferred_never_auto():
    d = determine_routing(FieldType.INFERRED, 0.95, 1.0, False, False)
    assert d == RoutingDecision.FORCED_REVIEW  # INFERRED always to review queue


def test_inferred_cap():
    assert cap_inferred_confidence(0.95, FieldType.INFERRED) == 0.70
    assert cap_inferred_confidence(0.95, FieldType.PROVED) == 0.95  # PROVED not capped


def test_routing_dispute():
    d = determine_routing(FieldType.DISPUTE, 0.80, 1.0, False, True)
    assert d == RoutingDecision.DISPUTE


def test_routing_constraint_violation():
    d = determine_routing(FieldType.PROVED, 0.99, 1.0, True, False)
    assert d == RoutingDecision.CONSTRAINT_VIOLATION


def test_routing_unknown_refusal():
    d = determine_routing(FieldType.UNKNOWN, 0.0, 1.0, False, False)
    assert d == RoutingDecision.UNKNOWN_REFUSAL


def test_extraction_strength_corroborated():
    p1 = {"attributes": {"voltage": "220V"}}
    p2 = {"attributes": {"voltage": "220V"}}
    strength, dispute = get_extraction_strength(p1, p2)
    assert strength == 1.0
    assert dispute is False


def test_extraction_strength_disagree():
    p1 = {"attributes": {"voltage": "220V"}}
    p2 = {"attributes": {"voltage": "240V"}}
    strength, dispute = get_extraction_strength(p1, p2)
    assert strength == 0.4
    assert dispute is True


def test_normalize_unit():
    key, unit = normalize_unit("voltage_rating", "v")
    assert key == "voltage_rating" and unit == "V"
    key2, unit2 = normalize_unit("weight", "kg")
    assert unit2 == "kg"


def test_canonicalize_attribute():
    assert canonicalize_attribute("Rated Voltage") == "voltage_rating"
    assert canonicalize_attribute("IP Code") == "ip_rating"
    assert canonicalize_attribute("weird_field") == "weird_field"


def test_validate_constraints_ip_ok():
    viol, cons = validate_constraints("ip_rating", "IP65", "IP")
    assert viol is False


def test_validate_constraints_ip_bad():
    viol, cons = validate_constraints("ip_rating", "IP99", "IP")
    assert viol is True


def test_validate_constraints_voltage_range():
    viol, cons = validate_constraints("voltage_rating", "999999", "V")
    assert viol is True


def test_normalize_extraction_produces_fields():
    raw = {
        "attributes": {
            "voltage": {"value": "220V", "unit": "V", "source_page": 2,
                        "extraction_strength": 1.0, "corroborated": True},
        }
    }
    fields = normalize_extraction(raw, source_authority=1.0)
    assert len(fields) == 1
    f = fields[0]
    assert f.attribute_key == "voltage_rating"
    assert f.value == "220V"
    assert f.field_type == FieldType.PROVED
    assert f.confidence > 0.9


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
