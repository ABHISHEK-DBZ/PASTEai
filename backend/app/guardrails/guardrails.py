from __future__ import annotations

import re
from typing import Any

import numpy as np


class GuardrailChecker:
    def __init__(self, domain_keywords: list[str] | None = None, min_score: float = 0.35):
        self.domain_keywords = domain_keywords or [
            "education", "health", "travel", "science", "technology", "government", "law",
            "finance", "policy", "history", "language", "business", "medicine", "job",
            "career", "learning", "school", "city", "country", "infrastructure",
        ]
        self.min_score = min_score

    def is_unsafe(self, raw_query: str) -> bool:
        unsafe_patterns = [
            r"hack\s+.*\bserver\b",
            r"\bexploit\b",
            r"\bmalware\b",
            r"\bweapon\b",
            r"\bkill\b",
            r"\bself[- ]harm\b",
            r"\battack\b",
        ]
        text = raw_query.lower()
        for pattern in unsafe_patterns:
            if re.search(pattern, text):
                return True
        return False

    def off_topic(self, query: str, centroid: np.ndarray | None = None, query_embedding: np.ndarray | None = None) -> bool:
        if centroid is None or query_embedding is None:
            tokens = set(re.findall(r"[a-zA-Z]+", query.lower()))
            score = sum(1 for token in tokens if token in self.domain_keywords)
            return score == 0 and len(tokens) > 0
        try:
            similarity = float(np.dot(query_embedding, centroid) / (np.linalg.norm(query_embedding) * np.linalg.norm(centroid)))
            return similarity < 0.15
        except Exception:
            return False

    def low_confidence(self, merged_score: float) -> bool:
        return merged_score < self.min_score

    def grounded(self, answer: str, cited_chunks: list[str], chunk_texts: dict[str, str]) -> bool:
        if not answer:
            return False
        answer_tokens = set(re.findall(r"[a-zA-Z0-9]+", answer.lower()))
        cited_text = " ".join(chunk_texts.get(chk, "") for chk in cited_chunks)
        if not cited_text:
            return False
        cited_tokens = set(re.findall(r"[a-zA-Z0-9]+", cited_text.lower()))
        overlap = len(answer_tokens & cited_tokens)
        return overlap > 0 or len(answer_tokens) == 0

    def explain(self, answer: str, chunks: list[str], chunk_texts: dict[str, str]) -> dict[str, Any]:
        grounded = self.grounded(answer, chunks, chunk_texts)
        return {
            "grounded": grounded,
            "cited_chunks": chunks,
            "grounding_failure": not grounded,
        }
