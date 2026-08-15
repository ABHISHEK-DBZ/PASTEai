from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import close_db, init_db
from app.events import router as events_router
from app.routes import router as api_router
from app.review_routes import router as review_router
from app.security import require_api_key


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("paste")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting PASTE API...")
    if not settings.secret_key:
        logger.warning("SECRET_KEY is not set - generate a strong random one before deploying.")
    if "*" in settings.cors_origins:
        logger.warning("CORS_ORIGINS includes '*' - this allows any origin to call the API. Restrict it before production.")
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as exc:
        logger.warning("Database initialization deferred or unavailable: %s", exc)
    logger.info("PASTE API ready - lifespan yield")
    try:
        yield
    finally:
        # Shutdown
        logger.info("Shutting down PASTE API...")
        await close_db()
        logger.info("Database connections closed")


app = FastAPI(
    title="PASTE - Product Intelligence Engine",
    description="AI-powered product intelligence for industrial commerce. Extract, validate, and export structured product data with provable confidence.",
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS - restrict to your frontend origins in production (CORS_ORIGINS env var).
# Credentials are only allowed when origins are explicit (never with wildcard).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials="*" not in settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API + review routers are protected by optional API-key auth (PASTE_API_KEY).
app.include_router(api_router, dependencies=[Depends(require_api_key)])
app.include_router(review_router, dependencies=[Depends(require_api_key)])
app.include_router(events_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "paste-api"}


@app.get("/api/info", tags=["meta"])
async def root():
    return {
        "name": "PASTE",
        "version": "1.1.0",
        "description": "AI-Powered Product Intelligence Engine",
        "docs": "/docs",
        "health": "/health",
        "realtime": "/api/v1/events",
        "dashboard": "/dashboard",
    }


# The dashboard's "Run Acme X-100 Demo Ingest" button fetches this file. Serve it
# from the repo root (must be registered before the catch-all static mounts).
@app.get("/sample_datasheet.pdf", include_in_schema=False)
async def sample_datasheet() -> FileResponse:
    sample = Path(__file__).resolve().parent.parent / "sample_datasheet.pdf"
    if not sample.exists():
        raise HTTPException(status_code=404, detail="sample_datasheet.pdf not found")
    return FileResponse(str(sample))


# Serve the review dashboard (must be registered last so API routes win).
_dashboard = Path(__file__).resolve().parent.parent / "frontend"
if _dashboard.exists():
    _index = _dashboard / "index.html"

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard_index() -> FileResponse:
        # StaticFiles(html=True) 404s on the bare mount path (no trailing slash).
        return FileResponse(str(_index))

    app.mount(
        "/dashboard",
        StaticFiles(directory=str(_dashboard), html=True),
        name="dashboard",
    )
    app.mount("/", StaticFiles(directory=str(_dashboard), html=True), name="frontend")
    logger.info("Serving dashboard from %s", _dashboard)
