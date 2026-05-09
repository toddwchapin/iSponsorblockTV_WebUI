"""Session auth + CSRF for the WebUI.

Single-admin model: one shared password from ``WEBUI_PASSWORD``. When unset,
auth is disabled (matches v1 deployment behavior, with a startup warning).

Session state lives in a signed cookie via ``starlette.middleware.sessions``.
CSRF uses the double-submit pattern: a per-session token stored in the session
cookie, echoed by the browser on every state-changing request via the
``X-CSRF-Token`` header (htmx) or a hidden ``_csrf`` form field.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app import settings

log = logging.getLogger(__name__)

# Routes that bypass auth + CSRF entirely.
PUBLIC_PATHS = {
    "/healthz",
    "/favicon.svg",
    "/favicon.ico",
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
    "/login",
    "/logout",
}
PUBLIC_PREFIXES = ("/static/",)

# scrypt parameters — modest cost; logins are rare, this is a tiny tool.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64


def auth_enabled() -> bool:
    return bool(settings.password())


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES)


def hash_password(plaintext: str, salt: Optional[bytes] = None) -> tuple[bytes, bytes]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        plaintext.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return salt, digest


class _Credential:
    """Holds the scrypt hash of WEBUI_PASSWORD captured at startup.

    Recomputed at module import (or via :func:`reload`), so rotating the env
    var requires a process restart — documented in README.
    """

    def __init__(self) -> None:
        self.salt: bytes = b""
        self.digest: bytes = b""
        self.load()

    def load(self) -> None:
        pw = settings.password()
        if pw:
            self.salt, self.digest = hash_password(pw)
        else:
            self.salt, self.digest = b"", b""

    def verify(self, attempt: str) -> bool:
        if not self.digest:
            return False
        _, candidate = hash_password(attempt, salt=self.salt)
        return hmac.compare_digest(candidate, self.digest)


_cred = _Credential()


def reload() -> None:
    """Re-read WEBUI_PASSWORD. Used by tests that monkeypatch env vars."""
    _cred.load()


def verify_password(attempt: str) -> bool:
    return _cred.verify(attempt)


def login(request: Request) -> None:
    request.session["authed"] = True
    request.session["csrf"] = secrets.token_urlsafe(32)


def logout(request: Request) -> None:
    request.session.clear()


def is_authed(request: Request) -> bool:
    return bool(request.session.get("authed"))


def csrf_token(request: Request) -> str:
    """Return the per-session CSRF token, creating one if missing."""
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def unauthorized_response(request: Request) -> Response:
    """Redirect for plain navigation, HX-Redirect for htmx."""
    next_path = request.url.path
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"
    target = f"/login?next={next_path}"
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=401, headers={"HX-Redirect": target})
    return RedirectResponse(target, status_code=303)


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def verify_csrf(request: Request) -> None:
    """FastAPI dependency: enforce CSRF on state-changing requests.

    No-op for safe methods (GET/HEAD/OPTIONS) and when auth is disabled —
    CSRF without auth is theatre. When auth is on and the method is unsafe,
    the submitted token must match the per-session value stored in the cookie.
    Token is accepted via ``X-CSRF-Token`` header (htmx) or ``_csrf`` form
    field (plain HTML forms).

    ``request.form()`` is awaited unconditionally on writes; Starlette caches
    the parsed form on the request, so the route's own ``Form(...)`` params
    re-read the same cached data.
    """
    if request.method in _SAFE_METHODS or not auth_enabled():
        return
    expected = request.session.get("csrf")
    submitted: Optional[str] = request.headers.get("X-CSRF-Token")
    if not submitted:
        ctype = request.headers.get("content-type", "")
        if "form" in ctype:
            form = await request.form()
            value = form.get("_csrf")
            submitted = value if isinstance(value, str) else None
    if not expected or not submitted or not hmac.compare_digest(expected, submitted):
        raise HTTPException(status_code=403, detail="CSRF token mismatch")
