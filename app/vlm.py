from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

import pdfplumber
from llama_cpp import Llama
from PIL import Image
import fitz

from app.config import settings
from app.trust_model import EXTRACTION_STRENGTH


def _find_model() -> Path:
    """Resolve the GGUF model path.

    Order: explicit VLM_MODEL_PATH → any *.gguf beside it → any *.gguf in the
    project's ./models directory. This lets you drop in any Qwen2-VL (or LLaVA)
    GGUF regardless of the exact filename.
    """
    configured = Path(settings.vlm_model_path)
    if configured.exists():
        return configured

    candidates = []
    parent = configured.parent
    if parent.exists():
        candidates.extend(sorted(parent.glob("*.gguf")))
    # Local dev: project-root models/ dir
    local_models = Path(__file__).resolve().parent.parent / "models"
    if local_models.exists():
        candidates.extend(sorted(local_models.glob("*.gguf")))

    if candidates:
        chosen = candidates[0]
        logging.getLogger("paste.vlm").warning(
            "Configured model %s not found - using discovered %s", configured, chosen
        )
        return chosen
    return configured


class VLMError(Exception):
    pass


# Anything below this is clearly a truncated download (real 2B/7B GGUFs are >= 100 MB).
MIN_VALID_MODEL_BYTES = 100 * 1024 * 1024


