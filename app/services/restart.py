"""Restart the iSponsorBlockTV service after a config save.

Detection order (mirrored in :mod:`app.services.service_status`):
1. Docker container `iSponsorBlockTV` running → docker restart
2. Systemd user unit active → systemctl --user restart
3. Sudo systemctl restart (system-wide) — requires NOPASSWD sudoers rule
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass

from app import settings
from app.services.service_status import (
    can_sudo_systemctl,
    docker_container_running,
    systemctl_user_state,
)

log = logging.getLogger(__name__)


@dataclass
class RestartResult:
    ok: bool
    method: str
    detail: str

    def message(self) -> str:
        if self.ok:
            return f"Service restarted via {self.method}."
        return f"Restart failed ({self.method}): {self.detail}"


def restart() -> RestartResult:
    if settings.restart_disabled():
        return RestartResult(True, "skipped", "WEBUI_NO_RESTART set")

    name = settings.service_name()

    if docker_container_running(name):
        log.info("restart: docker container %s detected", name)
        return _run(["docker", "restart", name], "docker")

    if systemctl_user_state(name) == "active":
        log.info("restart: systemd user unit %s active", name)
        return _run(["systemctl", "--user", "restart", name], "systemd-user")

    if can_sudo_systemctl():
        log.info("restart: passwordless sudo available, using systemctl restart %s", name)
        return _run(["sudo", "-n", "systemctl", "restart", name], "systemd-system")

    log.warning("restart: no detection method succeeded for %s", name)
    return RestartResult(
        ok=False,
        method="none",
        detail=(
            "no docker container, user unit, or passwordless sudo found — "
            "restart the service manually"
        ),
    )


def _run(cmd: list[str], method: str) -> RestartResult:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return RestartResult(False, method, str(e))
    if out.returncode == 0:
        return RestartResult(True, method, out.stdout.strip())
    return RestartResult(False, method, out.stderr.strip() or out.stdout.strip())
