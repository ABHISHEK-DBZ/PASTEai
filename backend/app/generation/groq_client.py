from __future__ import annotations

import os
import time

import requests


class GroqClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"

    def generate(self, query: str, context_chunks: list[str], model: str | None = None) -> dict:
        model_name = model or "llama-3.1-8b-instant"
        context = "\n\n".join(f"[Chunk {i + 1}] {chunk}" for i, chunk in enumerate(context_chunks))
        system_prompt = (
            "You answer only using the provided context. "
            "If the answer is not contained in the context, say explicitly that the context does not provide enough information. "
            "Do not guess. Cite the relevant chunk IDs in the output when possible."
        )
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Question: {query}\n\nContext:\n{context}"},
            ],
            "temperature": 0.1,
            "max_tokens": 250,
        }
        start = time.perf_counter()
        if not self.api_key:
            return {
                "answer": "This environment is missing GROQ_API_KEY. Configure it to enable generation.",
                "cited_chunk_ids": [],
                "raw_model_output": "stubbed output",
                "latency_ms": (time.perf_counter() - start) * 1000.0,
            }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        resp = requests.post(self.base_url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        latency_ms = (time.perf_counter() - start) * 1000.0
        return {"answer": content, "cited_chunk_ids": [], "raw_model_output": content, "latency_ms": latency_ms}
