"""YouTube Data API v3 channel search."""
from __future__ import annotations

from dataclasses import dataclass

import httpx

YT_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


@dataclass
class ChannelHit:
    id: str
    name: str
    thumbnail: str


class ChannelSearchError(RuntimeError):
    """Raised when YouTube API returns an error or is unreachable."""


async def search(api_key: str, query: str, max_results: int = 6) -> list[ChannelHit]:
    if not api_key:
        raise ChannelSearchError("No YouTube API key configured.")
    if not query.strip():
        return []
    params = {
        "key": api_key,
        "part": "snippet",
        "type": "channel",
        "q": query,
        "maxResults": max_results,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(YT_SEARCH_URL, params=params)
        except httpx.HTTPError as e:
            raise ChannelSearchError(f"YouTube API request failed: {e}") from e
    if resp.status_code != 200:
        raise ChannelSearchError(
            f"YouTube API returned {resp.status_code}: {resp.text[:200]}"
        )
    data = resp.json()
    if "error" in data:
        raise ChannelSearchError(data["error"].get("message", "unknown error"))
    hits = []
    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        channel_id = item.get("id", {}).get("channelId") or snippet.get("channelId")
        if not channel_id:
            continue
        thumbs = snippet.get("thumbnails", {})
        thumb = (thumbs.get("default") or thumbs.get("medium") or {}).get("url", "")
        hits.append(
            ChannelHit(
                id=channel_id,
                name=snippet.get("channelTitle") or snippet.get("title") or channel_id,
                thumbnail=thumb,
            )
        )
    return hits
