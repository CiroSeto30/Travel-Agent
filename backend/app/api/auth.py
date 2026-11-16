"""Registration, login, logout and the current user."""

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import COOKIE_NAME, CurrentUser, DbSession
from app.auth.security import TOKEN_LIFETIME, create_access_token, hash_password, verify_password
from app.config import get_settings
from app.db.models import Airport, User
from app.schemas.auth import LoginIn, RegisterIn, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _start_session(response: Response, user_id: int) -> None:
    response.set_cookie(
        COOKIE_NAME,
        create_access_token(user_id),
        max_age=int(TOKEN_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, db: DbSession, response: Response) -> UserOut:
    airport = db.get(Airport, data.home_airport)
    if airport is None or not airport.is_departure:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown departure airport")
    user = User(email=data.email, password_hash=hash_password(data.password), first_name=data.first_name,
                last_name=data.last_name, home_airport=data.home_airport)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    _start_session(response, user.id)
    return user


@router.post("/login")
def login(data: LoginIn, db: DbSession, response: Response) -> UserOut:
    user = db.scalar(select(User).where(User.email == data.email))
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    _start_session(response, user.id)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return user