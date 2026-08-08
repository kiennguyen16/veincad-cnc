from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Response, status

from app.config import Settings, get_settings
from app.database import Database, verify_password


def get_db() -> Database:
    settings = get_settings()
    assert settings.database_path is not None
    return Database(settings.database_path)


def public_user(user: dict) -> dict[str, str]:
    return {"id": str(user["id"]), "email": str(user["email"]), "role": str(user["role"])}


def authenticate_user(db: Database, email: str, password: str) -> dict | None:
    user = db.get_user_by_email(email)
    if user is None:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


def set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=settings.session_days * 24 * 60 * 60,
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(key=settings.auth_cookie_name, path="/")


def current_user(
    token: Annotated[str | None, Cookie(alias="veincad_session")] = None,
    db: Annotated[Database, Depends(get_db)] = None,
) -> dict:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required.")
    user = db.get_user_for_session(token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired.")
    return user
