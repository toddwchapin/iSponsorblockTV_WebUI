"""Runtime settings: data dir resolution, restart behavior, host/port, auth."""
from __future__ import annotations

import os
import secrets
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


def password() -> str:
    """Single shared password for the WebUI. Empty string → auth disabled."""
    return os.environ.get("WEBUI_PASSWORD", "")


def session_ttl_seconds() -> int:
    """Session cookie max-age. Default 7 days."""
    try:
        return int(os.environ.get("WEBUI_SESSION_TTL", str(7 * 24 * 3600)))
    except ValueError:
        return 7 * 24 * 3600


def session_secret() -> str:
    """Signing key for session cookies.

    Falls back to a process-lifetime random key — sessions survive restarts only
    when WEBUI_SESSION_SECRET is set, which is the right tradeoff for a
    single-admin tool: no on-disk secret to leak, log out everyone on restart.
    """
    return os.environ.get("WEBUI_SESSION_SECRET") or secrets.token_urlsafe(48)


# Default bind: 127.0.0.1. LAN deployments must opt in via WEBUI_HOST=0.0.0.0
# (and ideally pair with WEBUI_PASSWORD or a reverse proxy). See README
# Security notes for the threat model.
HOST = os.environ.get("WEBUI_HOST", "127.0.0.1")
PORT = int(os.environ.get("WEBUI_PORT", "8099"))
