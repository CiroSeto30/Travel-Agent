"""Database connection: one engine for the app, and a factory for sessions."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

engine = create_engine(get_settings().database_url)

SessionLocal = sessionmaker(bind=engine)

def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, closed when the request ends."""
    with SessionLocal() as session:
        yield session