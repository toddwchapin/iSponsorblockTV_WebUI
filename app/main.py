"""FastAPI app entry point."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import __version__, settings
from app.routes import channels as channels_route
from app.routes import config as config_route
from app.routes import pair as pair_route
from app.routes import status as status_route

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
ASSETS = BASE_DIR / "assets"
STATIC_DIR = ASSETS / "static"
FAVICON_SVG = ASSETS / "favicon.svg"


def create_app() -> FastAPI:
    app = FastAPI(title="iSponsorBlockTV WebUI", version=__version__)
    app.state.templates = TEMPLATES
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

    app.include_router(config_route.router)
    app.include_router(pair_route.router, prefix="/pair", tags=["pair"])
    app.include_router(channels_route.router, prefix="/channels", tags=["channels"])
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

    import uvicorn

    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=False)
