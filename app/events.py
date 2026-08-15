"""Realtime event bus for PASTE.

Publishes structured events (product status changes, queue updates, field
reviews) to a single Redis channel so the API process, the RQ worker, and any
SSE clients all stay in sync. When Redis is unavailable the bus degrades to an
in-process fan-out so the app still behaves in realtime in single-process dev.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import deque
from typing import AsyncGenerator

import redis
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.config import settings

logger = logging.getLogger("paste.events")

router = APIRouter(prefix="/api/v1", tags=["realtime"])

CHANNEL = "paste:events"
KEEPALIVE_SECONDS = 15.0

# --- In-process fan-out (works even without Redis) -------------------------
_local_buffer: deque[dict] = deque(maxlen=500)
_subscribers: set[asyncio.Queue] = set()

# Single lazily-created Redis client (redis-py manages its own connection pool,
# so a shared client avoids opening a fresh TCP connection on every publish).
_shared_conn: redis.Redis | None = None
_conn_lock = threading.Lock()


def _redis_conn() -> redis.Redis | None:
    global _shared_conn
    if _shared_conn is None:
        with _conn_lock:
            if _shared_conn is None:
                try:
                    _shared_conn = redis.from_url(settings.redis_url, socket_connect_timeout=1)
                except Exception:
                    return None
    return _shared_conn


def publish(event_type: str, payload: dict) -> None:
    """Publish an event. Best-effort: never raises, never blocks the caller."""
    event = {
        "type": event_type,
        "payload": payload,
        "ts": time.time(),
    }
    _local_buffer.append(event)
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass

    try:
        conn = _redis_conn()
        if conn is not None:
            conn.publish(CHANNEL, json.dumps(event))
    except Exception as exc:  # pragma: no cover - redis optional at runtime
        logger.debug("redis publish failed (realtime degraded to in-process): %s", exc)


# --- SSE endpoint ----------------------------------------------------------
def _format_sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _redis_relay_thread(
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue,
    stop: threading.Event,
) -> None:
    """Drain the Redis channel into the client's asyncio queue (cross-process).

    Uses a dedicated pubsub connection (a Redis pubsub subscription holds the
    connection open, so it must not share the pooled client).
    """
    try:
        conn = redis.from_url(settings.redis_url, socket_connect_timeout=1)
        ps = conn.pubsub()
        ps.subscribe(CHANNEL)
        while not stop.is_set():
            msg = ps.get_message(timeout=0.5)
            if msg and msg.get("type") == "message":
                try:
                    evt = json.loads(msg["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, evt)
                except Exception:
                    pass
        ps.unsubscribe()
        conn.close()
    except Exception as exc:  # pragma: no cover
        logger.debug("sse redis relay ended: %s", exc)


@router.get("/events")
async def events() -> StreamingResponse:
    """Server-Sent Events stream of PASTE realtime events."""

    async def gen() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        _subscribers.add(queue)
        loop = asyncio.get_running_loop()
        stop = threading.Event()
        relay = threading.Thread(
            target=_redis_relay_thread,
            args=(loop, queue, stop),
            daemon=True,
        )
        relay.start()

        # Replay a short history so a freshly-opened client isn't blind.
        for evt in list(_local_buffer)[-20:]:
            yield _format_sse(evt)

        yield _format_sse({"type": "hello", "payload": {"message": "connected"}, "ts": time.time()})

        try:
            while True:
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                    yield _format_sse(evt)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            stop.set()
            _subscribers.discard(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
