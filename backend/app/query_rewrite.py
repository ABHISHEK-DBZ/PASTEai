from __future__ import annotations

import re


class QueryRewriter:
    def __init__(self):
        self.filler_patterns = [
            r"\buh\b",
            r"\bumm\b",
            r"\bummm\b",
            r"\buhm\b",
            r"\blike\b",
            r"\bya know\b",
            r"\byou know\b",
            r"\bI mean\b",
            r"\bactually\b",
        ]

    def rewrite(self, text: str) -> str:
        cleaned = text.strip()
        for pattern in self.filler_patterns:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()
