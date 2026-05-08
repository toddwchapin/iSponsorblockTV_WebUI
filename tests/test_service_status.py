"""Unit tests for app.services.service_status — issue #4 detection chain."""
from __future__ import annotations

import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from app.services import service_status as ss


def _completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture(autouse=True)
def _service_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBUI_SERVICE_NAME", "iSponsorBlockTV")


# ----------------------- status() -----------------------

def test_status_docker_running(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "exists", lambda p: p == ss.DOCKER_SOCK)
    monkeypatch.setattr(shutil, "which", lambda b: f"/usr/bin/{b}")

    def fake_run(cmd, **kw):
        if len(cmd) >= 2 and cmd[1] == "ps":
            return _completed(stdout="iSponsorBlockTV\n")
        return _completed(returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    s = ss.status()
    assert s.method == "docker"
    assert s.running is True


def test_status_docker_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "exists", lambda p: p == ss.DOCKER_SOCK)
    monkeypatch.setattr(shutil, "which", lambda b: f"/usr/bin/{b}")

    def fake_run(cmd, **kw):
        if len(cmd) >= 2 and cmd[1] == "ps":
            return _completed(stdout="")  # no running container
        if len(cmd) >= 2 and cmd[1] == "inspect":
            return _completed(stdout="false\n")  # exists, not running
        return _completed(returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    s = ss.status()
    assert s.method == "docker"
    assert s.running is False
    assert "stopped" in s.detail


def test_status_systemd_user_active(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    monkeypatch.setattr(shutil, "which", lambda b: f"/usr/bin/{b}" if b == "systemctl" else None)

    def fake_run(cmd, **kw):
        if len(cmd) >= 3 and cmd[1] == "--user" and cmd[2] == "is-active":
            return _completed(stdout="active\n")
        return _completed(returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    s = ss.status()
    assert s.method == "systemd-user"
    assert s.running is True


def test_status_systemd_user_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    monkeypatch.setattr(shutil, "which", lambda b: f"/usr/bin/{b}" if b == "systemctl" else None)

    def fake_run(cmd, **kw):
        if len(cmd) >= 3 and cmd[1] == "--user" and cmd[2] == "is-active":
            return _completed(stdout="inactive\n", returncode=3)
        return _completed(returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    s = ss.status()
    assert s.method == "systemd-user"
    assert s.running is False


def test_status_none_when_nothing_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    monkeypatch.setattr(shutil, "which", lambda b: None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _completed(returncode=1))
    s = ss.status()
    assert s.method == "none"
    assert s.running is False


# ----------------------- tail_logs() -----------------------

def test_tail_logs_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "exists", lambda p: p == ss.DOCKER_SOCK)
    monkeypatch.setattr(shutil, "which", lambda b: f"/usr/bin/{b}")

    def fake_run(cmd, **kw):
        if cmd[1] == "ps":
            return _completed(stdout="iSponsorBlockTV\n")
        if cmd[1] == "logs":
            assert "--tail" in cmd
            return _completed(stdout="line one\nline two\n")
        return _completed(returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = ss.tail_logs(50)
    assert r.method == "docker"
    assert r.error is None
    assert r.lines == ["line one", "line two"]


def test_tail_logs_systemd_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    monkeypatch.setattr(shutil, "which", lambda b: f"/usr/bin/{b}" if b in ("systemctl", "journalctl") else None)

    def fake_run(cmd, **kw):
        if cmd[1] == "--user" and cmd[2] == "is-active":
            return _completed(stdout="active\n")
        if cmd[1] == "--user" and cmd[2] == "-u":
            return _completed(stdout="2026-05-08 a\n2026-05-08 b\n")
        return _completed(returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = ss.tail_logs(10)
    assert r.method == "systemd-user"
    assert r.error is None
    assert r.lines == ["2026-05-08 a", "2026-05-08 b"]


def test_tail_logs_sudo_journalctl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    monkeypatch.setattr(
        shutil, "which",
        lambda b: f"/usr/bin/{b}" if b in ("sudo", "journalctl") else None,
    )

    def fake_run(cmd, **kw):
        if cmd[1:3] == ["-n", "true"]:
            return _completed()
        # systemd_system_state probe: sudo -n systemctl is-active
        if "systemctl" in cmd and "is-active" in cmd:
            return _completed(returncode=1)
        if cmd[1] == "-n" and cmd[2] == "journalctl":
            return _completed(stdout="x\ny\n")
        return _completed(returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    r = ss.tail_logs(5)
    assert r.method == "systemd-system"
    assert r.error is None
    assert r.lines == ["x", "y"]


def test_tail_logs_none_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    monkeypatch.setattr(shutil, "which", lambda b: None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _completed(returncode=1))
    r = ss.tail_logs(50)
    assert r.method == "none"
    assert r.error
    assert r.lines == []


def test_tail_logs_clamps_n(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    monkeypatch.setattr(shutil, "which", lambda b: None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _completed(returncode=1))
    # Should not raise on absurd input.
    assert ss.tail_logs(-1).method == "none"
    assert ss.tail_logs(10**9).method == "none"
    assert ss.tail_logs("not a number").method == "none"  # type: ignore[arg-type]
