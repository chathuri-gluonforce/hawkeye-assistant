from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

DATA_DIR = PROJECT_ROOT / "data"
TRAIN_FILE = DATA_DIR / "train.json"
TEST_FILE = DATA_DIR / "test.json"
DEMO_FILE = DATA_DIR / "demo.json"

STORAGE_DIR = PROJECT_ROOT / "storage"
MEMORY_DB_DIR = STORAGE_DIR / "memory_db"
RESULTS_FILE = STORAGE_DIR / "results.json"

STORAGE_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """Application settings loaded from environment and optional `.env` file."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: SecretStr
    openrouter_model: str = Field(
        default="openai/gpt-4o-mini",
        description="OpenRouter model id (see https://openrouter.ai/models)",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenAI-compatible API base URL",
    )

    hawkeye_base_url: str = Field(
        default="http://127.0.0.1:8003",
        description="Base URL of the Hawkeye backend (source of truth for auth)",
    )
    hawkeye_api_prefix: str = Field(
        default="",
        description="Optional path prefix for Hawkeye routes, e.g. /api/v1",
    )
    hawkeye_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        le=120,
        description="Timeout for requests to the Hawkeye backend",
    )
    assistant_session_hours: float = Field(default=8.0, gt=0, le=168)

    @field_validator("openrouter_model", "openrouter_base_url", mode="before")
    @classmethod
    def strip_strings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("hawkeye_base_url", "hawkeye_api_prefix", mode="before")
    @classmethod
    def strip_hawkeye_strings(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("hawkeye_base_url")
    @classmethod
    def check_hawkeye_base_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("HAWKEYE_BASE_URL must start with http:// or https://")
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — re-read env only after process restart."""
    return Settings()
