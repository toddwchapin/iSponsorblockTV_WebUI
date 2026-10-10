"""LAN auto-discovery of YouTube TV devices via SSDP + DIAL (issue #3).

Reimplements the discovery half of upstream `iSponsorBlockTV.dial_client`
rather than importing it, for the same reason `services/pairing.py` talks to
the YouTube Lounge API directly instead of constructing a full upstream
`ApiHelper`: upstream's `dial_client.find_youtube_app`/`discover()` are
written to take an `ApiHelper` instance so they can call
`api_helper.pair_with_code` when a passive query doesn't yield a screen ID —
the WebUI has no `ApiHelper` and doesn't want the config/skip-logic baggage
that comes with constructing one. `pair_with_code` from `services/pairing.py`
does the exact same job standalone, so it's reused here instead. The overall
algorithm (M-SEARCH -> per-device DIAL probe -> launch-and-pair fallback) is
ported close to verbatim from upstream, since it's the proven-working shape.

Uses `ssdp` (SSDP M-SEARCH client) and `xmltodict` (DIAL device-description
XML parsing) — same libraries upstream uses. HTTP calls to the discovered
device use `httpx` (already a WebUI dependency) instead of upstream's
`aiohttp`, to avoid adding a second async HTTP client library.

A LAN scan spans several HTTP requests (start, then poll until done), so
results live in a module-level `ScanState` singleton rather than being
returned from a single request — consistent with this being a single-admin,
single-process tool (see `services/service_status.py` for the same shape).
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import secrets
import socket
from dataclasses import dataclass, field
from typing import Any

import httpx
import ssdp
import xmltodict
from ssdp import network

from app.services.pairing import pair_with_code

logger = logging.getLogger(__name__)

SEARCH_TARGET = "urn:dial-multiscreen-org:service:dial:1"
DISCOVERY_WINDOW = 10  # seconds spent listening for M-SEARCH responses
LAUNCH_PAIR_TIMEOUT = 20  # seconds to wait for a launched app to complete pairing
LAUNCH_PAIR_POLL_INTERVAL = 2.0


def _get_local_ip() -> str:
    """Local IP to bind the SSDP socket to (needed on multi-NIC hosts)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        s.connect(("10.254.254.254", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def _url_matches_ip(url: str, expected_ip: str) -> bool:
    """Guard against a spoofed/foreign LOCATION or application-url header."""
    try:
        host = httpx.URL(url).host
        return ipaddress.ip_address(host) == ipaddress.ip_address(expected_ip)
    except ValueError:
        return False


def _extract_screen_id(youtube_service_xml: str) -> str | None:
    try:
        data = xmltodict.parse(youtube_service_xml)
    except Exception:
        return None
    service_data = data.get("service") or {}
    additional_data = service_data.get("additionalData") or {}
    return additional_data.get("screenId")


class _Handler(ssdp.aio.SSDP):
    """Collects (LOCATION, sender IP) pairs from M-SEARCH responses."""

    def __init__(self) -> None:
        super().__init__()
        self.devices_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

    def __call__(self) -> _Handler:
        """Makes the instance usable as its own protocol_factory for
        `loop.create_datagram_endpoint()`, which calls the factory to obtain
        a fresh protocol object — we want it to hand back this same instance
        so callers can still read `devices_queue` off of it."""
        return self

    def response_received(self, response, addr) -> None:
        headers = {k.lower(): v for k, v in response.headers}
        location = headers.get("location")
        if location:
            self.devices_queue.put_nowait((location, addr[0]))

    def request_received(self, request, addr) -> None:
        pass  # discovery client only, never receives requests

    def connection_lost(self, exc) -> None:
        pass


async def _find_youtube_app(
    client: httpx.AsyncClient, location: str, expected_ip: str
) -> dict[str, Any] | None:
    """Probe one DIAL device: confirm it's YouTube-capable and get a screen ID.

    Ported from upstream `iSponsorBlockTV.dial_client.find_youtube_app`.
    """
    if not _url_matches_ip(location, expected_ip):
        logger.debug("Ignoring LOCATION from %s with mismatched host: %s", expected_ip, location)
        return None

    try:
        resp = await client.get(location)
    except httpx.HTTPError:
        return None
    app_url = resp.headers.get("application-url")
    if not app_url or not _url_matches_ip(app_url, expected_ip):
        return None
    try:
        data = xmltodict.parse(resp.text)
        name = data["root"]["device"]["friendlyName"]
    except Exception:
        return None

    youtube_url = app_url.rstrip("/") + "/YouTube"
    probe_headers = {"Origin": "https://www.youtube.com"}
    try:
        resp = await client.get(youtube_url, headers=probe_headers)
        screen_id = _extract_screen_id(resp.text)
        if screen_id:
            return {"screen_id": screen_id, "name": name, "offset": 0}
    except httpx.HTTPError:
        pass

    # No screen ID from a passive query (app not running / never paired with
    # this WebUI before) — launch it with a generated pairing code, the same
    # way `iSponsorBlockTV --setup`'s LAN scan does, then pair with that code
    # ourselves.
    pairing_code = "".join(str(secrets.randbelow(10)) for _ in range(12))
    launch_headers = {
        "Origin": "https://www.youtube.com",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        resp = await client.post(
            youtube_url,
            headers=launch_headers,
            data={"pairingCode": pairing_code, "theme": "cl"},
        )
    except httpx.HTTPError:
        return None
    if not resp.headers.get("location"):
        return None

    logger.debug("Launched YouTube app on %s, waiting for it to pair...", name)
    attempts = max(int(LAUNCH_PAIR_TIMEOUT / LAUNCH_PAIR_POLL_INTERVAL), 1)
    for _ in range(attempts):
        await asyncio.sleep(LAUNCH_PAIR_POLL_INTERVAL)
        try:
            device = await pair_with_code(pairing_code)
        except Exception:
            logger.debug("Pairing poll failed for %s, will retry", name, exc_info=True)
            continue
        if device:
            return {"screen_id": device.screen_id, "name": name, "offset": 0}
    return None


async def _process_devices(
    handler: _Handler,
    client: httpx.AsyncClient,
    pending_tasks: set[asyncio.Task[Any]],
    result_queue: asyncio.Queue[dict[str, Any]],
    discovery_complete: asyncio.Event,
    seen: set[str],
) -> None:
    while not discovery_complete.is_set() or not handler.devices_queue.empty() or pending_tasks:
        try:
            location, ip = await asyncio.wait_for(handler.devices_queue.get(), timeout=0.5)
            task = asyncio.create_task(_find_youtube_app(client, location, ip))
            pending_tasks.add(task)
        except asyncio.TimeoutError:
            pass

        done = {t for t in pending_tasks if t.done()}
        for task in done:
            pending_tasks.discard(task)
            try:
                device = await task
            except Exception:
                device = None
            if device and device["screen_id"] not in seen:
                seen.add(device["screen_id"])
                await result_queue.put(device)


async def discover():
    """Yield discovered YouTube TV devices as dicts (screen_id, name, offset).

    Single discovery cycle: sends one M-SEARCH, listens for
    `DISCOVERY_WINDOW` seconds, validates (and if needed, pairs with) every
    DIAL device that responds, and yields each as it completes.
    """
    handler = _Handler()
    family, _ = network.get_best_family(None, network.PORT)
    loop = asyncio.get_running_loop()
    local_ip = _get_local_ip()
    transport, _ = await loop.create_datagram_endpoint(
        handler, family=family, local_addr=(local_ip, None)
    )
    target = (network.MULTICAST_ADDRESS_IPV4, network.PORT)
    search_request = ssdp.messages.SSDPRequest(
        "M-SEARCH",
        headers={
            "HOST": f"{target[0]}:{target[1]}",
            "MAN": '"ssdp:discover"',
            "MX": "3",
            "ST": SEARCH_TARGET,
        },
    )

    seen: set[str] = set()
    pending_tasks: set[asyncio.Task[Any]] = set()
    result_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    discovery_complete = asyncio.Event()

    async def _send_and_wait() -> None:
        search_request.sendto(transport, target)
        await asyncio.sleep(DISCOVERY_WINDOW)
        discovery_complete.set()

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            search_task = asyncio.create_task(_send_and_wait())
            process_task = asyncio.create_task(
                _process_devices(
                    handler, client, pending_tasks, result_queue, discovery_complete, seen
                )
            )
            try:
                while True:
                    try:
                        device = await asyncio.wait_for(result_queue.get(), timeout=1.0)
                        yield device
                    except asyncio.TimeoutError:
                        if (
                            discovery_complete.is_set()
                            and result_queue.empty()
                            and not pending_tasks
                        ):
                            break
            finally:
                search_task.cancel()
                process_task.cancel()
                for t in (search_task, process_task):
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass
    finally:
        transport.close()


@dataclass
class ScanState:
    scanning: bool = False
    devices: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    # How many of `devices` have already been sent to a client as rendered
    # HTML (either a full-page render or a prior poll's OOB append) — see
    # take_new_devices()/mark_all_delivered() below. `devices` only ever
    # grows during a scan, so this is a simple watermark rather than a set.
    rendered_count: int = 0


_state = ScanState()
_lock = asyncio.Lock()


def get_state() -> ScanState:
    return _state


def mark_all_delivered() -> None:
    """Call after a full render of `devices` (page load, scan start) so the
    next poll only sends what's actually new."""
    _state.rendered_count = len(_state.devices)


def take_new_devices() -> list[dict[str, Any]]:
    """Devices discovered since the last full render or poll — for the poll
    endpoint to append via OOB swap instead of re-rendering the whole list
    (which would blow away an in-progress edit on an already-added row)."""
    new = _state.devices[_state.rendered_count :]
    _state.rendered_count = len(_state.devices)
    return new


async def start_scan() -> ScanState:
    """Kick off a background scan if one isn't already running (idempotent)."""
    async with _lock:
        if _state.scanning:
            return _state
        _state.scanning = True
        _state.devices = []
        _state.error = None
        _state.rendered_count = 0
        asyncio.create_task(_run_scan())
    return _state


async def _run_scan() -> None:
    try:
        async for device in discover():
            _state.devices.append(device)
    except Exception as e:
        logger.exception("LAN scan failed")
        _state.error = f"Scan failed: {e}"
    finally:
        _state.scanning = False
