from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from app.models import Chunk
from app.utils import normalize_whitespace, simple_tokenize


@dataclass
class ChunkingResult:
    strategy: str
    chunks: list[Chunk]


class SemanticChunker:
    def __init__(self, embedding_model=None, similarity_threshold: float = 0.65, max_chars: int = 500):
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold
        self.max_chars = max_chars

    def chunk(self, text: str, doc_id: str = "doc") -> list[Chunk]:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        if not sentences:
            return [Chunk(id=f"{doc_id}-0", text=text, doc_id=doc_id, position=0, language="en", strategy="semantic")]

        chunks: list[Chunk] = []
        current = []
        current_len = 0
        for index, sentence in enumerate(sentences):
            current.append(sentence)
            current_len += len(sentence)
            if current_len >= self.max_chars and index < len(sentences) - 1:
                joined = " ".join(current)
                chunks.append(Chunk(id=f"{doc_id}-{len(chunks)}", text=normalize_whitespace(joined), doc_id=doc_id, position=len(chunks), language="en", strategy="semantic"))
                current = []
                current_len = 0
        if current:
            chunks.append(Chunk(id=f"{doc_id}-{len(chunks)}", text=normalize_whitespace(" ".join(current)), doc_id=doc_id, position=len(chunks), language="en", strategy="semantic"))
        return chunks


class FixedOverlapChunker:
    def __init__(self, chunk_size: int = 250, overlap: float = 0.2):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str, doc_id: str = "doc") -> list[Chunk]:
        tokens = simple_tokenize(text)
        if not tokens:
            return [Chunk(id=f"{doc_id}-0", text=text, doc_id=doc_id, position=0, language="en", strategy="fixed")]
        step = max(1, int(self.chunk_size * (1 - self.overlap)))
        chunks: list[Chunk] = []
        for i in range(0, len(tokens), step):
            segment = tokens[i:i + self.chunk_size]
            if not segment:
                continue
            chunk_text = " ".join(segment)
            chunks.append(Chunk(id=f"{doc_id}-{len(chunks)}", text=normalize_whitespace(chunk_text), doc_id=doc_id, position=len(chunks), language="en", strategy="fixed"))
        return chunks


class MetadataAwareChunker:
    def __init__(self, chunk_size: int = 250, overlap: float = 0.2):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str, doc_id: str = "doc", language: str = "en") -> list[Chunk]:
        tokens = simple_tokenize(text)
        if not tokens:
            return [Chunk(id=f"{doc_id}-0", text=text, doc_id=doc_id, position=0, language=language, strategy="metadata", metadata={"doc_id": doc_id, "language": language})]
        step = max(1, int(self.chunk_size * (1 - self.overlap)))
        chunks = []
        for i in range(0, len(tokens), step):
            segment = tokens[i:i + self.chunk_size]
            if not segment:
                continue
            chunk_text = " ".join(segment)
            chunk = Chunk(
                id=f"{doc_id}-{len(chunks)}",
                text=normalize_whitespace(chunk_text),
                doc_id=doc_id,
                position=len(chunks),
                language=language,
                strategy="metadata",
                metadata={"doc_id": doc_id, "language": language, "start_token": i, "end_token": i + len(segment)},
            )
            chunks.append(chunk)
        return chunks


class ChunkBuilder:
    def __init__(self, strategy: str = "semantic"):
        self.strategy = strategy
        self.semantic_chunker = SemanticChunker()
        self.fixed_chunker = FixedOverlapChunker()
        self.metadata_chunker = MetadataAwareChunker()

    def build(self, text: str, doc_id: str = "doc", language: str = "en") -> list[Chunk]:
        if self.strategy == "semantic":
            return self.semantic_chunker.chunk(text, doc_id)
        if self.strategy == "fixed":
            return self.fixed_chunker.chunk(text, doc_id)
        if self.strategy == "metadata":
            return self.metadata_chunker.chunk(text, doc_id, language)
        raise ValueError(f"Unsupported strategy: {self.strategy}")


def chunk_documents(records: Iterable[dict], strategy: str = "semantic") -> list[Chunk]:
    builder = ChunkBuilder(strategy=strategy)
    chunks: list[Chunk] = []
    for record in records:
        text = record.get("text") or record.get("passage") or record.get("content") or ""
        doc_id = str(record.get("doc_id") or record.get("id") or "doc")
        language = str(record.get("language") or "en")
        chunks.extend(builder.build(text, doc_id=doc_id, language=language))
    return chunks
