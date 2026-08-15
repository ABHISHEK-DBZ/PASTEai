from __future__ import annotations

import base64
import json
import logging
import mimetypes
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pdfplumber

from app.config import settings
from app.trust_model import EXTRACTION_STRENGTH, get_extraction_strength

logger = logging.getLogger("paste.vlm")


class VLMError(Exception):
    """Raised when a configured model cannot produce a usable extraction."""


class VLMClient:
    """Two-pass OpenAI-compatible vision extraction client.

    The API is optional: with no API key the caller can use the deterministic
    PDF fallback.  This keeps local development usable without pretending a
    text-only llama.cpp instance can process document images.
    """

    _instance: "VLMClient | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.client: Any | None = None
        provider = settings.model_provider.strip().lower()
        if provider not in {"auto", "openai"}:
            logger.warning("Unsupported MODEL_PROVIDER=%r; using deterministic fallback", provider)
        elif settings.openai_api_key:
            try:
                from openai import OpenAI

                options: dict[str, Any] = {
                    "api_key": settings.openai_api_key,
                    "timeout": settings.model_timeout_seconds,
                }
                if settings.openai_base_url:
                    options["base_url"] = settings.openai_base_url
                self.client = OpenAI(**options)
                logger.info("Vision extraction configured with model %s", settings.openai_model)
            except Exception as exc:
                logger.warning("Model API unavailable; using deterministic fallback: %s", exc)
        elif provider == "openai":
            logger.warning("MODEL_PROVIDER=openai but OPENAI_API_KEY is not configured")
        self._initialized = True

    def is_available(self) -> bool:
        return self.client is not None

    def extract_from_pdf(self, pdf_path: Path, part_number: str | None = None) -> dict[str, Any]:
        """Backward-compatible alias for PDF callers."""
        return self.extract_from_document(pdf_path, part_number)

    def extract_from_document(self, document_path: Path, part_number: str | None = None) -> dict[str, Any]:
        """Run independent extraction passes for a PDF or supported image."""
        if not self.client:
            raise VLMError("No model API is configured. Set OPENAI_API_KEY to enable vision extraction.")
        if not document_path.exists():
            raise VLMError(f"Source document not found: {document_path}")

        with TemporaryDirectory(prefix="paste-vlm-") as tmp:
            images = self._document_images(document_path, Path(tmp))
            if not images:
                return self._result_from_passes({"attributes": {}}, {"attributes": {}}, [])
            pass1 = self._run_model(self._build_extraction_prompt(part_number, 1), images)
            pass2 = self._run_model(self._build_extraction_prompt(part_number, 2), images)
            return self._result_from_passes(pass1, pass2, images)

    @staticmethod
    def _document_images(document_path: Path, output_dir: Path, max_pages: int = 5) -> list[Path]:
        suffix = document_path.suffix.lower()
        if suffix != ".pdf":
            if suffix not in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
                raise VLMError(f"Unsupported document type: {suffix or '(none)'}")
            return [document_path]
        try:
            import fitz

            document = fitz.open(document_path)
            images: list[Path] = []
            for index, page in enumerate(document):
                if index >= max_pages:
                    break
                image_path = output_dir / f"page-{index + 1}.png"
                page.get_pixmap(dpi=150).save(str(image_path))
                images.append(image_path)
            document.close()
            return images
        except Exception as exc:
            raise VLMError(f"Could not render PDF for model extraction: {exc}") from exc

    @staticmethod
    def _build_extraction_prompt(part_number: str | None, pass_num: int) -> str:
        known_part = f"Known part number: {part_number}" if part_number else ""
        return f"""Extract only product attributes visibly evidenced in these technical-document images.
Return exactly one JSON object with this schema:
{{"attributes": {{"attribute_key": {{"value": "string", "unit": "string", "source_page": 1, "bbox": [0,0,1,1]}}}}}}

Rules:
- Do not infer, estimate, or invent values. Omit absent attributes.
- Use canonical keys where possible: voltage_rating, current_rating, power_rating,
  frequency_rating, ip_rating, temperature_range, dimensions, weight, material,
  certifications, part_number, manufacturer, series, description.
- bbox is optional and must be normalized 0-1 when supplied.
- Return JSON only, with no Markdown.
{known_part}
This is independent extraction pass {pass_num} of 2."""

    def _run_model(self, prompt: str, images: list[Path]) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image_path in images:
            mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
            encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}})
        try:
            response = self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": content}],
                temperature=settings.vlm_temperature,
                top_p=settings.vlm_top_p,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            parsed = json.loads(raw)
        except Exception as exc:
            raise VLMError(f"Model API extraction failed: {exc}") from exc
        if not isinstance(parsed, dict):
            raise VLMError("Model API returned JSON that is not an object")
        attributes = parsed.get("attributes", {})
        if not isinstance(attributes, dict):
            raise VLMError("Model API response has an invalid attributes object")
        return {"attributes": attributes}

    def _result_from_passes(self, pass1: dict[str, Any], pass2: dict[str, Any], images: list[Path]) -> dict[str, Any]:
        extraction_strength, is_dispute = get_extraction_strength(pass1, pass2)
        return {
            "pass1": pass1,
            "pass2": pass2,
            "merged": self._merge_passes(pass1, pass2),
            "extraction_strength": extraction_strength,
            "is_dispute": is_dispute,
            "images_used": [str(image) for image in images],
        }

    @staticmethod
    def _merge_passes(pass1: dict[str, Any], pass2: dict[str, Any]) -> dict[str, Any]:
        attrs1 = pass1.get("attributes", {}) or {}
        attrs2 = pass2.get("attributes", {}) or {}
        merged: dict[str, dict[str, Any]] = {}
        for key in set(attrs1) | set(attrs2):
            first, second = attrs1.get(key), attrs2.get(key)
            if not isinstance(first, dict):
                first = None
            if not isinstance(second, dict):
                second = None
            if first and second:
                if str(first.get("value", "")).strip().casefold() == str(second.get("value", "")).strip().casefold():
                    merged[key] = {**first, "corroborated": True, "extraction_strength": EXTRACTION_STRENGTH["corroborated"]}
                else:
                    merged[key] = {
                        **first,
                        "corroborated": False,
                        "conflict": {"pass1": first.get("value"), "pass2": second.get("value")},
                        "extraction_strength": EXTRACTION_STRENGTH["disagree"],
                    }
            elif first:
                merged[key] = {**first, "corroborated": False, "extraction_strength": EXTRACTION_STRENGTH["single_pass"]}
            elif second:
                merged[key] = {**second, "corroborated": False, "extraction_strength": EXTRACTION_STRENGTH["single_pass"]}
        return {"attributes": merged}


