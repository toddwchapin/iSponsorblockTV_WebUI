"""Detect iSponsorBlockTV service state and tail its logs.

The detection chain mirrors :mod:`app.services.restart`: docker container →
systemd user unit → systemd system unit (via passwordless sudo). Public
helpers below are shared with ``restart.py`` so the two modules cannot drift.

Public API:
    status()             -> Status
    tail_logs(n)         -> LogsResult

Detection helpers (shared with restart.py):
    docker_socket_exists()
    docker_container_running(name)
    docker_inspect_exists(name)
    systemctl_user_state(name)
    systemctl_system_state(name)
    can_sudo_systemctl()
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field

from app import settings

log = logging.getLogger(__name__)

DOCKER_SOCK = "/var/run/docker.sock"
DEFAULT_TAIL_LINES = 200
MAX_TAIL_LINES = 5000


@dataclass
class Status:
    method: str  # "docker" | "systemd-user" | "systemd-system" | "none"
    running: bool
    detail: str = ""


@dataclass
class LogsResult:
    method: str
    lines: list[str] = field(default_factory=list)
    error: str | None = None


# ----------------------- detection helpers -----------------------

def docker_socket_exists() -> bool:
    return os.path.exists(DOCKER_SOCK)


def docker_container_running(name: str) -> bool:
    """True iff a running container with this exact name is listed by `docker ps`."""
    if not docker_socket_exists():
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


def docker_inspect_exists(name: str) -> bool:
    """True iff a container with this name exists (running or stopped)."""
    if not docker_socket_exists():
        return False
    docker = shutil.which("docker")
    if not docker:
        return False
    try:
        out = subprocess.run(
            [docker, "inspect", "--format", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0


def systemctl_user_state(name: str) -> str | None:
    """Return systemctl --user is-active state ('active', 'inactive', 'failed', etc.)
    or None if systemctl is unavailable or the call errors."""
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return None
    try:
        out = subprocess.run(
            [systemctl, "--user", "is-active", name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    state = out.stdout.strip()
    # is-active prints "inactive\n" with returncode 3 — treat any non-empty
    # stdout as a valid state. Empty + nonzero return means unit unknown.
    return state or None


def can_sudo_systemctl() -> bool:
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


def systemctl_system_state(name: str) -> str | None:
    if not can_sudo_systemctl():
        return None
    sudo = shutil.which("sudo")
    if not sudo:
        return None
    try:
        out = subprocess.run(
            [sudo, "-n", "systemctl", "is-active", name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or None


# ----------------------- public API -----------------------

def status() -> Status:
    name = settings.service_name()

    if docker_socket_exists() and shutil.which("docker"):
        if docker_container_running(name):
            return Status("docker", True, f"container {name} running")
        if docker_inspect_exists(name):
            return Status("docker", False, f"container {name} stopped")
        # No such container — fall through to systemd.

    user_state = systemctl_user_state(name)
    if user_state:
        return Status("systemd-user", user_state == "active", f"user unit: {user_state}")

    system_state = systemctl_system_state(name)
    if system_state:
        return Status(
            "systemd-system", system_state == "active", f"system unit: {system_state}"
        )

    return Status("none", False, "no detection method available")


def tail_logs(n: int = DEFAULT_TAIL_LINES) -> LogsResult:
    name = settings.service_name()
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = DEFAULT_TAIL_LINES
    n = max(1, min(n, MAX_TAIL_LINES))

    docker = shutil.which("docker") if docker_socket_exists() else None
    if docker and (docker_container_running(name) or docker_inspect_exists(name)):
        return _run_tail([docker, "logs", "--tail", str(n), name], "docker")

    journalctl = shutil.which("journalctl")
    if journalctl and systemctl_user_state(name):
        return _run_tail(
            [journalctl, "--user", "-u", name, "-n", str(n), "--no-pager",
             "--output=short-iso"],
            "systemd-user",
        )

    if journalctl and can_sudo_systemctl():
        sudo = shutil.which("sudo")
        if sudo:
            return _run_tail(
                [sudo, "-n", "journalctl", "-u", name, "-n", str(n), "--no-pager",
                 "--output=short-iso"],
                "systemd-system",
            )

    return LogsResult(
        "none",
        error=(
            "No log source available: docker socket, `journalctl --user`, and "
            "passwordless `sudo journalctl` all unavailable. See README."
        ),
    )


def _run_tail(cmd: list[str], method: str) -> LogsResult:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        return LogsResult(method, error=f"log tail failed: {e}")
    if out.returncode != 0:
        err = out.stderr.strip() or out.stdout.strip() or f"exit {out.returncode}"
        return LogsResult(method, error=err)
    return LogsResult(method, lines=out.stdout.splitlines())
