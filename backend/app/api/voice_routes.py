from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models import QueryRequest
from app.pipeline import VoiceRAGPipeline

router = APIRouter()
pipeline = VoiceRAGPipeline(index_dir="data/index")


@router.post("/voice")
async def answer_voice_query(payload: QueryRequest):
    if not payload.query and not payload.audio_b64:
        raise HTTPException(status_code=400, detail="Either query text or audio payload is required.")
    if payload.query:
        data = pipeline.process(payload.query)
    else:
        data = pipeline.process("placeholder transcript from audio")
    return data
