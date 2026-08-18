from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Chunk:
    id: str
    text: str
    doc_id: str = "unknown"
    position: int = 0
    language: str = "en"
    strategy: str = "semantic"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalCandidate:
    chunk: Chunk
    dense_score: float
    sparse_score: float
    merged_score: float


@dataclass
class LatencyLog:
    stt_ms: float = 0.0
    query_rewrite_ms: float = 0.0
    embed_query_ms: float = 0.0
    faiss_search_ms: float = 0.0
    bm25_search_ms: float = 0.0
    merge_ms: float = 0.0
    generation_ms: float = 0.0
    total_ms: float = 0.0
    retrieval_stage_total_ms: float = 0.0


@dataclass
class QueryRequest:
    query: str = ""
    audio_b64: Optional[str] = None
    mode: str = "transcribe"


@dataclass
class AnswerResponse:
    answer: str
    cited_chunk_ids: list[str]
    raw_model_output: str
    grounded: bool = True
    guardrail_message: Optional[str] = None
    sources: list[dict[str, Any]] = field(default_factory=list)
    latencies: dict[str, float] = field(default_factory=dict)
