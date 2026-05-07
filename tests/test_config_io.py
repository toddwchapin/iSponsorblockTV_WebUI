"""Round-trip + sanitize tests for config_io."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import config_io


def test_load_missing_returns_defaults(tmp_path: Path) -> None:
    cfg = config_io.load(tmp_path / "missing.json")
    assert cfg == config_io.DEFAULTS


def test_load_merges_partial_over_defaults(tmp_path: Path) -> None:
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"apikey": "abc", "mute_ads": True}))
    cfg = config_io.load(p)
    assert cfg["apikey"] == "abc"
    assert cfg["mute_ads"] is True
    assert cfg["skip_categories"] == ["sponsor"]  # default preserved


def test_save_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "config.json"
    payload = {
        "devices": [{"screen_id": "abc123", "name": "Living Room", "offset": 250}],
        "apikey": "key",
        "skip_categories": ["sponsor", "selfpromo"],
        "mute_ads": True,
    }
    config_io.save(payload, p)
    on_disk = json.loads(p.read_text())
    assert on_disk["devices"][0]["screen_id"] == "abc123"
    assert on_disk["apikey"] == "key"
    assert on_disk["mute_ads"] is True
    # Defaults filled in for omitted keys
    assert on_disk["skip_count_tracking"] is True


def test_sanitize_filters_empty_skip_categories() -> None:
    cleaned = config_io.sanitize({"skip_categories": ["sponsor", "", None, "intro"]})
    assert cleaned["skip_categories"] == ["sponsor", "intro"]


def test_sanitize_drops_devices_without_screen_id() -> None:
    cleaned = config_io.sanitize(
        {"devices": [{"screen_id": "x", "name": "ok"}, {"screen_id": "", "name": "drop"}]}
    )
    assert len(cleaned["devices"]) == 1
    assert cleaned["devices"][0]["screen_id"] == "x"


def test_sanitize_coerces_minimum_skip_length() -> None:
    cleaned = config_io.sanitize({"minimum_skip_length": "5"})
    assert cleaned["minimum_skip_length"] == 5

    cleaned = config_io.sanitize({"minimum_skip_length": "garbage"})
    assert cleaned["minimum_skip_length"] == 1


def test_sanitize_drops_whitelist_entries_missing_id() -> None:
    cleaned = config_io.sanitize(
        {"channel_whitelist": [{"id": "UC1", "name": "a"}, {"id": "", "name": "b"}]}
    )
    assert len(cleaned["channel_whitelist"]) == 1
    assert cleaned["channel_whitelist"][0]["id"] == "UC1"


def test_load_rejects_non_object_root(tmp_path: Path) -> None:
    p = tmp_path / "config.json"
    p.write_text("[]")
    with pytest.raises(ValueError):
        config_io.load(p)
