"""Shared test fixtures: a dedicated test database and an isolated session per test."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from datetime import date


from app.config import get_settings
import app.db.models # noqa: F401  (registers every model on Base.metadata)
from app.db.base import Base

from seed.build_catalog import build_catalog
from seed.load_db import DATA_DIR, load_catalog
from seed.schema import BaseData, load_base_data

TODAY = date(2027, 3, 31)  # the planner tests' catalog covers April and the first half of May

def check_test_database(test_url: str, app_url: str) -> None:
    """The fixtures drop every table: refuse to run them against the app's own database."""
    test_db, app_db = make_url(test_url).database, make_url(app_url).database
    if test_db == app_db:
        raise RuntimeError(f"TEST_DATABASE_URL points to '{test_db}', the same database as DATABASE_URL. "
            "Tests would delete its tables: set TEST_DATABASE_URL to a separate database.")

def _reset_schema(engine) -> None:
    """Drop everything in the test database, including tables the models no longer define."""
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

def _ensure_database_exists(url: str) -> None:
    """Create the test database if it is missing (first run on a new machine)."""
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()

@pytest.fixture(scope="session")
def test_engine():
    settings = get_settings()
    url = settings.test_database_url
    check_test_database(url, settings.database_url)
    _ensure_database_exists(url)
    engine = create_engine(url)
    _reset_schema(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()

@pytest.fixture
def db_session(test_engine):
    """A session inside a transaction that is rolled back after the test."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db_session):
    """HTTP client for the app, with every request using the test session."""
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def base_data():
    return load_base_data(DATA_DIR)


@pytest.fixture
def japan(db_session, base_data):
    """A small catalog for the planner tests: only Japan, 45 days from 1 April 2027."""
    cities = {a.city for a in base_data.airports if a.country == "Giappone"}
    base = BaseData(
        airports=[a for a in base_data.airports if a.role == "departure" or a.country == "Giappone"],
        hotels=[h for h in base_data.hotels if h.city in cities],
        activities=[a for a in base_data.activities if a.city in cities],
    )
    load_catalog(db_session, build_catalog(base, date(2027, 4, 1), days=45), base)
    return db_session