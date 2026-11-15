from sqlalchemy import text

def test_database_answer(db_session):
    assert db_session.execute(text("SELECT 1")).scalar()==1

def test_tests_use_the_test_database(db_session):
    name = db_session.execute(text("SELECT current_database()")).scalar()
    assert name == "travel_test"