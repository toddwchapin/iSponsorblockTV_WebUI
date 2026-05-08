"""Smoke tests for HTTP routes via FastAPI TestClient."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_tmp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WEBUI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WEBUI_NO_RESTART", "1")
    # Clear cached settings if any module-level cached the dir
    import importlib

    from app import settings as settings_mod
    importlib.reload(settings_mod)
    from app import main as main_mod
    importlib.reload(main_mod)
    return main_mod.app, tmp_path


def test_healthz_reports_version(app_with_tmp_config) -> None:
    """Users debug stale-install issues with `curl /healthz`. Don't break it."""
    from app import __version__

    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body == {"status": "ok", "version": __version__}


def test_favicon_svg_served(app_with_tmp_config) -> None:
    """Issue #18: /favicon.svg returns the bundled icon."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/favicon.svg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in r.content


def test_favicon_ico_served_as_svg(app_with_tmp_config) -> None:
    """Issue #18: legacy /favicon.ico probe gets the same SVG, not 404."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert b"<svg" in r.content


def test_apple_touch_icon_returns_204(app_with_tmp_config) -> None:
    """Issue #18: iOS apple-touch-icon probes get 204, not 404."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    for path in ("/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"):
        r = client.get(path)
        assert r.status_code == 204, path
        assert r.content == b""


def test_index_links_favicon(app_with_tmp_config) -> None:
    """Issue #18: base.html declares the SVG favicon so browsers stop
    probing /favicon.ico in the first place."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert 'rel="icon"' in r.text
    assert '/favicon.svg' in r.text


def test_no_static_mount(app_with_tmp_config) -> None:
    """Regression for issue #9.

    The empty `app/static/` dir was never shipped in the wheel because the
    `static/**/*` package-data glob matched no files. Starlette's
    `StaticFiles(directory=...)` then raised at app construction on pipx
    installs. If you re-add real static assets, ship at least one real
    file and delete this test in the same PR.
    """
    app, _ = app_with_tmp_config
    routes = {getattr(r, "path", None) for r in app.routes}
    assert "/static" not in routes


def test_index_renders_with_no_existing_config(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Configuration" in r.text
    assert "Skip categories" in r.text


def test_save_persists_config(app_with_tmp_config) -> None:
    app, tmp = app_with_tmp_config
    client = TestClient(app)
    r = client.post(
        "/save",
        data={
            "device_name": "Living",
            "device_screen_id": "screen-xyz",
            "device_offset": "100",
            "skip_categories": ["sponsor", "selfpromo"],
            "minimum_skip_length": "2",
            "skip_count_tracking": "on",
            "mute_ads": "on",
            "auto_play": "on",
            "join_name": "iSponsorBlockTV",
            "apikey": "test-key",
        },
    )
    assert r.status_code == 200
    assert "Saved" in r.text
    on_disk = json.loads((tmp / "config.json").read_text())
    assert on_disk["apikey"] == "test-key"
    assert on_disk["devices"] == [
        {"screen_id": "screen-xyz", "name": "Living", "offset": 100}
    ]
    assert on_disk["mute_ads"] is True
    assert on_disk["skip_ads"] is False
    assert "selfpromo" in on_disk["skip_categories"]


def test_save_writes_to_settings_config_path(app_with_tmp_config) -> None:
    """Issue #15 comment B: /save writes the file iSponsorBlockTV reads."""
    from app import settings

    app, tmp = app_with_tmp_config
    assert settings.config_path() == tmp / "config.json"
    client = TestClient(app)
    r = client.post("/save", data={"device_screen_id": "x"})
    assert r.status_code == 200
    assert settings.config_path().exists()


def test_index_reads_existing_config(app_with_tmp_config) -> None:
    """Issue #15 comment D: GET / reflects what's on disk at config_path()."""
    app, tmp = app_with_tmp_config
    (tmp / "config.json").write_text(
        json.dumps(
            {
                "apikey": "PRELOADED_KEY_123",
                "devices": [{"screen_id": "scr-pre", "name": "Pre", "offset": 42}],
                "mute_ads": True,
            }
        )
    )
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "PRELOADED_KEY_123" in r.text
    assert "scr-pre" in r.text


def test_blank_device_row(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/devices/blank-row")
    assert r.status_code == 200
    assert 'name="device_screen_id"' in r.text


def test_channels_page_warns_when_no_apikey(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/channels")
    assert r.status_code == 200
    assert "No YouTube API key" in r.text


def test_channels_remove_404_when_missing(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.delete("/channels/UC_does_not_exist")
    assert r.status_code == 404


def test_channels_search_errors_without_apikey(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/channels/search?q=foo")
    assert r.status_code == 200
    assert "No YouTube API key" in r.text


def test_pair_page_renders(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/pair")
    assert r.status_code == 200
    assert "Pair a YouTube TV device" in r.text


def test_pair_code_rejects_short_code(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.post("/pair/code", data={"code": "12345"})
    assert r.status_code == 200
    assert "12 digits" in r.text


def test_status_endpoint_shape(app_with_tmp_config) -> None:
    """Issue #4: GET /status returns method + running + detail."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/status")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"method", "running", "detail"}
    assert isinstance(body["running"], bool)


def test_status_badge_partial(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/status/badge")
    assert r.status_code == 200
    assert "status-badge" in r.text
    assert 'hx-get="/status/badge"' in r.text


def test_logs_page_renders(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/logs")
    assert r.status_code == 200
    assert "Service logs" in r.text


def test_logs_tail_partial(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/logs/tail?n=10")
    assert r.status_code == 200
    assert 'id="logs-tail"' in r.text


def test_logs_link_in_nav(app_with_tmp_config) -> None:
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/logs"' in r.text
    assert 'id="status-badge"' in r.text


def test_pair_save_appends_device(app_with_tmp_config) -> None:
    app, tmp = app_with_tmp_config
    client = TestClient(app)
    r = client.post(
        "/pair/save",
        data={
            "screen_id": "abc-screen",
            "name": "TV",
            "display_name": "Bedroom",
            "offset": "0",
        },
    )
    assert r.status_code == 200
    assert "added to config" in r.text
    on_disk = json.loads((tmp / "config.json").read_text())
    assert on_disk["devices"] == [
        {"screen_id": "abc-screen", "name": "Bedroom", "offset": 0}
    ]
