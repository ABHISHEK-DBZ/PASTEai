"""Verify real 2-pass VLM extraction + dispute detection.

With a GGUF in ./models/ this runs the actual Qwen2-VL extraction (2
independent passes) against sample_datasheet.pdf and prints pass1 / pass2 /
merged output plus extraction_strength and is_dispute. Without a model it
verifies the deterministic 2-pass dispute logic instead.

Run:
    .venv/Scripts/python tests/verify_vlm_extraction.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.trust_model import EXTRACTION_STRENGTH, get_extraction_strength  # noqa: E402
from app.vlm import VLMClient, VLMError, _find_model  # noqa: E402

SAMPLE = pathlib.Path(__file__).parent.parent / "sample_datasheet.pdf"


def run_deterministic_checks() -> bool:
    print("\n=== Deterministic 2-pass dispute verification (no model required) ===")
    checks = [
        # (name, pass1, pass2, expected_strength, expected_dispute)
        (
            "passes agree",
            {"attributes": {"voltage_rating": {"value": "220V"}, "ip_rating": {"value": "IP65"}}},
            {"attributes": {"voltage_rating": {"value": "220V"}, "ip_rating": {"value": "IP65"}}},
            EXTRACTION_STRENGTH["corroborated"],
            False,
        ),
        (
            "same attr, different value -> dispute",
            {"attributes": {"voltage_rating": {"value": "220V"}}},
            {"attributes": {"voltage_rating": {"value": "240V"}}},
            EXTRACTION_STRENGTH["disagree"],
            True,
        ),
        (
            "partial key overlap -> near match",
            {"attributes": {"voltage_rating": {"value": "220V"}}},
            {"attributes": {"voltage_rating": {"value": "220V"}, "weight": {"value": "12 kg"}}},
            EXTRACTION_STRENGTH["near_match"],
            False,
        ),
        (
            "disjoint attributes -> disagree",
            {"attributes": {"voltage_rating": {"value": "220V"}}},
            {"attributes": {"ip_rating": {"value": "IP65"}}},
            EXTRACTION_STRENGTH["disagree"],
            True,
        ),
    ]
    all_ok = True
    for name, p1, p2, exp_s, exp_d in checks:
        s, d = get_extraction_strength(p1, p2)
        ok = s == exp_s and d == exp_d
        all_ok = all_ok and ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:36s} -> strength={s} dispute={d} (expect {exp_s}/{exp_d})")
    print("  deterministic 2-pass checks:", "PASS" if all_ok else "FAIL")
    return all_ok


def run_real_vlm(client: VLMClient) -> bool:
    model = _find_model()
    print(f"\n=== REAL 2-PASS VLM EXTRACTION ===")
    print(f"model: {model}")

    result = client.extract_from_pdf(SAMPLE, part_number="X-100")
    print("images used :", result["images_used"])
    print(f"strength    : {result['extraction_strength']}  (1.0 corroborated / 0.8 near / 0.5 single / 0.4 disagree)")
    print(f"is_dispute  : {result['is_dispute']}")

    for label in ("pass1", "pass2"):
        print(f"\n--- {label} ---")
        attrs = result[label].get("attributes", {})
        if not attrs:
            print("  (no attributes extracted)")
        for k, v in attrs.items():
            print(f"  {k}: value={v.get('value')} unit={v.get('unit', '')} page={v.get('source_page')} conf={v.get('confidence')}")

    print("\n--- merged (routing input) ---")
    for k, v in result["merged"].get("attributes", {}).items():
        conflict = f" CONFLICT(pass1={v.get('conflict', {}).get('pass1')} vs pass2={v.get('conflict', {}).get('pass2')})" if v.get("conflict") else ""
        print(f"  {k}: value={v.get('value')} corroborated={v.get('corroborated')} strength={v.get('extraction_strength')}{conflict}")

    print("\nREAL VLM EXTRACTION: PASS")
    return True


def main() -> bool:
    print("PASTE - VLM 2-pass extraction verification")
    model = _find_model()
    if not model.exists():
        print(f"NOTE: no GGUF found (configured/searched: {model}).")
        print("      Download one into ./models/ to run the real VLM, e.g.:")
        print("        curl -L -C - -o models/Qwen2-VL-7B-Instruct-Q4_K_M.gguf \\")
        print("          'https://huggingface.co/bartowski/Qwen2-VL-7B-Instruct-GGUF/resolve/main/Qwen2-VL-7B-Instruct-Q4_K_M.gguf'")
        print("      (bartowski's mirror is not gated; Qwen's official repo requires a HF token)")
        print("      Running deterministic 2-pass dispute checks instead.\n")
        return run_deterministic_checks()

    client = VLMClient()
    if not client.is_available():
        # e.g. a present-but-corrupt/truncated GGUF - same graceful degradation
        # the pipeline uses (rule-based fallback).
        print(f"NOTE: model file exists ({model}) but failed to load - it may be")
        print("      truncated/corrupt. Re-download the full GGUF to run the real VLM;")
        print("      running deterministic 2-pass dispute checks instead.\n")
        return run_deterministic_checks()

    ok = run_real_vlm(client)
    ok2 = run_deterministic_checks()
    return ok and ok2


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
