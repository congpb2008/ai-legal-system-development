from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.paths import resource_dir, writable_dir

BASE_DIR = writable_dir()
RESOURCE_DIR = resource_dir()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(BASE_DIR / ".env") if (BASE_DIR / ".env").exists() else str(RESOURCE_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Banking Legal Assistant"
    environment: str = "development"
    debug: bool = True

    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'legal.db'}"
    data_dir: Path = BASE_DIR / "data"
    secret_key: str = "change-me-in-production"
    session_cookie: str = "legal_session"
    session_ttl_seconds: int = 60 * 60 * 12

    admin_email: str = "admin@example.com"
    admin_password: str = "admin123"

    max_upload_mb: int = 200

    # OpenAI-compatible chat endpoint, e.g. https://api.example.com/v1
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 300

    # OpenAI-compatible embeddings endpoint. If empty, use local hash embeddings.
    embedding_provider: str = "hash"  # hash | openai
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 384

    ocr_provider: str = "auto"  # auto | paddle | tesseract | none
    ocr_lang: str = "vi"
    ocr_dpi: int = 220
    ocr_min_text_chars: int = 40

    run_worker_inprocess: bool = True
    worker_poll_seconds: float = 1.0

    cors_origins: str = "http://localhost:5173,http://localhost:8000,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def pages_dir(self) -> Path:
        return self.data_dir / "pages"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.pages_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
