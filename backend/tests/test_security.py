from datetime import UTC, datetime, timedelta

import jwt

from app.auth.security import create_access_token, hash_password, read_access_token, verify_password


def test_password_hash_verifies_only_the_right_password():
    stored = hash_password("correct horse")
    assert stored != "correct horse"
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong horse", stored)


def test_same_password_gives_different_hashes():
    assert hash_password("correct horse") != hash_password("correct horse")


def test_token_carries_the_user_id():
    assert read_access_token(create_access_token(42)) == 42


def test_expired_token_is_rejected():
    yesterday = datetime.now(UTC) - timedelta(hours=25)
    assert read_access_token(create_access_token(42, now=yesterday)) is None


def test_token_signed_with_another_secret_is_rejected():
    forged = jwt.encode({"sub": "42", "exp": datetime.now(UTC) + timedelta(hours=1)},
                        "a-different-secret-that-is-long-enough", algorithm="HS256")
    assert read_access_token(forged) is None


def test_garbage_token_is_rejected():
    assert read_access_token("not-a-token") is None