from __future__ import annotations

import math
from typing import Any

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

from app.models import Chunk, RetrievalCandidate
from app.utils import simple_tokenize


class HybridRetriever:
    def __init__(self, chunks: list[Chunk], embeddings: np.ndarray):
        self.chunks = chunks
        self.embeddings = embeddings.astype("float32")
        self.index = self._build_faiss_index(self.embeddings)
        self.bm25 = self._build_bm25(chunks)

    def _build_faiss_index(self, embeddings: np.ndarray) -> faiss.Index:
        if not embeddings.size:
            return faiss.IndexFlatIP(384)
        vectors = embeddings.copy().astype("float32")
        # Flat exhaustive search keeps retrieval latency low and deterministic for the target 2k-5k chunk working set.
        index = faiss.IndexFlatIP(vectors.shape[1])
        faiss.normalize_L2(vectors)
        index.add(vectors)
        return index

    def _build_bm25(self, chunks: list[Chunk]) -> BM25Okapi:
        tokenized = [simple_tokenize(chunk.text) for chunk in chunks]
        return BM25Okapi(tokenized)

    def dense_search(self, query_vector: np.ndarray, top_k: int = 10) -> list[tuple[int, float]]:
        if self.embeddings.size == 0:
            return []
        query = query_vector.astype("float32").reshape(1, -1)
        faiss.normalize_L2(query)
        scores, indices = self.index.search(query, min(top_k, self.embeddings.shape[0]))
        pairs = []
        for idx, score in zip(indices[0], scores[0]):
            if idx < 0:
                continue
            pairs.append((int(idx), float(score)))
        return pairs

    def sparse_search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        tokens = simple_tokenize(query)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [(idx, float(score)) for idx, score in ranked]

    def merge_results(self, dense: list[tuple[int, float]], sparse: list[tuple[int, float]], top_k: int = 5) -> list[RetrievalCandidate]:
        dense_map = {idx: score for idx, score in dense}
        sparse_map = {idx: score for idx, score in sparse}
        all_idx = sorted(set(dense_map) | set(sparse_map))
        results: list[RetrievalCandidate] = []
        for idx in all_idx:
            dense_score = dense_map.get(idx, 0.0)
            sparse_score = sparse_map.get(idx, 0.0)
            dense_norm = self._normalize(dense_score, dense_map.values())
            sparse_norm = self._normalize(sparse_score, sparse_map.values())
            merged_score = 0.7 * dense_norm + 0.3 * sparse_norm
            chunk = self.chunks[idx]
            results.append(RetrievalCandidate(chunk=chunk, dense_score=dense_score, sparse_score=sparse_score, merged_score=merged_score))
        results.sort(key=lambda r: r.merged_score, reverse=True)
        return results[:top_k]

    def _normalize(self, value: float, values: Any) -> float:
        values = list(values)
        if not values or max(values) == min(values):
            return 0.0
        return (value - min(values)) / (max(values) - min(values) + 1e-9)

    def search(self, query: str, query_vector: np.ndarray, top_k: int = 5) -> list[RetrievalCandidate]:
        dense = self.dense_search(query_vector, top_k=10)
        sparse = self.sparse_search(query, top_k=10)
        return self.merge_results(dense, sparse, top_k=top_k)
