from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.models import Chunk


class IndexStore:
    def __init__(self, index_dir: str = "data/index"):
        self.index_dir = Path(index_dir)
        self.chunks: list[Chunk] = []
        self.embeddings: np.ndarray | None = None
        self.metadata: dict = {}
        self._load()

    def _load(self):
        chunks_path = self.index_dir / "chunks.json"
        embeddings_path = self.index_dir / "embeddings.npy"
        if not chunks_path.exists() or not embeddings_path.exists():
            self.chunks = []
            self.embeddings = np.empty((0, 384), dtype="float32")
            self.metadata = {"count": 0}
            return
        with open(chunks_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self.chunks = [Chunk(**x) for x in raw]
        self.embeddings = np.load(embeddings_path).astype("float32")
        meta_path = self.index_dir / "index_meta.json"
        if meta_path.exists():
            self.metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    def chunk_texts(self) -> list[str]:
        return [chunk.text for chunk in self.chunks]

    def get_chunk_by_id(self, chunk_id: str) -> Chunk | None:
        for chunk in self.chunks:
            if chunk.id == chunk_id:
                return chunk
        return None
