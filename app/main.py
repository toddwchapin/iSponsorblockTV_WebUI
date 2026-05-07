"""FastAPI app entry point."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from app import settings
from app.routes import channels as channels_route
from app.routes import config as config_route
from app.routes import pair as pair_route

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_app() -> FastAPI:
    app = FastAPI(title="iSponsorBlockTV WebUI", version="0.1.0")
    app.state.templates = TEMPLATES
    app.include_router(config_route.router)
    app.include_router(pair_route.router, prefix="/pair", tags=["pair"])
    app.include_router(channels_route.router, prefix="/channels", tags=["channels"])
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=False)
