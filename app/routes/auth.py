"""Login / logout routes.

GET /login  — render password prompt (also issues an anonymous session cookie
              with a CSRF token, so the login POST itself is CSRF-protected
              against forced-login attacks).
POST /login — verify password, regenerate session, redirect to ``next``.
POST /logout — clear session, redirect to /login.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import auth

log = logging.getLogger(__name__)
router = APIRouter()


def _safe_next(raw: str) -> str:
    """Reject open-redirect: only accept same-origin paths starting with /."""
    if not raw or not raw.startswith("/") or raw.startswith("//"):
        return "/"
    return raw


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request, next: str = "/") -> HTMLResponse:
    if not auth.auth_enabled():
        return RedirectResponse("/", status_code=303)  # type: ignore[return-value]
    if auth.is_authed(request):
        return RedirectResponse(_safe_next(next), status_code=303)  # type: ignore[return-value]
    csrf = auth.csrf_token(request)
    return request.app.state.templates.TemplateResponse(
        request,
        "login.html",
        {"next": _safe_next(next), "csrf": csrf, "error": None},
    )


@router.post("/login", response_class=HTMLResponse, dependencies=[Depends(auth.verify_csrf)])
async def login_post(
    request: Request,
    password: str = Form(...),
    next: str = Form("/"),
) -> HTMLResponse:
    if not auth.auth_enabled():
        return RedirectResponse("/", status_code=303)  # type: ignore[return-value]
    if not auth.verify_password(password):
        log.warning("login failed from %s", request.client.host if request.client else "?")
        csrf = auth.csrf_token(request)
        return request.app.state.templates.TemplateResponse(
            request,
            "login.html",
            {"next": _safe_next(next), "csrf": csrf, "error": "Wrong password."},
            status_code=401,
        )
    auth.login(request)
    return RedirectResponse(_safe_next(next), status_code=303)  # type: ignore[return-value]


@router.post("/logout")
async def logout_post(request: Request) -> RedirectResponse:
    auth.logout(request)
    return RedirectResponse("/login", status_code=303)
