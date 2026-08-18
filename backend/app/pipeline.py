from __future__ import annotations

import time

import numpy as np

from app.embeddings.embedding_service import EmbeddingService
from app.guardrails.guardrails import GuardrailChecker
from app.generation.groq_client import GroqClient
from app.models import AnswerResponse, LatencyLog
from app.query_rewrite import QueryRewriter
from app.retrieval.hybrid_search import HybridRetriever
from app.retrieval.index_store import IndexStore
from app.utils import now_ms


class VoiceRAGPipeline:
    def __init__(self, index_dir: str = "data/index"):
        self.index_store = IndexStore(index_dir)
        self.embedding_service = EmbeddingService()
        self.query_rewriter = QueryRewriter()
        self.guardrails = GuardrailChecker()
        self.groq = GroqClient()
        self.retriever = None
        if self.index_store.embeddings is not None and self.index_store.embeddings.size:
            self.retriever = HybridRetriever(self.index_store.chunks, self.index_store.embeddings)

    def process(self, raw_query: str, top_k: int = 5) -> dict:
        started = now_ms()
        lat = LatencyLog()
        query_rewritten = self.query_rewriter.rewrite(raw_query)
        lat.query_rewrite_ms = now_ms() - started

        if self.guardrails.is_unsafe(raw_query):
            return {"answer": "I can’t help with unsafe requests.", "guardrail_message": "unsafe input", "latencies": {"query_rewrite_ms": lat.query_rewrite_ms}} 

        if not query_rewritten:
            return {"answer": "Please repeat that clearly.", "guardrail_message": "empty query", "latencies": {"query_rewrite_ms": lat.query_rewrite_ms}} 

        if self.retriever is None:
            return {"answer": "The retrieval index is not ready yet. Please build it first.", "guardrail_message": "index missing", "latencies": {"query_rewrite_ms": lat.query_rewrite_ms}} 

        embed_start = now_ms()
        query_vector = self.embedding_service.embed_query(query_rewritten)
        lat.embed_query_ms = now_ms() - embed_start

        faiss_start = now_ms()
        dense = self.retriever.dense_search(query_vector, top_k=10)
        lat.faiss_search_ms = now_ms() - faiss_start

        bm25_start = now_ms()
        sparse = self.retriever.sparse_search(query_rewritten, top_k=10)
        lat.bm25_search_ms = now_ms() - bm25_start

        merge_start = now_ms()
        candidates = self.retriever.merge_results(dense, sparse, top_k=top_k)
        lat.merge_ms = now_ms() - merge_start
        lat.retrieval_stage_total_ms = lat.embed_query_ms + lat.faiss_search_ms + lat.bm25_search_ms + lat.merge_ms

        top_score = candidates[0].merged_score if candidates else 0.0
        if self.guardrails.low_confidence(top_score):
            return {"answer": "I don't have enough information to answer that.", "guardrail_message": "below confidence threshold", "latencies": {"query_rewrite_ms": lat.query_rewrite_ms, "embed_query_ms": lat.embed_query_ms, "faiss_search_ms": lat.faiss_search_ms, "bm25_search_ms": lat.bm25_search_ms, "merge_ms": lat.merge_ms, "retrieval_stage_total_ms": lat.retrieval_stage_total_ms}} 

        context = [candidate.chunk.text for candidate in candidates]
        generation_start = now_ms()
        result = self.groq.generate(query_rewritten, context)
        lat.generation_ms = now_ms() - generation_start

        chunk_texts = {candidate.chunk.id: candidate.chunk.text for candidate in candidates}
        grounded = self.guardrails.grounded(result["answer"], result.get("cited_chunk_ids", []), chunk_texts)
        lat.total_ms = now_ms() - started

        return {
            "raw_query": raw_query,
            "rewritten_query": query_rewritten,
            "answer": result["answer"],
            "grounded": grounded,
            "guardrail_message": None if grounded else "grounding check failed",
            "sources": [{"id": cand.chunk.id, "text": cand.chunk.text, "score": round(cand.merged_score, 4)} for cand in candidates],
            "latencies": {
                "query_rewrite_ms": lat.query_rewrite_ms,
                "embed_query_ms": lat.embed_query_ms,
                "faiss_search_ms": lat.faiss_search_ms,
                "bm25_search_ms": lat.bm25_search_ms,
                "merge_ms": lat.merge_ms,
                "generation_ms": lat.generation_ms,
                "retrieval_stage_total_ms": lat.retrieval_stage_total_ms,
                "total_ms": lat.total_ms,
            },
        }
