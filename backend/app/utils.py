import re
import time
from collections.abc import Iterable


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def simple_tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+(?:'[a-zA-Z0-9]+)?", text.lower())


def safe_float(value: float, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def now_ms() -> float:
    return time.perf_counter() * 1000.0
