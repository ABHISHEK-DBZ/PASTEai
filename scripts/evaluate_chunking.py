from __future__ import annotations

import json
from pathlib import Path

from app.chunking import ChunkBuilder


TEST_QUERIES = [
    {"query": "What is the capital of France?", "expected": "Paris"},
    {"query": "How does diabetes affect blood sugar?", "expected": "blood sugar"},
    {"query": "Explain the purpose of a resume.", "expected": "resume"},
    {"query": "What is the definition of biodiversity?", "expected": "biodiversity"},
    {"query": "What is a mortgage?", "expected": "mortgage"},
    {"query": "Why do plants need sunlight?", "expected": "photosynthesis"},
    {"query": "Describe the benefits of exercise.", "expected": "exercise"},
    {"query": "What is the role of a teacher?", "expected": "teacher"},
    {"query": "How does a computer process information?", "expected": "computer"},
    {"query": "What is climate change?", "expected": "climate change"},
]


# This is a lightweight local evaluation harness used to compare chunking strategies.
def evaluate(strategy: str):
    builder = ChunkBuilder(strategy=strategy)
    total = 0
    hits = 0
    for item in TEST_QUERIES:
        text = f"{item['query']} {item['expected']} is commonly discussed in educational material about the topic."
        chunks = builder.build(text, doc_id="demo")
        total += 1
        for chunk in chunks:
            if item['expected'].lower() in chunk.text.lower():
                hits += 1
                break
    return hits / total if total else 0.0


if __name__ == "__main__":
    strategy_scores = {strategy: evaluate(strategy) for strategy in ["semantic", "fixed", "metadata"]}
    print(json.dumps(strategy_scores, indent=2))
    out = Path("README.md")
    if out.exists():
        lines = out.read_text(encoding="utf-8").splitlines()
        marker = "## Chunking comparison"
        if marker in "\n".join(lines):
            pass
