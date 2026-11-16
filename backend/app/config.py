"""Application settings, read from environment variables and the .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> parents[2] is the repository root
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    app_name: str = "Travel Assistant"
    database_url: str = "postgresql+psycopg://travel:travel@localhost:5432/travel"
    test_database_url: str = "postgresql+psycopg://travel:travel@localhost:5432/travel_test"
    qdrant_url: str = "http://localhost:6333"
    llm_provider: str = "google_genai"
    llm_model: str = "gemini-3.5-flash-lite"
    llm_api_key: SecretStr = SecretStr("")
    # signs the login tokens: required, at least 32 characters (HS256 needs a 256-bit key)
    jwt_secret: SecretStr = Field(min_length=32)
    # send the login cookie over HTTPS only; keep False for http://localhost
    cookie_secure: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return the settings, loaded once and then reused."""
    return Settings()