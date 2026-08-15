"""Verify two-pass model API extraction and deterministic dispute routing.

With OPENAI_API_KEY configured this invokes the configured OpenAI-compatible
vision model. Otherwise it validates the deterministic pass-comparison logic.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.trust_model import EXTRACTION_STRENGTH, get_extraction_strength  # noqa: E402
from app.vlm import VLMClient  # noqa: E402

SAMPLE = pathlib.Path(__file__).parent.parent / "sample_datasheet.pdf"


def run_deterministic_checks() -> bool:
    print("\n=== Deterministic 2-pass dispute verification ===")
    checks = [
        ("passes agree", {"attributes": {"voltage_rating": {"value": "220V"}}}, {"attributes": {"voltage_rating": {"value": "220V"}}}, EXTRACTION_STRENGTH["corroborated"], False),
        ("same attribute disagrees", {"attributes": {"voltage_rating": {"value": "220V"}}}, {"attributes": {"voltage_rating": {"value": "240V"}}}, EXTRACTION_STRENGTH["disagree"], True),
        ("partial overlap", {"attributes": {"voltage_rating": {"value": "220V"}}}, {"attributes": {"voltage_rating": {"value": "220V"}, "weight": {"value": "12 kg"}}}, EXTRACTION_STRENGTH["near_match"], False),
        ("disjoint attributes", {"attributes": {"voltage_rating": {"value": "220V"}}}, {"attributes": {"ip_rating": {"value": "IP65"}}}, EXTRACTION_STRENGTH["disagree"], True),
    ]
    passed = True
    for name, first, second, expected_strength, expected_dispute in checks:
        strength, dispute = get_extraction_strength(first, second)
        ok = strength == expected_strength and dispute == expected_dispute
        passed = passed and ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: strength={strength}, dispute={dispute}")
    return passed


def run_real_model(client: VLMClient) -> bool:
    print("\n=== REAL 2-PASS MODEL API EXTRACTION ===")
    result = client.extract_from_document(SAMPLE, part_number="X-100")
    print("images used:", result["images_used"])
    print("strength:", result["extraction_strength"], "dispute:", result["is_dispute"])
    print("merged attributes:", list(result["merged"].get("attributes", {})))
    return True


def main() -> bool:
    print("PASTE - model API verification")
    client = VLMClient()
    if not client.is_available():
        print("NOTE: OPENAI_API_KEY is not configured; model API call skipped.")
        return run_deterministic_checks()
    return run_real_model(client) and run_deterministic_checks()


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)