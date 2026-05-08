"""Service status badge + log tail viewer (issue #4)."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.services import service_status

router = APIRouter()


@router.get("/status")
async def status_json() -> JSONResponse:
    return JSONResponse(asdict(service_status.status()))


@router.get("/status/badge", response_class=HTMLResponse)
async def status_badge(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request, "partials/status_badge.html", {"st": service_status.status()}
    )


@router.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, n: int = service_status.DEFAULT_TAIL_LINES) -> HTMLResponse:
    result = service_status.tail_logs(n)
    return request.app.state.templates.TemplateResponse(
        request, "logs.html", {"result": result, "n": n, "default_n": service_status.DEFAULT_TAIL_LINES}
    )


@router.get("/logs/tail", response_class=HTMLResponse)
async def logs_tail(request: Request, n: int = service_status.DEFAULT_TAIL_LINES) -> HTMLResponse:
    result = service_status.tail_logs(n)
    return request.app.state.templates.TemplateResponse(
        request, "partials/logs_tail.html", {"result": result, "n": n}
    )