def extract_text_fallback(document_path: Path) -> dict[str, Any]:
    """Extract basic key/value data from structured PDFs without an AI model."""
    if document_path.suffix.lower() != ".pdf":
        logger.warning("No model API configured for image source %s", document_path.name)
        return {"attributes": {}}

    attributes: dict[str, dict[str, Any]] = {}
    try:
        with pdfplumber.open(document_path) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    for row in table:
                        if len(row) < 2 or not row[0] or not row[1]:
                            continue
                        key = str(row[0]).strip().lower().replace(" ", "_").replace("/", "_")
                        value = str(row[1]).strip()
                        if key and value and len(key) < 64:
                            attributes[key] = {"value": value, "unit": "", "source_page": page.page_number}
                text = page.extract_text() or ""
                for line in text.splitlines():
                    if ":" not in line:
                        continue
                    key, value = (part.strip() for part in line.split(":", 1))
                    key = key.lower().replace(" ", "_")
                    if key and value and len(key) < 64 and any(char.isdigit() for char in value):
                        attributes[key] = {"value": value, "unit": "", "source_page": page.page_number}
    except Exception as exc:
        raise VLMError(f"PDF fallback extraction failed: {exc}") from exc
    return {"attributes": attributes}


def get_vlm_client() -> VLMClient:
    return VLMClient()
