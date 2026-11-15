import pytest
from sqlalchemy import text

from tests.conftest import check_test_database

def test_database_answer(db_session):
    assert db_session.execute(text("SELECT 1")).scalar()==1

def test_tests_use_the_test_database(db_session):
    name = db_session.execute(text("SELECT current_database()")).scalar()
    assert name == "travel_test"

def test_refuses_to_run_on_the_app_database():
    app_url = "postgresql+psycopg://travel:travel@localhost:5432/travel"
    with pytest.raises(RuntimeError, match="travel"):
        check_test_database(app_url, app_url)

def test_accepts_a_separate_test_database():
    check_test_database("postgresql+psycopg://travel:travel@localhost:5432/travel_test",
        "postgresql+psycopg://travel:travel@localhost:5432/travel")