class VLMClient:
    """Wrapper around llama.cpp for Qwen2-VL / LLaVA extraction."""

    _instance: VLMClient | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.llm = None
        try:
            self._load_model()
        except VLMError as e:
            # ponytail: model optional at runtime — fall back to rule-based extraction
            logging.getLogger("paste.vlm").warning("VLM unavailable, using rule-based fallback: %s", e)
        except Exception as e:
            # A present-but-corrupt/truncated GGUF raises from llama.cpp (not VLMError).
            # Treat it like a missing model so extraction degrades to the rule-based
            # fallback instead of crashing the processing job.
            logging.getLogger("paste.vlm").warning(
                "VLM failed to initialize (%s: %s), using rule-based fallback", type(e).__name__, e
            )
        self._initialized = True

    def is_available(self) -> bool:
        return self.llm is not None

    def _load_model(self):
        model_path = _find_model()
        if not model_path.exists():
            raise VLMError(
                f"Model not found at {model_path}. Download any Qwen2-VL GGUF into ./models/ "
                "(e.g. bartowski/Qwen2-VL-7B-Instruct-GGUF) or set VLM_MODEL_PATH."
            )

        # Any real 7B (or 2B) GGUF is hundreds of MB to GBs. A file far smaller
        # than that is a truncated/corrupt download - fail fast instead of letting
        # llama.cpp crash mid-init (which also dumps a noisy __del__ traceback).
        if model_path.stat().st_size < MIN_VALID_MODEL_BYTES:
            raise VLMError(
                f"Model file {model_path} is only {model_path.stat().st_size} bytes - "
                "the download appears truncated. Re-download the full GGUF "
                f"(at least {MIN_VALID_MODEL_BYTES // (1024 * 1024)} MB)."
            )

        self.llm = Llama(
            model_path=str(model_path),
            n_ctx=settings.vlm_n_ctx,
            n_gpu_layers=settings.vlm_n_gpu_layers,
            verbose=False,
            n_threads=8,
            use_mmap=True,
            use_mlock=False,
        )

    def _encode_image(self, image_path: Path) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _pdf_to_images(self, pdf_path: Path, max_pages: int = 5) -> list[Path]:
        """Convert PDF pages to images for VLM."""
        output_dir = Path("/tmp/pdf_images")
        output_dir.mkdir(exist_ok=True)

        doc = fitz.open(pdf_path)
        images = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(dpi=150)
            img_path = output_dir / f"{pdf_path.stem}_page_{i+1}.png"
            pix.save(str(img_path))
            images.append(img_path)
        doc.close()
        return images

    def extract_from_pdf(self, pdf_path: Path, part_number: str | None = None) -> dict[str, Any]:
        """Run 2-pass extraction on a PDF."""
        images = self._pdf_to_images(pdf_path)

        # Pass 1
        prompt = self._build_extraction_prompt(part_number, pass_num=1)
        pass1 = self._run_vlm(prompt, images)

        # Pass 2 (independent)
        prompt2 = self._build_extraction_prompt(part_number, pass_num=2)
        pass2 = self._run_vlm(prompt2, images)

        # Compare passes
        from app.trust_model import get_extraction_strength
        extraction_strength, is_dispute = get_extraction_strength(pass1, pass2)

        # Merge results (prefer corroborated fields)
        merged = self._merge_passes(pass1, pass2)

        return {
            "pass1": pass1,
            "pass2": pass2,
            "merged": merged,
            "extraction_strength": extraction_strength,
            "is_dispute": is_dispute,
            "images_used": [str(p) for p in images],
        }

    def _build_extraction_prompt(self, part_number: str | None, pass_num: int) -> str:
        base = f"""You are an expert industrial product data extractor. Extract ONLY evidenced attributes from the provided datasheet images.

RULES:
1. Return ONLY valid JSON. No markdown, no explanations.
2. If an attribute is NOT visibly present in the images, OMIT it (do not guess).
3. For each attribute, include: value, unit (if applicable), confidence (0-1), source_page, bbox [x0,y0,x1,y1] normalized 0-1.
4. Focus on: electrical (voltage, current, power, frequency), mechanical (dimensions, weight, IP rating, material), environmental (temp range, humidity, certifications), identification (part number, manufacturer, series, description).
5. Be conservative. Better to miss an attribute than hallucinate.

{f"Known part number: {part_number}" if part_number else ""}

Pass {pass_num} of 2 - work independently."""

        return base

    def _run_vlm(self, prompt: str, images: list[Path]) -> dict[str, Any]:
        """Run VLM with images, return parsed JSON."""
        if not images:
            return {"attributes": {}}

        # Build messages with images
        content = [{"type": "text", "text": prompt}]
        for img_path in images:
            b64 = self._encode_image(img_path)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"}
            })

        response = self.llm.create_chat_completion(
            messages=[{"role": "user", "content": content}],
            temperature=settings.vlm_temperature,
            top_p=settings.vlm_top_p,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )

        try:
            result = json.loads(response["choices"][0]["message"]["content"])
            return result if isinstance(result, dict) else {"attributes": {}}
        except (json.JSONDecodeError, KeyError) as e:
            raise VLMError(f"Failed to parse VLM response: {e}")

    def _merge_passes(self, pass1: dict, pass2: dict) -> dict[str, Any]:
        """Merge two extraction passes, preferring corroborated fields."""
        attrs1 = pass1.get("attributes", {})
        attrs2 = pass2.get("attributes", {})

        merged = {}
        all_keys = set(attrs1.keys()) | set(attrs2.keys())

        for key in all_keys:
            v1 = attrs1.get(key)
            v2 = attrs2.get(key)

            if v1 and v2:
                # Both passes found it - check agreement
                if str(v1.get("value")) == str(v2.get("value")):
                    # Corroborated
                    merged[key] = {
                        **v1,
                        "corroborated": True,
                        "extraction_strength": EXTRACTION_STRENGTH["corroborated"],
                    }
                else:
                    # Disagreement - mark for review
                    merged[key] = {
                        **v1,
                        "corroborated": False,
                        "conflict": {"pass1": v1.get("value"), "pass2": v2.get("value")},
                        "extraction_strength": EXTRACTION_STRENGTH["disagree"],
                    }
            elif v1:
                merged[key] = {**v1, "corroborated": False, "extraction_strength": EXTRACTION_STRENGTH["single_pass"]}
            else:
                merged[key] = {**v2, "corroborated": False, "extraction_strength": EXTRACTION_STRENGTH["single_pass"]}

        return {"attributes": merged}


def extract_text_fallback(pdf_path: Path) -> dict[str, Any]:
    """Rule-based fallback using pdfplumber for structured PDFs."""
    attributes = {}

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if len(row) >= 2:
                        key = str(row[0]).strip().lower().replace(" ", "_").replace("/", "_")
                        val = str(row[1]).strip()
                        if key and val and len(key) < 64:
                            attributes[key] = {
                                "value": val,
                                "unit": "",
                                "confidence": 0.7,
                                "source_page": page.page_number,
                                "extraction_method": "pdfplumber_table",
                            }

            # Also try key-value patterns in text
            text = page.extract_text()
            if text:
                import re
                for line in text.split("\n"):
                    if ":" in line:
                        parts = line.split(":", 1)
                        key = parts[0].strip().lower().replace(" ", "_")
                        val = parts[1].strip()
                        if key and val and len(key) < 64 and any(c.isdigit() for c in val):
                            attributes[key] = {
                                "value": val,
                                "unit": "",
                                "confidence": 0.5,
                                "source_page": page.page_number,
                                "extraction_method": "pdfplumber_kv",
                            }

    return {"attributes": attributes}


# Singleton accessor
def get_vlm_client() -> VLMClient:
    return VLMClient()
