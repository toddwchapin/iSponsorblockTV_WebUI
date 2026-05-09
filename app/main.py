"""FastAPI app entry point."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app import __version__, auth, settings
from app.routes import auth as auth_route
from app.routes import channels as channels_route
from app.routes import config as config_route
from app.routes import pair as pair_route
from app.routes import status as status_route

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
ASSETS = BASE_DIR / "assets"
STATIC_DIR = ASSETS / "static"
FAVICON_SVG = ASSETS / "favicon.svg"

log = logging.getLogger(__name__)


def _csrf_for_template(request) -> str:
    """Jinja global: surface the per-session CSRF token to base.html."""
    return auth.csrf_token(request) if auth.auth_enabled() else ""


def create_app() -> FastAPI:
    app = FastAPI(title="iSponsorBlockTV WebUI", version=__version__)
    app.state.templates = TEMPLATES
    TEMPLATES.env.globals["auth_enabled"] = auth.auth_enabled
    TEMPLATES.env.globals["csrf_for_request"] = _csrf_for_template

    # Middleware registration is LIFO — the last added middleware is outermost.
    # auth_gate reads request.session, so SessionMiddleware must wrap it (be
    # registered AFTER auth_gate so it ends up outer).
    @app.middleware("http")
    async def auth_gate(request, call_next):
        if not auth.auth_enabled() or auth.is_public(request.url.path):
            return await call_next(request)
        if auth.is_authed(request):
            return await call_next(request)
        return auth.unauthorized_response(request)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret(),
        max_age=settings.session_ttl_seconds(),
        same_site="lax",
        https_only=False,
    )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/favicon.svg", include_in_schema=False)
    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(FAVICON_SVG, media_type="image/svg+xml")

    @app.get("/apple-touch-icon.png", include_in_schema=False)
    @app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
    async def apple_touch_icon() -> Response:
        return Response(status_code=204)

    app.include_router(auth_route.router)

    # CSRF on every state-changing route. GET routes are unaffected — the
    # dependency no-ops outside of write methods because it only reads
    # form/header data on POST/DELETE/PUT (FastAPI doesn't invoke Form()
    # parsing on GET).
    csrf_dep = [Depends(auth.verify_csrf)]
    app.include_router(config_route.router, dependencies=csrf_dep)
    app.include_router(pair_route.router, prefix="/pair", tags=["pair"], dependencies=csrf_dep)
    app.include_router(
        channels_route.router, prefix="/channels", tags=["channels"], dependencies=csrf_dep
    )
    app.include_router(status_route.router, tags=["status"])
    return app


app = create_app()


def run() -> None:
    parser = argparse.ArgumentParser(prog="isponsorblocktv-webui")
    parser.add_argument(
        "--version",
        action="version",
        version=f"isponsorblocktv-webui {__version__}",
    )
    parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    if not auth.auth_enabled():
        log.warning(
            "WEBUI_PASSWORD not set — UI is open to anyone who can reach %s:%s. "
            "Set WEBUI_PASSWORD or front the service with an authenticated reverse proxy.",
            settings.HOST,
            settings.PORT,
        )

    import uvicorn

    # access_log off: forms POST the YouTube Data API key in the request body
    # (not the URL), but disable access logging anyway as a belt-and-suspenders
    # measure against future routes that might accept secrets in query strings.
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        access_log=False,
    )
