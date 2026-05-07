"""Runtime settings: data dir resolution, restart behavior, host/port."""
from __future__ import annotations

import os
from pathlib import Path

from appdirs import user_data_dir


def data_dir() -> Path:
    """Resolve iSponsorBlockTV data dir.

    Override order: WEBUI_DATA_DIR > iSPBTV_data_dir > platform user_data_dir.
    """
    override = os.environ.get("WEBUI_DATA_DIR") or os.environ.get("iSPBTV_data_dir")
    if override:
        return Path(override).expanduser()
    return Path(user_data_dir("iSponsorBlockTV", "dmunozv04"))


def config_path() -> Path:
    return data_dir() / "config.json"


def restart_disabled() -> bool:
    """Skip subprocess restart calls (used in dev/tests)."""
    return os.environ.get("WEBUI_NO_RESTART", "").lower() in ("1", "true", "yes")


def service_name() -> str:
    return os.environ.get("WEBUI_SERVICE_NAME", "iSponsorBlockTV")


HOST = os.environ.get("WEBUI_HOST", "0.0.0.0")
PORT = int(os.environ.get("WEBUI_PORT", "8099"))
