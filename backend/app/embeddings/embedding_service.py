from __future__ import annotations

import time
from typing import Iterable

import numpy as np
from sentence_transformers import SentenceTransformer


class EmbeddingService:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name, device="cpu")

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype="float32")
        embeddings = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return np.asarray(embeddings, dtype="float32")

    def embed_query(self, query: str) -> np.ndarray:
        embeddings = self.embed_texts([query])
        return embeddings[0].astype("float32")

    def embed_many(self, texts: Iterable[str]) -> np.ndarray:
        return self.embed_texts(list(texts))
