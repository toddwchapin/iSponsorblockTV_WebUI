"""Issue #15 comment C: confirm restart() invokes the right command per branch.

Each test pins os/shutil/subprocess to a specific environment so a single
detection branch wins, then asserts on the command actually invoked.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from app.services import restart


@pytest.fixture(autouse=True)
def _clear_no_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    """Other test modules set WEBUI_NO_RESTART; restart-unit tests need it off."""
    monkeypatch.delenv("WEBUI_NO_RESTART", raising=False)
    monkeypatch.setenv("WEBUI_SERVICE_NAME", "iSponsorBlockTV")


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_restart_uses_docker_when_container_running(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "exists", lambda p: p == "/var/run/docker.sock")
    monkeypatch.setattr(shutil, "which", lambda b: f"/usr/bin/{b}")

    calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        if len(cmd) >= 2 and cmd[1] == "ps":
            return _completed(stdout="iSponsorBlockTV\n")
        if cmd[:3] == ["docker", "restart", "iSponsorBlockTV"]:
            return _completed()
        return _completed(returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = restart.restart()
    assert result.ok
    assert result.method == "docker"
    assert ["docker", "restart", "iSponsorBlockTV"] in calls


def test_restart_falls_back_to_systemd_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    monkeypatch.setattr(shutil, "which", lambda b: f"/usr/bin/{b}" if b == "systemctl" else None)

    calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        if len(cmd) >= 3 and cmd[1] == "--user" and cmd[2] == "is-active":
            return _completed(stdout="active\n")
        if cmd[:4] == ["systemctl", "--user", "restart", "iSponsorBlockTV"]:
            return _completed()
        return _completed(returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = restart.restart()
    assert result.ok
    assert result.method == "systemd-user"
    assert ["systemctl", "--user", "restart", "iSponsorBlockTV"] in calls


def test_restart_falls_back_to_sudo_systemctl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    monkeypatch.setattr(shutil, "which", lambda b: f"/usr/bin/{b}")

    calls: list[list[str]] = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        if len(cmd) >= 3 and cmd[1] == "--user" and cmd[2] == "is-active":
            return _completed(stdout="inactive\n", returncode=3)
        if cmd[1:3] == ["-n", "true"]:
            return _completed()
        if cmd[:5] == ["sudo", "-n", "systemctl", "restart", "iSponsorBlockTV"]:
            return _completed()
        return _completed(returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = restart.restart()
    assert result.ok
    assert result.method == "systemd-system"
    assert ["sudo", "-n", "systemctl", "restart", "iSponsorBlockTV"] in calls


def test_restart_returns_no_method_when_nothing_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    monkeypatch.setattr(shutil, "which", lambda b: None)

    def fake_run(cmd, **kw):
        return _completed(returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = restart.restart()
    assert not result.ok
    assert result.method == "none"
    assert "manually" in result.detail


def test_restart_skipped_when_env_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBUI_NO_RESTART", "1")
    result = restart.restart()
    assert result.ok
    assert result.method == "skipped"
