from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class STTResult:
    transcript: str
    raw_transcript: str
    confidence: float
    latency_ms: float


class SarvamSTTClient:
    def __init__(self, api_key: str | None = None, websocket_url: str = "wss://api.sarvam.ai/ws"):
        self.api_key = api_key or ""
        self.websocket_url = websocket_url

    async def transcribe(self, audio_b64: str, mode: str = "transcribe") -> STTResult:
        start = time.perf_counter()
        await asyncio.sleep(0.05)
        transcript = "This is a placeholder transcript from the integration stub. Replace with live Sarvam WebSocket calls when credentials are configured."
        latency_ms = (time.perf_counter() - start) * 1000.0
        return STTResult(transcript=transcript, raw_transcript=transcript, confidence=0.88, latency_ms=latency_ms)
