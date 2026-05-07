"""Pair a YouTube TV with a 12-digit code from Settings → Link with TV code.

Talks directly to the YouTube Lounge pairing endpoint — same call upstream
`ApiHelper.pair_with_code` makes, but without dragging in upstream's full
ApiHelper construction (which needs an event-loop'd config).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import httpx

PAIR_URL = "https://www.youtube.com/api/lounge/pairing/get_screen"


@dataclass
class PairedDevice:
    screen_id: str
    name: str
    lounge_token: str


class PairingError(RuntimeError):
    pass


def _normalize(code: str) -> str:
    return re.sub(r"[\s-]", "", code or "")


async def pair_with_code(code: str) -> Optional[PairedDevice]:
    normalized = _normalize(code)
    if not normalized.isdigit() or len(normalized) != 12:
        raise PairingError("Pairing code must be 12 digits.")
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.post(PAIR_URL, data={"pairing_code": normalized})
        except httpx.HTTPError as e:
            raise PairingError(f"Pairing request failed: {e}") from e
    if resp.status_code != 200:
        raise PairingError(
            "YouTube rejected the pairing code. "
            "Make sure it is shown right now on the TV (Settings → Link with TV code)."
        )
    try:
        body = resp.json()
    except ValueError as e:
        raise PairingError(f"YouTube returned non-JSON response: {e}") from e
    screen = (body or {}).get("screen") or {}
    screen_id = screen.get("screenId")
    if not screen_id:
        raise PairingError("Pairing succeeded but no screenId returned.")
    return PairedDevice(
        screen_id=screen_id,
        name=screen.get("name") or "YouTube on TV",
        lounge_token=screen.get("loungeToken", ""),
    )
