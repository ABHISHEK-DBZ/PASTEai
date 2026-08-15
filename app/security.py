"""Optional API-key authentication for PASTE.

When `PASTE_API_KEY` is set, every request to protected routers must include
`Authorization: Bearer <key>` or `X-API-Key: <key>`. When unset (local dev),
auth is disabled and the dependency simply passes through.
"""
from __future__ import annotations

import hmac
import logging

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

logger = logging.getLogger("paste.security")

_bearer = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

_WARNED = False


def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    x_api_key: str | None = Security(_api_key_header),
) -> str | None:
    global _WARNED
    if not settings.api_key:
        if not _WARNED:
            logger.warning(
                "PASTE_API_KEY is not set - API authentication is DISABLED. "
                "Set it before exposing this service publicly."
            )
            _WARNED = True
        return None

    candidate = credentials.credentials if credentials else (x_api_key or None)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Send `Authorization: Bearer <key>` or `X-API-Key: <key>`.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not hmac.compare_digest(candidate, settings.api_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return candidate