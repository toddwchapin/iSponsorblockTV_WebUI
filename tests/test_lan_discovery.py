"""Issue #3: LAN auto-discovery via SSDP/DIAL.

Unit tests for the pure parsing/validation helpers and the per-device DIAL
probe (`_find_youtube_app`, exercised over `httpx.MockTransport` — no real
network). `discover()` itself opens a real UDP socket and sends multicast
M-SEARCH traffic, so it isn't unit tested here; it's exercised manually
against a real network (see PR description) since that's what it's for.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.services import lan_discovery
from app.services.pairing import PairedDevice

DEVICE_XML = """<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <device>
    <friendlyName>Living Room TV</friendlyName>
  </device>
</root>"""

YOUTUBE_SERVICE_XML_WITH_SCREEN = """<?xml version="1.0" encoding="UTF-8"?>
<service xmlns="urn:dial-multiscreen-org:schemas:dial">
  <name>YouTube</name>
  <options allowStop="true"/>
  <state>running</state>
  <additionalData>
    <screenId>abc123screen</screenId>
  </additionalData>
</service>"""

YOUTUBE_SERVICE_XML_NO_SCREEN = """<?xml version="1.0" encoding="UTF-8"?>
<service xmlns="urn:dial-multiscreen-org:schemas:dial">
  <name>YouTube</name>
  <options allowStop="true"/>
  <state>stopped</state>
</service>"""


@pytest.mark.asyncio
async def test_handler_is_usable_as_its_own_protocol_factory() -> None:
    """Regression: `loop.create_datagram_endpoint(handler, ...)` calls
    `handler()` to obtain a protocol instance — without `_Handler.__call__`
    that raises `TypeError: '_Handler' object is not callable` the moment a
    scan actually starts, which unit tests that only exercise
    `_find_youtube_app` over a mocked transport never hit `discover()`
    doesn't catch. Bind on loopback so this doesn't need real network."""
    handler = lan_discovery._Handler()
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        handler, local_addr=("127.0.0.1", 0)
    )
    try:
        assert protocol is handler
    finally:
        transport.close()


def test_url_matches_ip_true_for_matching_host() -> None:
    assert lan_discovery._url_matches_ip("http://192.168.1.50:8008/dial", "192.168.1.50")


def test_url_matches_ip_false_for_mismatched_host() -> None:
    """The DIAL LOCATION/application-url must point back at whoever answered
    the M-SEARCH — otherwise a malicious host could redirect us elsewhere."""
    assert not lan_discovery._url_matches_ip("http://10.0.0.9:8008/dial", "192.168.1.50")


def test_url_matches_ip_false_for_hostname() -> None:
    assert not lan_discovery._url_matches_ip("http://not-an-ip:8008/dial", "192.168.1.50")


def test_extract_screen_id_found() -> None:
    assert lan_discovery._extract_screen_id(YOUTUBE_SERVICE_XML_WITH_SCREEN) == "abc123screen"


def test_extract_screen_id_missing() -> None:
    assert lan_discovery._extract_screen_id(YOUTUBE_SERVICE_XML_NO_SCREEN) is None


def test_extract_screen_id_malformed_xml() -> None:
    assert lan_discovery._extract_screen_id("not xml at all") is None


def _client_with_transport(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


@pytest.mark.asyncio
async def test_find_youtube_app_rejects_location_from_wrong_ip() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should never make a request for a mismatched host")

    async with _client_with_transport(handler) as client:
        device = await lan_discovery._find_youtube_app(
            client, "http://10.0.0.9:8008/dial", "192.168.1.50"
        )
    assert device is None


@pytest.mark.asyncio
async def test_find_youtube_app_passive_success() -> None:
    """Device already has the YouTube app running with a screen ID — no
    launch/pair fallback needed."""

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "http://192.168.1.50:8008/dial":
            return httpx.Response(
                200,
                text=DEVICE_XML,
                headers={"application-url": "http://192.168.1.50:8008/apps/"},
            )
        if str(request.url) == "http://192.168.1.50:8008/apps/YouTube":
            assert request.method == "GET"
            return httpx.Response(200, text=YOUTUBE_SERVICE_XML_WITH_SCREEN)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async with _client_with_transport(handler) as client:
        device = await lan_discovery._find_youtube_app(
            client, "http://192.168.1.50:8008/dial", "192.168.1.50"
        )
    assert device == {"screen_id": "abc123screen", "name": "Living Room TV", "offset": 0}


@pytest.mark.asyncio
async def test_find_youtube_app_rejects_mismatched_application_url() -> None:
    """A DIAL device description that points application-url at a different
    host than the one that answered M-SEARCH is ignored."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=DEVICE_XML,
            headers={"application-url": "http://10.0.0.9:8008/apps/"},
        )

    async with _client_with_transport(handler) as client:
        device = await lan_discovery._find_youtube_app(
            client, "http://192.168.1.50:8008/dial", "192.168.1.50"
        )
    assert device is None


