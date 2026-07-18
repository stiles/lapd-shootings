"""YouTube Data API retrieval and OIS video filtering."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from typing import Any

from googleapiclient.discovery import build

from .config import LAPD_CHANNEL_ID

OIS_TITLE_PATTERN = re.compile(r"\bOIS\b")


def require_youtube_key() -> str:
    """Return the YouTube API key or raise a useful configuration error."""
    api_key = os.environ.get("YOUTUBE_KEY")
    if not api_key:
        message = "Set YOUTUBE_KEY to use the YouTube Data API."
        raise RuntimeError(message)
    return api_key


def fetch_uploads(
    api_key: str, channel_id: str = LAPD_CHANNEL_ID
) -> list[dict[str, Any]]:
    """Fetch metadata for every public video in a channel's upload playlist."""
    youtube = build("youtube", "v3", developerKey=api_key)
    channel_response = (
        youtube.channels().list(part="contentDetails", id=channel_id).execute()
    )
    channels = channel_response.get("items", [])
    if not channels:
        raise RuntimeError(f"YouTube channel {channel_id} was not found.")

    playlist_id = channels[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    videos: list[dict[str, Any]] = []
    page_token: str | None = None

    while True:
        page = (
            youtube.playlistItems()
            .list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=page_token,
            )
            .execute()
        )
        video_ids = [
            item["contentDetails"]["videoId"] for item in page.get("items", [])
        ]
        videos.extend(_fetch_video_details(youtube, video_ids))

        page_token = page.get("nextPageToken")
        if not page_token:
            return videos


def _fetch_video_details(
    youtube: Any, video_ids: Iterable[str]
) -> list[dict[str, Any]]:
    """Fetch the fields unavailable from playlist item responses."""
    ids = list(video_ids)
    if not ids:
        return []
    response = (
        youtube.videos()
        .list(part="snippet,statistics,contentDetails", id=",".join(ids))
        .execute()
    )
    details_by_id = {item["id"]: item for item in response.get("items", [])}
    videos = []
    for video_id in ids:
        item = details_by_id.get(video_id)
        if item is None:
            continue
        statistics = item.get("statistics", {})
        videos.append(
            {
                "video_id": video_id,
                "title": item["snippet"]["title"],
                "published_at": item["snippet"]["publishedAt"],
                "duration": item["contentDetails"]["duration"],
                "views": int(statistics.get("viewCount", 0)),
                "likes": int(statistics.get("likeCount", 0)),
                "comments": int(statistics.get("commentCount", 0)),
                "url": f"https://youtu.be/{video_id}",
            }
        )
    return videos


def filter_ois_videos(videos: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return videos whose title includes the OIS marker."""
    return [
        video
        for video in videos
        if OIS_TITLE_PATTERN.search(str(video.get("title", "")))
    ]
