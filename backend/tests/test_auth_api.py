from app.db.models import User

NEW_USER = {"email": "Ciro@Example.com", "password": "correct horse", "first_name": "Ciro", "last_name": "Setolino"}


def register(client, **changes):
    return client.post("/api/auth/register", json={**NEW_USER, **changes})


def test_register_creates_the_user_and_logs_in(client):
    r = register(client)
    assert r.status_code == 201
    assert r.json()["email"] == "ciro@example.com"
    assert "password" not in r.text and "password_hash" not in r.text
    assert client.get("/api/auth/me").json()["first_name"] == "Ciro"


def test_password_is_stored_hashed(client, db_session):
    register(client)
    user = db_session.query(User).one()
    assert user.password_hash != NEW_USER["password"]


def test_session_cookie_is_http_only(client):
    cookie = register(client).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_same_email_twice_is_rejected(client):
    register(client)
    assert register(client, email="ciro@example.com").status_code == 409


def test_short_password_is_rejected(client):
    assert register(client, password="short").status_code == 422


def test_login_and_logout(client):
    register(client)
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401

    r = client.post("/api/auth/login", json={"email": "ciro@example.com", "password": "correct horse"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 200

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_wrong_password_is_rejected(client):
    register(client)
    r = client.post("/api/auth/login", json={"email": "ciro@example.com", "password": "wrong horse"})
    assert r.status_code == 401


def test_invalid_cookie_is_rejected(client):
    client.cookies.set("access_token", "not-a-token")
    assert client.get("/api/auth/me").status_code == 401


def test_departure_airport_is_not_part_of_the_account(client):
    assert "home_airport" not in register(client).json()