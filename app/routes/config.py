"""Config form: GET /, GET /devices/blank-row, POST /save."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import settings
from app.services import config_io, restart as restart_service, service_status

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    cfg = config_io.load()
    return request.app.state.templates.TemplateResponse(
        request,
        "config.html",
        {
            "cfg": cfg,
            "config_path": str(settings.config_path()),
            "all_skip_categories": config_io.ALL_SKIP_CATEGORIES,
            "st": service_status.status(),
            "active": "config",
        },
    )


@router.get("/devices/blank-row", response_class=HTMLResponse)
async def blank_device_row(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/device_row.html",
        {"d": {"name": "YouTube on TV", "screen_id": "", "offset": 0}},
    )


@router.post("/save", response_class=HTMLResponse)
async def save(request: Request) -> HTMLResponse:
    form = await request.form()
    existing = config_io.load()
    new_cfg = _form_to_config(form, existing)
    try:
        config_io.save(new_cfg)
    except OSError as e:
        return _toast(request, ok=False, message=f"Save failed: {e}")
    result = restart_service.restart()
    return _toast(request, ok=result.ok, message=f"Saved. {result.message()}")


def _form_to_config(form: Any, existing: dict[str, Any]) -> dict[str, Any]:
    names = form.getlist("device_name")
    screen_ids = form.getlist("device_screen_id")
    offsets = form.getlist("device_offset")
    devices = []
    for n, s, o in zip(names, screen_ids, offsets):
        if str(s).strip():
            devices.append({"name": n, "screen_id": s, "offset": o or 0})
    return {
        "devices": devices,
        "skip_categories": form.getlist("skip_categories"),
        "minimum_skip_length": form.get("minimum_skip_length") or 0,
        "skip_count_tracking": form.get("skip_count_tracking") == "on",
        "mute_ads": form.get("mute_ads") == "on",
        "skip_ads": form.get("skip_ads") == "on",
        "auto_play": form.get("auto_play") == "on",
        "join_name": form.get("join_name") or "iSponsorBlockTV",
        # Preserved from disk — managed via /channels (apikey, use_proxy)
        # and the /channels page itself (channel_whitelist).
        "apikey": existing.get("apikey", ""),
        "use_proxy": existing.get("use_proxy", False),
        "channel_whitelist": existing.get("channel_whitelist", []),
    }


def _toast(request: Request, ok: bool, message: str) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request, "partials/toast.html", {"ok": ok, "message": message}
    )
