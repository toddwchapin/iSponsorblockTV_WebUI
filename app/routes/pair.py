"""Device pairing routes: TV code, LAN scan, and device save."""
from __future__ import annotations

from html import escape

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.services import config_io, lan_discovery
from app.services import pairing as pairing_service

router = APIRouter()


def _pair_context(request: Request, **extra) -> dict:
    return {
        "active": "pair",
        "lan_state": lan_discovery.get_state(),
        "launch_pair_timeout": lan_discovery.LAUNCH_PAIR_TIMEOUT,
        **extra,
    }


@router.get("", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    # A full render includes all current results; only append later arrivals.
    lan_discovery.mark_all_delivered()
    return request.app.state.templates.TemplateResponse(
        request, "pair.html", _pair_context(request)
    )


@router.post("/code", response_class=HTMLResponse)
async def pair_code(request: Request, code: str = Form(...)) -> HTMLResponse:
    try:
        device = await pairing_service.pair_with_code(code)
    except pairing_service.PairingError as e:
        return HTMLResponse(f'<article class="toast err">{escape(str(e))}</article>')
    if device is None:
        return HTMLResponse('<article class="toast err">Pairing returned no device.</article>')
    return request.app.state.templates.TemplateResponse(
        request, "partials/paired_device.html", {"device": device}
    )


@router.post("/save", response_class=HTMLResponse)
async def pair_save(
    screen_id: str = Form(...),
    name: str = Form(...),
    display_name: str = Form(...),
    offset: int = Form(0),
) -> HTMLResponse:
    cfg = config_io.load()
    devices = cfg.get("devices", [])
    if any(d["screen_id"] == screen_id for d in devices):
        return HTMLResponse(
            '<article class="toast err">A device with this screen ID is already in config.</article>'
        )
    selected_name = display_name or name
    devices.append({"screen_id": screen_id, "name": selected_name, "offset": offset})
    cfg["devices"] = devices
    config_io.save(cfg)
    return HTMLResponse(
        '<article class="toast ok">'
        f"Device <strong>{escape(selected_name)}</strong> added to config. "
        "Restart to apply it: "
        '<form hx-post="/restart" hx-target="closest article" hx-swap="outerHTML" style="display:inline;">'
        '<button type="submit" class="secondary">Restart service</button>'
        "</form>"
        "</article>"
    )


@router.post("/lan-scan", response_class=HTMLResponse)
async def lan_scan_start(request: Request) -> HTMLResponse:
    await lan_discovery.start_scan()
    return request.app.state.templates.TemplateResponse(
        request, "partials/lan_scan_results.html", _pair_context(request)
    )


@router.get("/lan-scan/poll", response_class=HTMLResponse)
async def lan_scan_poll(request: Request) -> HTMLResponse:
    # Append only new results; don't overwrite an in-progress display-name edit.
    new_devices = lan_discovery.take_new_devices()
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/lan_scan_poll.html",
        _pair_context(request, new_devices=new_devices),
    )
