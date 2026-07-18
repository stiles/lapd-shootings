"""Transcript retrieval with resumable, structured cache records."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from http.client import IncompleteRead
from pathlib import Path
from typing import Any

import urllib3
from requests import Session
from requests.exceptions import ChunkedEncodingError, RequestException, Timeout
from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    IpBlocked,
    RequestBlocked,
    VideoUnplayable,
    YouTubeDataUnparsable,
    YouTubeTranscriptApi,
)

from .storage import write_json

TranscriptCache = dict[str, dict[str, Any]]


class TimeoutSession(Session):
    """Session that applies a default timeout to every request.

    Without a timeout, a hung proxy connection blocks the pipeline
    indefinitely, since requests waits forever by default.
    """

    def __init__(self, timeout: float) -> None:
        super().__init__()
        self.timeout = timeout

    def request(self, *args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("timeout", self.timeout)
        return super().request(*args, **kwargs)


def transcript_client(
    use_proxy: bool, residential: bool = False, timeout: float = 120.0
) -> YouTubeTranscriptApi:
    """Create a transcript client, optionally using the ScrapeOps proxy port."""
    session = TimeoutSession(timeout)
    if not use_proxy:
        return YouTubeTranscriptApi(http_client=session)

    proxy_key = os.environ.get("SCRAPE_PROXY_KEY")
    if not proxy_key:
        message = "Set SCRAPE_PROXY_KEY or use --no-proxy to fetch transcripts."
        raise RuntimeError(message)

    # Flags are passed through the proxy username, e.g. scrapeops.residential=true.
    # Residential requests cost 10 API credits instead of 1.
    username = "scrapeops.residential=true" if residential else "scrapeops"
    proxy_url = f"http://{username}:{proxy_key}@proxy.scrapeops.io:5353"

    session.proxies = {"http": proxy_url, "https": proxy_url}
    # The ScrapeOps proxy port re-signs TLS, so certificate checks must be off.
    session.verify = False
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return YouTubeTranscriptApi(http_client=session)


def fetch_transcripts(
    video_ids: Iterable[str],
    cache: TranscriptCache,
    cache_path: str,
    *,
    client: YouTubeTranscriptApi,
    passes: int = 5,
    batch_size: int = 25,
    sleep_seconds: float = 1.0,
    retry_delay: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> TranscriptCache:
    """Fetch uncached transcripts and retain transient failures for later retries."""
    path = Path(cache_path)
    ids = list(dict.fromkeys(video_ids))
    network_failed_ids: set[str] = set()
    for pass_number in range(1, passes + 1):
        pending = [
            video_id
            for video_id in ids
            if (
                cache.get(video_id, {}).get("status") in (None, "retryable")
                and video_id not in network_failed_ids
            )
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
                cache[video_id] = _retryable_record(error, previous_attempts)
            except (Timeout, ChunkedEncodingError) as error:
                # The proxy sometimes stalls on a single request; the next
                # attempt usually goes through, so retry within this run.
                cache[video_id] = _retryable_record(error, previous_attempts)
            except (VideoUnplayable, YouTubeDataUnparsable) as error:
                # The proxy occasionally serves a garbled watch page that
                # looks like an unplayable video; treat it as transient.
                cache[video_id] = _retryable_record(error, previous_attempts)
            except (RequestException, IncompleteRead, OSError) as error:
                cache[video_id] = _retryable_record(error, previous_attempts)
                network_failed_ids.add(video_id)
            except CouldNotRetrieveTranscript as error:
                cache[video_id] = {
                    "status": "unavailable",
                    "text": None,
                    "error": type(error).__name__,
                    "attempts": previous_attempts + 1,
                    "retrieved_at": _now(),
                }

            record = cache[video_id]
            outcome = record["error"] or record["status"]
            print(f"{index}/{len(pending)} {video_id}: {outcome}", flush=True)
            if index % batch_size == 0:
                write_json(path, cache)
            if sleep_seconds:
                sleep(sleep_seconds)
        write_json(path, cache)
        retryable_ids = [
            video_id
            for video_id in ids
            if (
                cache.get(video_id, {}).get("status") == "retryable"
                and video_id not in network_failed_ids
            )
        ]
        if pass_number < passes and retryable_ids:
            backoff = retry_delay * (2 ** (pass_number - 1))
            print(f"Waiting {backoff:g} seconds before retrying blocked requests")
            sleep(backoff)
    return cache


def fetch_age_restricted(
    video_ids: Iterable[str],
    cache: TranscriptCache,
    cache_path: str,
    *,
    browser: str,
    sleep_seconds: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
) -> TranscriptCache:
    """Fetch transcripts with yt-dlp using a signed-in browser session.

    Age-restricted videos only render caption data for logged-in requests,
    so this fetcher borrows YouTube cookies from a local browser profile.
    Requests go directly to YouTube (no proxy), since pairing account
    cookies with rotating proxy IPs tends to trip YouTube's abuse checks.
    """
    import yt_dlp

    path = Path(cache_path)
    ids = list(dict.fromkeys(video_ids))
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "cookiesfrombrowser": (browser,),
        # Captions are all that matters here. Age-restricted videos often
        # expose no playable video formats even when signed in, and without
        # this flag extraction fails before the caption data is returned.
        "ignore_no_formats_error": True,
    }
    ytdlp_errors = (
        yt_dlp.utils.DownloadError,
        yt_dlp.networking.exceptions.RequestError,
        json.JSONDecodeError,
    )
    with yt_dlp.YoutubeDL(options) as downloader:
        for index, video_id in enumerate(ids, start=1):
            previous_attempts = cache.get(video_id, {}).get("attempts", 0)
            try:
                text = _fetch_ytdlp_captions(downloader, video_id)
            except ytdlp_errors as error:
                cache[video_id] = {
                    "status": "unavailable",
                    "text": None,
                    "error": f"yt-dlp: {_short_error(error)}",
                    "attempts": previous_attempts + 1,
                    "retrieved_at": _now(),
                }
            else:
                cache[video_id] = {
                    "status": "fetched" if text else "unavailable",
                    "text": text,
                    "error": None if text else "yt-dlp: no English captions",
                    "attempts": previous_attempts + 1,
                    "retrieved_at": _now(),
                }
            record = cache[video_id]
            outcome = "fetched" if record["status"] == "fetched" else record["error"]
            print(f"{index}/{len(ids)} {video_id}: {outcome}", flush=True)
            write_json(path, cache)
            if sleep_seconds and index < len(ids):
                sleep(sleep_seconds)
    return cache


def _fetch_ytdlp_captions(downloader: Any, video_id: str) -> str | None:
    """Return English caption text for a video, or None when there is none."""
    info = downloader.extract_info(
        f"https://www.youtube.com/watch?v={video_id}", download=False
    )
    tracks = []
    for source in ("subtitles", "automatic_captions"):
        for language, formats in (info.get(source) or {}).items():
            if language == "en" or language.startswith("en-"):
                tracks.extend(formats)
                break
        if tracks:
            break
    track = next((t for t in tracks if t.get("ext") == "json3"), None)
    if track is None:
        return None
    payload = json.loads(downloader.urlopen(track["url"]).read().decode("utf-8"))
    return json3_to_text(payload)


def json3_to_text(payload: dict[str, Any]) -> str:
    """Flatten YouTube's json3 caption events into plain text."""
    pieces = []
    for event in payload.get("events", []):
        for segment in event.get("segs") or []:
            text = segment.get("utf8", "")
            if text.strip():
                pieces.append(text.strip())
    return " ".join(pieces)


def _short_error(error: Exception) -> str:
    return str(error).splitlines()[0][:200]


def _retryable_record(error: Exception, attempts: int) -> dict[str, Any]:
    """Create a cache record for failures likely to succeed on a later request."""
    return {
        "status": "retryable",
        "text": None,
        "error": type(error).__name__,
        "attempts": attempts + 1,
        "retrieved_at": _now(),
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()
