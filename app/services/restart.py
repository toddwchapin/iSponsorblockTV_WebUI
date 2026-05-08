"""Restart the iSponsorBlockTV service after a config save.

Detection order:
1. Docker container `iSponsorBlockTV` running → docker restart
2. Systemd user unit active → systemctl --user restart
3. Sudo systemctl restart (system-wide) — requires NOPASSWD sudoers rule
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass

from app import settings

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

    if _docker_container_running(name):
        log.info("restart: docker container %s detected", name)
        return _run(["docker", "restart", name], "docker")

    if _systemd_user_unit_active(name):
        log.info("restart: systemd user unit %s active", name)
        return _run(["systemctl", "--user", "restart", name], "systemd-user")

    if _can_sudo_systemctl():
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


def _docker_container_running(name: str) -> bool:
    if not os.path.exists("/var/run/docker.sock"):
        return False
    docker = shutil.which("docker")
    if not docker:
        return False
    try:
        out = subprocess.run(
            [docker, "ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("docker ps failed: %s", e)
        return False
    return name in out.stdout.strip().splitlines()


def _systemd_user_unit_active(name: str) -> bool:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return False
    try:
        out = subprocess.run(
            [systemctl, "--user", "is-active", name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.stdout.strip() == "active"


def _can_sudo_systemctl() -> bool:
    sudo = shutil.which("sudo")
    if not sudo:
        return False
    try:
        out = subprocess.run(
            [sudo, "-n", "true"], capture_output=True, timeout=3, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0


def _run(cmd: list[str], method: str) -> RestartResult:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return RestartResult(False, method, str(e))
    if out.returncode == 0:
        return RestartResult(True, method, out.stdout.strip())
    return RestartResult(False, method, out.stderr.strip() or out.stdout.strip())
