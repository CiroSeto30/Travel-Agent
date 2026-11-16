"""Dependencies shared by the API routes: the database session and the logged-in user."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.security import read_access_token
from app.db.models import User
from app.db.session import get_db

COOKIE_NAME = "access_token"

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(db: DbSession, access_token: Annotated[str | None, Cookie()] = None) -> User:
    user_id = read_access_token(access_token) if access_token else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]