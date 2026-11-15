"""Application settings, read from environment variables and the .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> parents[2] is the repository root
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    app_name: str = "Travel Assistant"
    database_url: str = "postgresql+psycopg://travel:travel@localhost:5432/travel"
    test_database_url: str = "postgresql+psycopg://travel:travel@localhost:5432/travel_test"
    qdrant_url: str = "http://localhost:6333"
    llm_provider: str = "anthropic"
    llm_api_key: SecretStr = SecretStr("")
    jwt_secret: SecretStr = SecretStr("change-me")


@lru_cache
def get_settings() -> Settings:
    """Return the settings, loaded once and then reused."""
    return Settings()