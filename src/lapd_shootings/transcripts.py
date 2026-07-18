"""Transcript retrieval with resumable, structured cache records."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    IpBlocked,
    RequestBlocked,
    YouTubeTranscriptApi,
)
from youtube_transcript_api.proxies import GenericProxyConfig

from .storage import write_json

TranscriptCache = dict[str, dict[str, Any]]


def transcript_client(use_proxy: bool) -> YouTubeTranscriptApi:
    """Create a transcript client, optionally using the ScrapeOps proxy."""
    if not use_proxy:
        return YouTubeTranscriptApi()

    proxy_key = os.environ.get("SCRAPE_PROXY_KEY")
    if not proxy_key:
        message = "Set SCRAPE_PROXY_KEY or use --no-proxy to fetch transcripts."
        raise RuntimeError(message)
    proxy_url = f"http://scrapeops:{proxy_key}@residential-proxy.scrapeops.io:8181"
    proxy_config = GenericProxyConfig(http_url=proxy_url, https_url=proxy_url)
    return YouTubeTranscriptApi(proxy_config=proxy_config)


def fetch_transcripts(
    video_ids: Iterable[str],
    cache: TranscriptCache,
    cache_path: str,
    *,
    client: YouTubeTranscriptApi,
    passes: int = 5,
    batch_size: int = 25,
    sleep_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> TranscriptCache:
    """Fetch uncached transcripts, retrying only transient IP blocks."""
    path = Path(cache_path)
    ids = list(dict.fromkeys(video_ids))
    for pass_number in range(1, passes + 1):
        pending = [
            video_id
            for video_id in ids
            if cache.get(video_id, {}).get("status") in (None, "retryable")
        ]
        if not pending:
            break
        print(f"Pass {pass_number}: fetching {len(pending)} transcripts")
        for index, video_id in enumerate(pending, start=1):
            previous_attempts = cache.get(video_id, {}).get("attempts", 0)
            try:
                fetched = client.fetch(video_id)
                cache[video_id] = {
                    "status": "fetched",
                    "text": " ".join(snippet.text for snippet in fetched),
                    "error": None,
                    "attempts": previous_attempts + 1,
                    "retrieved_at": _now(),
                }
            except (RequestBlocked, IpBlocked) as error:
                cache[video_id] = {
                    "status": "retryable",
                    "text": None,
                    "error": type(error).__name__,
                    "attempts": previous_attempts + 1,
                    "retrieved_at": _now(),
                }
            except CouldNotRetrieveTranscript as error:
                cache[video_id] = {
                    "status": "unavailable",
                    "text": None,
                    "error": type(error).__name__,
                    "attempts": previous_attempts + 1,
                    "retrieved_at": _now(),
                }

            if index % batch_size == 0:
                write_json(path, cache)
                print(f"Saved {index}/{len(pending)} transcript records")
            if sleep_seconds:
                sleep(sleep_seconds)
        write_json(path, cache)
    return cache


def _now() -> str:
    return datetime.now(UTC).isoformat()
