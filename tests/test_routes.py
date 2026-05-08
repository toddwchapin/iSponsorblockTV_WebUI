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
    # Issue #15 round 2: blank rows stay editable so the "+ Add device"
    # power-user path keeps working.
    assert "readonly" not in r.text


def test_existing_device_screen_id_readonly(app_with_tmp_config) -> None:
    """Issue #15 round 2 #1: screen IDs for existing devices are not editable."""
    app, tmp = app_with_tmp_config
    (tmp / "config.json").write_text(
        json.dumps({"devices": [{"screen_id": "scr-x", "name": "TV", "offset": 0}]})
    )
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "scr-x" in r.text
    # The screen-id input for an existing device carries the readonly attr.
    assert 'name="device_screen_id" value="scr-x"' in r.text
    assert "readonly" in r.text


def test_config_page_uses_two_column_grid(app_with_tmp_config) -> None:
    """Issue #15 round 2 #4-5: SponsorBlock left, Ads/Playback stacked right."""
    app, _ = app_with_tmp_config
    client = TestClient(app)
    r = client.get("/")
    assert 'class="config-grid"' in r.text
    assert 'class="grid-left"' in r.text
    assert 'class="grid-right-top"' in r.text
    assert 'class="grid-right-bottom"' in r.text


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


def test_save_button_disabled_when_running(app_with_tmp_config, monkeypatch) -> None:
    """Issue #15 round 3 item 4: with service running, save button starts disabled
    so dirty-tracking JS can enable it on first edit."""
    from app.services import service_status as ss

    app, _ = app_with_tmp_config
    monkeypatch.setattr(
        ss, "status", lambda: ss.Status("docker", True, "container running")
    )
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="save-btn"' in r.text
    assert "Save and restart service" in r.text
    assert 'data-mode="restart"' in r.text
    assert "disabled" in r.text  # the save button is disabled


def test_save_button_start_mode_when_stopped(app_with_tmp_config, monkeypatch) -> None:
    """Issue #15 round 3 item 5: when service detected as stopped, button is
    labeled 'Start service' and is enabled (no dirty gate)."""
    from app.services import service_status as ss

    app, _ = app_with_tmp_config
    monkeypatch.setattr(
        ss, "status", lambda: ss.Status("docker", False, "container stopped")
    )
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Start service" in r.text
    assert 'data-mode="start"' in r.text
    # The save-btn line itself must not be disabled. Other elements may be
    # disabled, so anchor on the button id.
    btn_line = next(
        line for line in r.text.splitlines() if 'id="save-btn"' in line
    )
    # button tag spans multiple lines — collect until '>'
    idx = r.text.index('id="save-btn"')
    tag_close = r.text.index(">", idx)
    btn_tag = r.text[r.text.rindex("<", 0, idx):tag_close + 1]
    assert "disabled" not in btn_tag


def test_save_button_legacy_when_unknown(app_with_tmp_config, monkeypatch) -> None:
    """When detection method is 'none', no dirty gate (user not locked out)."""
    from app.services import service_status as ss

    app, _ = app_with_tmp_config
    monkeypatch.setattr(
        ss, "status", lambda: ss.Status("none", False, "no detection")
    )
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Save and restart service" in r.text
    idx = r.text.index('id="save-btn"')
    tag_close = r.text.index(">", idx)
    btn_tag = r.text[r.text.rindex("<", 0, idx):tag_close + 1]
    assert "disabled" not in btn_tag
    assert 'data-no-dirty-gate="1"' in btn_tag


def test_status_badge_short_labels(app_with_tmp_config, monkeypatch) -> None:
    """Issue #15 round 3 item 6: badge shows 'Running' / 'Stopped' / 'Unknown'."""
    from app.services import service_status as ss

    app, _ = app_with_tmp_config
    client = TestClient(app)

    monkeypatch.setattr(ss, "status", lambda: ss.Status("docker", True, "ok"))
    r = client.get("/status/badge")
    assert "Running" in r.text and "Stopped" not in r.text

    monkeypatch.setattr(ss, "status", lambda: ss.Status("docker", False, "down"))
    r = client.get("/status/badge")
    assert "Stopped" in r.text
    assert "status-badge err" in r.text  # red

    monkeypatch.setattr(ss, "status", lambda: ss.Status("none", False, "none"))
    r = client.get("/status/badge")
    assert "Unknown" in r.text
    assert "status-badge unknown" in r.text


def test_tab_bar_active_class_per_page(app_with_tmp_config) -> None:
    """Issue #15 round 3 item 1: nav becomes a tab bar with the current
    page's tab marked active."""
    app, _ = app_with_tmp_config
    client = TestClient(app)

    for path, label in [("/", "Config"), ("/pair", "Pair Device"),
                         ("/channels", "Channels"), ("/logs", "Logs")]:
        r = client.get(path)
        assert r.status_code == 200, path
        # The active tab gets the 'active' CSS class.
        idx = r.text.index(f">{label}<")
        # Walk back to the opening <a tag for this link
        tag_start = r.text.rindex("<a", 0, idx)
        anchor = r.text[tag_start:idx]
        assert "active" in anchor, f"{path} tab missing active class"


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
