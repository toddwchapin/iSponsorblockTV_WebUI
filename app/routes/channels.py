"""Channel whitelist routes: list, search, add, remove."""
from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.services import channels as channels_service
from app.services import config_io

router = APIRouter()


@router.get("", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    cfg = config_io.load()
    return request.app.state.templates.TemplateResponse(
        request,
        "channels.html",
        {
            "whitelist": cfg.get("channel_whitelist", []),
            "has_api_key": bool(cfg.get("apikey")),
            "use_proxy": bool(cfg.get("use_proxy", False)),
            "active": "channels",
        },
    )


@router.post("/apikey", response_class=HTMLResponse)
async def save_apikey(
    request: Request,
    apikey: str = Form(""),
    use_proxy: str = Form(""),
) -> HTMLResponse:
    cfg = config_io.load()
    cfg["apikey"] = apikey.strip()
    cfg["use_proxy"] = (use_proxy == "on")
    config_io.save(cfg)
    msg = "API key saved." if cfg["apikey"] else "API key cleared."
    return HTMLResponse(f'<div class="toast ok">{msg}</div>')


@router.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = "") -> HTMLResponse:
    cfg = config_io.load()
    api_key = cfg.get("apikey", "")
    try:
        hits = await channels_service.search(api_key, q)
    except channels_service.ChannelSearchError as e:
        return HTMLResponse(f'<p class="toast err">{e}</p>')
    existing_ids = {c["id"] for c in cfg.get("channel_whitelist", [])}
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/channel_search_results.html",
        {"hits": hits, "existing_ids": existing_ids},
    )


@router.post("/add", response_class=HTMLResponse)
async def add(
    request: Request,
    channel_id: str = Form(...),
    channel_name: str = Form(...),
) -> HTMLResponse:
    cfg = config_io.load()
    whitelist = cfg.get("channel_whitelist", [])
    if not any(c["id"] == channel_id for c in whitelist):
        whitelist.append({"id": channel_id, "name": channel_name})
        cfg["channel_whitelist"] = whitelist
        config_io.save(cfg)
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/channel_row.html",
        {"c": {"id": channel_id, "name": channel_name}},
    )


@router.delete("/{channel_id}", response_class=HTMLResponse)
async def remove(channel_id: str) -> HTMLResponse:
    cfg = config_io.load()
    before = cfg.get("channel_whitelist", [])
    after = [c for c in before if c["id"] != channel_id]
    if len(after) == len(before):
        raise HTTPException(404, "channel not in whitelist")
    cfg["channel_whitelist"] = after
    config_io.save(cfg)
    return HTMLResponse("")  # empty replaces the row
