import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import jwt
from fastapi import Response

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.api import auth as auth_api
from app.config import settings
from app.repositories.user_repository import UserRepository
from app.services.auth_service import create_access_token, get_current_user
from app.services.auth_session import AuthSession
from app.services.request_security import is_csrf_token_valid, is_origin_allowed


class NoopRateLimiter:
    def enforce(self, *_args, **_kwargs):
        return None


class FakeAuthSessions:
    def __init__(self):
        self.revoked = []
        self.revoked_all = []

    def create(self, username):
        return AuthSession("session-1", username, "refresh-token-1")

    def rotate(self, refresh_token):
        if refresh_token != "refresh-token-1":
            return None
        return AuthSession("session-1", "cookie-user", "refresh-token-2")

    def exists(self, session_id):
        return session_id == "session-1"

    def revoke(self, refresh_token=None, session_id=None):
        self.revoked.append((refresh_token, session_id))

    def revoke_all(self, username):
        self.revoked_all.append(username)


def request_from(ip="127.0.0.1"):
    return SimpleNamespace(headers={}, client=SimpleNamespace(host=ip))


def test_login_sets_short_access_and_refresh_cookies(monkeypatch):
    user = SimpleNamespace(id=7, username="cookie-user", role="user")
    form = SimpleNamespace(username="cookie-user", password="correct-password")
    response = Response()

    monkeypatch.setattr(auth_api, "authenticate_user", lambda *_: user)

    result = auth_api.login(
        request=request_from(),
        response=response,
        form_data=form,
        db=None,
        auth_sessions=FakeAuthSessions(),
        rate_limiter=NoopRateLimiter(),
    )

    assert result is user
    set_cookie_headers = response.headers.getlist("set-cookie")
    auth_cookie = next(
        header for header in set_cookie_headers
        if header.startswith(f"{settings.AUTH_COOKIE_NAME}=")
    )
    refresh_cookie = next(
        header for header in set_cookie_headers
        if header.startswith(f"{settings.AUTH_REFRESH_COOKIE_NAME}=")
    )

    assert "HttpOnly" in auth_cookie
    assert f"Max-Age={settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60}" in auth_cookie
    assert "refresh-token-1" in refresh_cookie
    assert f"Max-Age={settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400}" in refresh_cookie
    assert response.headers["X-CSRF-Token"]


def test_refresh_rotates_token_and_returns_user(monkeypatch):
    expected_user = SimpleNamespace(id=8, username="cookie-user", role="user")
    response = Response()
    monkeypatch.setattr(UserRepository, "get_by_username", lambda *_: expected_user)

    result = auth_api.refresh(
        response=response,
        refresh_token="refresh-token-1",
        db=None,
        auth_sessions=FakeAuthSessions(),
    )

    assert result is expected_user
    assert any(
        header.startswith(f"{settings.AUTH_REFRESH_COOKIE_NAME}=refresh-token-2")
        for header in response.headers.getlist("set-cookie")
    )


def test_logout_revokes_refresh_and_expires_all_cookies():
    response = Response()
    sessions = FakeAuthSessions()

    auth_api.logout(
        response=response,
        refresh_token="refresh-token-1",
        auth_sessions=sessions,
    )

    assert sessions.revoked == [("refresh-token-1", None)]
    set_cookie_headers = response.headers.getlist("set-cookie")
    for cookie_name in (
        settings.AUTH_COOKIE_NAME,
        settings.AUTH_REFRESH_COOKIE_NAME,
        settings.AUTH_CSRF_COOKIE_NAME,
    ):
        assert any(
            header.startswith(f"{cookie_name}=") and "Max-Age=0" in header
            for header in set_cookie_headers
        )


def test_access_token_is_short_lived_and_session_backed(monkeypatch):
    expected_user = SimpleNamespace(id=8, username="cookie-user", role="user")
    token = create_access_token({
        "sub": expected_user.username,
        "sid": "session-1",
        "type": "access",
    })
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    lifetime = payload["exp"] - int(datetime.now(timezone.utc).timestamp())
    assert 0 < lifetime <= settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    monkeypatch.setattr(UserRepository, "get_by_username", lambda *_: expected_user)
    assert get_current_user(
        token=token,
        db=None,
        auth_sessions=FakeAuthSessions(),
    ) is expected_user


def test_origin_and_csrf_validation():
    allowed_origins = {"https://legal.example.com"}

    assert is_origin_allowed("https://legal.example.com", allowed_origins)
    assert is_origin_allowed(None, allowed_origins)
    assert not is_origin_allowed("https://attacker.example.com", allowed_origins)

    assert is_csrf_token_valid("same-token", "same-token")
    assert not is_csrf_token_valid("cookie-token", "header-token")
    assert not is_csrf_token_valid(None, "header-token")
