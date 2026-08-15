from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://paste:***REMOVED***@localhost:5432/paste",
        validation_alias="DATABASE_URL",
    )

    # VLM (llama.cpp)
    vlm_model_path: str = Field(default="/models/qwen2-vl-7b-instruct-q4_k_m.gguf", validation_alias="VLM_MODEL_PATH")
    vlm_n_ctx: int = Field(default=8192, validation_alias="VLM_N_CTX")
    vlm_n_gpu_layers: int = Field(default=-1, validation_alias="VLM_N_GPU_LAYERS")
    vlm_temperature: float = Field(default=0.1, validation_alias="VLM_TEMPERATURE")
    vlm_top_p: float = Field(default=0.95, validation_alias="VLM_TOP_P")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")

    # Security
    secret_key: str = Field(default="***REMOVED***", validation_alias="SECRET_KEY")
    api_key_hash_salt: str = Field(default="***REMOVED***", validation_alias="API_KEY_HASH_SALT")
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=60, validation_alias="JWT_EXPIRE_MINUTES")
    # Optional API key. When set, every API call must send `Authorization: Bearer <key>`
    # or `X-API-Key: <key>`. When unset (dev), auth is disabled with a startup warning.
    api_key: str | None = Field(default=None, validation_alias="PASTE_API_KEY")

    # API
    api_host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    api_port: int = Field(default=8000, validation_alias="API_PORT")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    # Processing
    max_concurrent_jobs: int = Field(default=2, validation_alias="MAX_CONCURRENT_JOBS")
    extraction_pass_count: int = Field(default=2, validation_alias="EXTRACTION_PASS_COUNT")
    confidence_auto_approve: float = Field(default=0.90, validation_alias="CONFIDENCE_AUTO_APPROVE")
    confidence_inferred_cap: float = Field(default=0.70, validation_alias="CONFIDENCE_INFERRED_CAP")
    confidence_forced_review: float = Field(default=0.50, validation_alias="CONFIDENCE_FORCED_REVIEW")

    # File uploads
    upload_dir: Path = Field(default=Path("/uploads"), validation_alias="UPLOAD_DIR")
    max_file_size_mb: int = Field(default=50, validation_alias="MAX_FILE_SIZE_MB")
    allowed_extensions: set[str] = Field(default={"pdf", "png", "jpg", "jpeg", "tiff"}, validation_alias="ALLOWED_EXTENSIONS")

    # CORS - restrict to your frontend origins in production (comma-separated).
    cors_origins: list[str] = Field(default=["*"], validation_alias="CORS_ORIGINS")

    # Export
    export_dir: Path = Field(default=Path("/exports"), validation_alias="EXPORT_DIR")

    @field_validator("allowed_extensions", mode="before")
    @classmethod
    def _split_allowed_extensions(cls, v: Any) -> Any:
        if isinstance(v, str):
            return {s.strip().lower() for s in v.split(",") if s.strip()}
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()