@pytest.mark.asyncio
async def test_find_youtube_app_launches_and_pairs_when_no_screen_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Passive query returns no screen ID -> app gets launched with a
    generated code -> we pair with that same code ourselves."""
    monkeypatch.setattr(lan_discovery, "LAUNCH_PAIR_POLL_INTERVAL", 0.001)

    launched_codes: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "http://192.168.1.50:8008/dial":
            return httpx.Response(
                200,
                text=DEVICE_XML,
                headers={"application-url": "http://192.168.1.50:8008/apps/"},
            )
        if url == "http://192.168.1.50:8008/apps/YouTube" and request.method == "GET":
            return httpx.Response(200, text=YOUTUBE_SERVICE_XML_NO_SCREEN)
        if url == "http://192.168.1.50:8008/apps/YouTube" and request.method == "POST":
            body = request.read().decode()
            code = dict(p.split("=") for p in body.split("&"))["pairingCode"]
            launched_codes.append(code)
            return httpx.Response(
                201, headers={"Location": "http://192.168.1.50:8008/apps/YouTube/run"}
            )
        raise AssertionError(f"unexpected request: {request.method} {url}")

    async def fake_pair_with_code(code: str):
        assert code == launched_codes[0]
        return PairedDevice(screen_id="paired-via-launch", name="ignored", lounge_token="tok")

    monkeypatch.setattr(lan_discovery, "pair_with_code", fake_pair_with_code)

    async with _client_with_transport(handler) as client:
        device = await lan_discovery._find_youtube_app(
            client, "http://192.168.1.50:8008/dial", "192.168.1.50"
        )
    assert device == {"screen_id": "paired-via-launch", "name": "Living Room TV", "offset": 0}
    assert len(launched_codes) == 1


@pytest.mark.asyncio
async def test_find_youtube_app_gives_up_if_launch_never_pairs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lan_discovery, "LAUNCH_PAIR_POLL_INTERVAL", 0.001)
    monkeypatch.setattr(lan_discovery, "LAUNCH_PAIR_TIMEOUT", 0.005)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "http://192.168.1.50:8008/dial":
            return httpx.Response(
                200,
                text=DEVICE_XML,
                headers={"application-url": "http://192.168.1.50:8008/apps/"},
            )
        if url == "http://192.168.1.50:8008/apps/YouTube" and request.method == "GET":
            return httpx.Response(200, text=YOUTUBE_SERVICE_XML_NO_SCREEN)
        if url == "http://192.168.1.50:8008/apps/YouTube" and request.method == "POST":
            return httpx.Response(
                201, headers={"Location": "http://192.168.1.50:8008/apps/YouTube/run"}
            )
        raise AssertionError(f"unexpected request: {request.method} {url}")

    async def fake_pair_with_code(code: str):
        return None  # TV never actually paired

    monkeypatch.setattr(lan_discovery, "pair_with_code", fake_pair_with_code)

    async with _client_with_transport(handler) as client:
        device = await lan_discovery._find_youtube_app(
            client, "http://192.168.1.50:8008/dial", "192.168.1.50"
        )
    assert device is None


@pytest.mark.asyncio
async def test_start_scan_populates_devices_and_clears_scanning_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_discover():
        yield {"screen_id": "a", "name": "TV A", "offset": 0}
        yield {"screen_id": "b", "name": "TV B", "offset": 0}

    monkeypatch.setattr(lan_discovery, "discover", fake_discover)
    monkeypatch.setattr(lan_discovery, "_state", lan_discovery.ScanState())

    state = await lan_discovery.start_scan()
    assert state.scanning is True

    for _ in range(50):
        if not lan_discovery.get_state().scanning:
            break
        await asyncio.sleep(0.02)

    final = lan_discovery.get_state()
    assert final.scanning is False
    assert final.error is None
    assert {d["screen_id"] for d in final.devices} == {"a", "b"}


@pytest.mark.asyncio
async def test_start_scan_is_idempotent_while_running(monkeypatch: pytest.MonkeyPatch) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_discover():
        started.set()
        await release.wait()
        yield {"screen_id": "only-one", "name": "TV", "offset": 0}

    monkeypatch.setattr(lan_discovery, "discover", fake_discover)
    monkeypatch.setattr(lan_discovery, "_state", lan_discovery.ScanState())

    await lan_discovery.start_scan()
    await asyncio.wait_for(started.wait(), timeout=1)

    # Calling start_scan again while the first scan is in flight must not
    # spawn a second `discover()` run (which would send duplicate M-SEARCH
    # traffic and could double-launch the YouTube app on found devices).
    state = await lan_discovery.start_scan()
    assert state.scanning is True

    release.set()
    for _ in range(50):
        if not lan_discovery.get_state().scanning:
            break
        await asyncio.sleep(0.02)

    assert [d["screen_id"] for d in lan_discovery.get_state().devices] == ["only-one"]


@pytest.mark.asyncio
async def test_start_scan_records_error_and_clears_scanning_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_discover():
        raise RuntimeError("socket bind failed")
        yield  # pragma: no cover - unreachable, makes this an async generator

    monkeypatch.setattr(lan_discovery, "discover", fake_discover)
    monkeypatch.setattr(lan_discovery, "_state", lan_discovery.ScanState())

    await lan_discovery.start_scan()
    for _ in range(50):
        if not lan_discovery.get_state().scanning:
            break
        await asyncio.sleep(0.02)

    final = lan_discovery.get_state()
    assert final.scanning is False
    assert "socket bind failed" in final.error


def test_take_new_devices_returns_only_undelivered_and_advances_watermark() -> None:
    state = lan_discovery.ScanState(
        devices=[
            {"screen_id": "a", "name": "A", "offset": 0},
            {"screen_id": "b", "name": "B", "offset": 0},
        ],
        rendered_count=1,  # "a" already delivered
    )
    lan_discovery._state = state

    new = lan_discovery.take_new_devices()
    assert [d["screen_id"] for d in new] == ["b"]
    assert state.rendered_count == 2

    # A second call with nothing new added returns an empty list.
    assert lan_discovery.take_new_devices() == []
    assert state.rendered_count == 2


def test_mark_all_delivered_sets_watermark_to_current_length() -> None:
    state = lan_discovery.ScanState(
        devices=[{"screen_id": "a", "name": "A", "offset": 0}],
        rendered_count=0,
    )
    lan_discovery._state = state

    lan_discovery.mark_all_delivered()
    assert state.rendered_count == 1
    assert lan_discovery.take_new_devices() == []


@pytest.mark.asyncio
async def test_start_scan_resets_rendered_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fresh scan must not let a stale watermark from the previous scan
    suppress re-sending devices found this time around."""

    async def fake_discover():
        return
        yield  # pragma: no cover - unreachable, makes this an async generator

    monkeypatch.setattr(lan_discovery, "discover", fake_discover)
    lan_discovery._state = lan_discovery.ScanState(
        devices=[{"screen_id": "stale", "name": "Stale", "offset": 0}],
        rendered_count=1,
    )

    await lan_discovery.start_scan()
    assert lan_discovery.get_state().rendered_count == 0
