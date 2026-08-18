from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
from datasets import load_dataset

from app.chunking import chunk_documents
from app.embeddings.embedding_service import EmbeddingService
from app.models import Chunk
from app.retrieval.hybrid_search import HybridRetriever


def _iter_subset(limit: int = 3000):
    dataset = load_dataset("ai4bharat/MSMARCO-XI", split="train[:50%]", streaming=True)
    for idx, row in enumerate(dataset):
        if idx >= limit:
            break
        passage = row.get("passage") or row.get("text") or ""
        if not passage:
            continue
        yield {
            "id": f"doc-{idx}",
            "doc_id": f"doc-{idx}",
            "text": passage,
            "language": row.get("language", "en"),
        }


def build_index(limit: int = 3000, output_dir: str = "data/index"):
    records = list(_iter_subset(limit=limit))
    chunks = chunk_documents(records, strategy="semantic")
    embeds = EmbeddingService().embed_many([chunk.text for chunk in chunks])
    retriever = HybridRetriever(chunks, embeds)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(out_dir / "embeddings.npy", embeds)
    with open(out_dir / "chunks.json", "w", encoding="utf-8") as f:
        json.dump([{"id": chunk.id, "text": chunk.text, "doc_id": chunk.doc_id, "position": chunk.position, "language": chunk.language, "strategy": chunk.strategy, "metadata": chunk.metadata} for chunk in chunks], f, ensure_ascii=False)
    with open(out_dir / "index_meta.json", "w", encoding="utf-8") as fx:
        json.dump({"count": len(chunks), "strategy": "semantic", "limit": limit}, fx)
    print(f"Built {len(chunks)} chunks from {len(records)} source docs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3000)
    parser.add_argument("--output-dir", type=str, default="data/index")
    args = parser.parse_args()
    build_index(limit=args.limit, output_dir=args.output_dir)
