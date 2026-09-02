from functools import lru_cache
from typing import List, Union
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application Info
    APP_NAME: str = "Secure Enterprise RAG"
    APP_ENV: str = "development"  # development, testing, production
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://rag_admin:change_this_in_production@localhost:5432/rag_enterprise_db"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10

    # Security & Tokens
    SECRET_KEY: SecretStr = SecretStr("replace-with-a-secure-random-secret-key-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Embeddings & GenAI
    GEMINI_API_KEY: Union[SecretStr, None] = None
    EMBEDDING_MODEL: str = "gemini-embedding-2"
    EMBEDDING_DIMENSIONS: int = 768
    EMBEDDING_BATCH_SIZE: int = 32

    # LLM Generation (Phase 4)
    LLM_MODEL: str = "gemini-3.7-flash"
    LLM_MAX_OUTPUT_TOKENS: int = 1024
    LLM_THINKING_BUDGET: int = 0
    RAG_MAX_CONTEXT_CHUNKS: int = 5
    RAG_MAX_CONTEXT_CHARS: int = 16000
    COST_PER_MILLION_INPUT_TOKENS: float = 0.10   # Gemini 3.7 Flash: $0.10 / 1M input tokens
    COST_PER_MILLION_OUTPUT_TOKENS: float = 0.40  # Gemini 3.7 Flash: $0.40 / 1M output tokens

    # Ingestion & Storage Limits
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB
    MAX_PDF_PAGES: int = 100
    STORAGE_LOCAL_DIR: str = ".local/storage"

    # CORS
    CORS_ORIGINS: Union[str, List[str]] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if isinstance(value, str):
            cleaned = value.strip()
            # Normalize legacy/cloud postgresql schemas (e.g. Render, Heroku) to asyncpg driver
            if cleaned.startswith("postgres://"):
                return "postgresql+asyncpg://" + cleaned[len("postgres://"):]
            elif cleaned.startswith("postgresql://"):
                return "postgresql+asyncpg://" + cleaned[len("postgresql://"):]
            return cleaned
        return value

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


@lru_cache()
def get_settings() -> Settings:
    """Cached accessor for application settings."""
    return Settings()
