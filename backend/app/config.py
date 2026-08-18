import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = "voice-rag"
    app_version: str = "0.1.0"
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    backend_host: str = os.getenv("HOST", "0.0.0.0")
    backend_port: int = int(os.getenv("PORT", "8000"))
    sarvam_api_key: str = os.getenv("SARVAM_API_KEY", "")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    allowed_origins: list[str] = None

    def __post_init__(self):
        object.__setattr__(
            self,
            "allowed_origins",
            [self.frontend_url, "http://localhost:5173", "http://127.0.0.1:5173"],
        )


settings = Settings()
