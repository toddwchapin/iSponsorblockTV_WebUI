"""Read and write iSponsorBlockTV config.json.

Direct JSON I/O against the documented schema, deliberately avoiding upstream's
`Config.validate()` which calls `sys.exit` on missing devices.
"""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

from app import settings

log = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "devices": [],
    "skip_categories": ["sponsor"],
    "skip_count_tracking": True,
    "mute_ads": False,
    "skip_ads": False,
    "minimum_skip_length": 1,
    "auto_play": True,
    "join_name": "iSponsorBlockTV",
    "apikey": "",
    "channel_whitelist": [],
    "use_proxy": False,
}

KNOWN_KEYS = set(DEFAULTS.keys())

ALL_SKIP_CATEGORIES = [
    "sponsor",
    "selfpromo",
    "exclusive_access",
    "interaction",
    "poi_highlight",
    "intro",
    "outro",
    "preview",
    "filler",
    "music_offtopic",
]


def load(path: Path | None = None) -> dict[str, Any]:
    """Load config, merging on top of DEFAULTS. Missing file → defaults."""
    path = path or settings.config_path()
    cfg = deepcopy(DEFAULTS)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"config.json root must be an object, got {type(data).__name__}")
        for k, v in data.items():
            cfg[k] = v
    return cfg


def save(cfg: dict[str, Any], path: Path | None = None) -> Path:
    """Persist config atomically. Returns the file path written."""
    path = path or settings.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = sanitize(cfg)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=4)
    tmp.replace(path)
    log.info("config saved to %s (%d bytes)", path, path.stat().st_size)
    return path


def sanitize(cfg: dict[str, Any]) -> dict[str, Any]:
    """Coerce types + filter unknown/empty values to match upstream expectations."""
    out: dict[str, Any] = {}
    for key, default in DEFAULTS.items():
        value = cfg.get(key, default)
        if key == "skip_categories":
            value = [c for c in (value or []) if c]
        elif key == "minimum_skip_length":
            try:
                value = int(value)
            except (TypeError, ValueError):
                value = DEFAULTS[key]
        elif key == "devices":
            value = [_clean_device(d) for d in (value or []) if d.get("screen_id")]
        elif key == "channel_whitelist":
            value = [
                {"id": c.get("id", "").strip(), "name": c.get("name", "").strip()}
                for c in (value or [])
                if c.get("id")
            ]
        elif isinstance(default, bool):
            value = bool(value)
        out[key] = value
    return out


def _clean_device(d: dict[str, Any]) -> dict[str, Any]:
    try:
        offset = int(d.get("offset", 0) or 0)
    except (TypeError, ValueError):
        offset = 0
    return {
        "screen_id": str(d.get("screen_id", "")).strip(),
        "name": str(d.get("name", "")).strip() or "YouTube on TV",
        "offset": offset,
    }
