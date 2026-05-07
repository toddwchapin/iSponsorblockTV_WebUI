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
