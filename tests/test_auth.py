"""Auth + CSRF tests (issue #5).

Auth is gated on WEBUI_PASSWORD. When unset the middleware is a no-op — the
existing test_routes.py suite already exercises that path. This module covers
the password-set path: login flow, redirects, CSRF enforcement, and the
allowlist for unauthenticated endpoints.
"""
from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WEBUI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBUI_NO_RESTART", "1")
    monkeypatch.setenv("WEBUI_PASSWORD", "hunter2")
    monkeypatch.setenv("WEBUI_SESSION_SECRET", "test-secret-not-for-prod")
    (tmp_path / "config.json").write_text(json.dumps({"devices": []}))

    from app import settings as settings_mod
    importlib.reload(settings_mod)
    from app import auth as auth_mod
    importlib.reload(auth_mod)
    from app import main as main_mod
    importlib.reload(main_mod)
    return main_mod.app, tmp_path


def _csrf_from_login_page(client: TestClient) -> str:
    """The login page issues a session cookie + renders its CSRF token in a
    hidden ``_csrf`` input. Pull it out so the POST /login can be CSRF-valid."""
    r = client.get("/login")
    assert r.status_code == 200
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', r.text)
    assert m, "login form must expose a CSRF token"
    return m.group(1)


def _login(client: TestClient, password: str = "hunter2") -> None:
    csrf = _csrf_from_login_page(client)
    r = client.post(
        "/login",
        data={"_csrf": csrf, "password": password, "next": "/"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/"


def test_unauth_redirects_to_login(app_with_auth) -> None:
    app, _ = app_with_auth
    client = TestClient(app)
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_unauth_htmx_returns_401_with_hx_redirect(app_with_auth) -> None:
    """htmx requests want a 401 + HX-Redirect header, not an HTML redirect."""
    app, _ = app_with_auth
    client = TestClient(app)
    r = client.get("/", headers={"HX-Request": "true"}, follow_redirects=False)
    assert r.status_code == 401
    assert r.headers["HX-Redirect"].startswith("/login")


def test_login_wrong_password_401(app_with_auth) -> None:
    app, _ = app_with_auth
    client = TestClient(app)
    csrf = _csrf_from_login_page(client)
    r = client.post(
        "/login",
        data={"_csrf": csrf, "password": "wrong", "next": "/"},
        follow_redirects=False,
    )
    assert r.status_code == 401


def test_login_correct_password_redirects_and_authorizes(app_with_auth) -> None:
    app, _ = app_with_auth
    client = TestClient(app)
    _login(client)
    r = client.get("/")
    assert r.status_code == 200
    assert "Configuration" in r.text


def test_healthz_open_when_auth_enabled(app_with_auth) -> None:
    app, _ = app_with_auth
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_static_open_when_auth_enabled(app_with_auth) -> None:
    app, _ = app_with_auth
    client = TestClient(app)
    r = client.get("/static/app.css")
    assert r.status_code == 200


def test_csrf_blocks_post_without_token(app_with_auth) -> None:
    app, _ = app_with_auth
    client = TestClient(app)
    _login(client)
    r = client.post("/save", data={"join_name": "x"})
    assert r.status_code == 403


def test_csrf_accepts_post_with_header_token(app_with_auth) -> None:
    app, _ = app_with_auth
    client = TestClient(app)
    _login(client)
    # Pull the CSRF from the rendered config page meta tag.
    body = client.get("/").text
    m = re.search(r'name="csrf-token"\s+content="([^"]+)"', body)
    assert m, "config page must expose a CSRF meta tag"
    token = m.group(1)
    r = client.post(
        "/save",
        data={"join_name": "Test"},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 200, r.text


def test_logout_clears_session(app_with_auth) -> None:
    app, _ = app_with_auth
    client = TestClient(app)
    _login(client)
    r = client.post("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
    # Subsequent request should redirect to login.
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303


def test_login_next_open_redirect_blocked(app_with_auth) -> None:
    """`next=//evil.com` must not redirect off-origin."""
    app, _ = app_with_auth
    client = TestClient(app)
    csrf = _csrf_from_login_page(client)
    r = client.post(
        "/login",
        data={"_csrf": csrf, "password": "hunter2", "next": "//evil.com/path"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_auth_disabled_when_password_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No password → auth is off entirely; / serves directly with no redirect."""
    monkeypatch.setenv("WEBUI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBUI_NO_RESTART", "1")
    monkeypatch.delenv("WEBUI_PASSWORD", raising=False)
    from app import settings as settings_mod
    importlib.reload(settings_mod)
    from app import auth as auth_mod
    importlib.reload(auth_mod)
    from app import main as main_mod
    importlib.reload(main_mod)
    client = TestClient(main_mod.app)
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 200
