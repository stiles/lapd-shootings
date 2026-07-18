"""Parse OIS video metadata and transcript text into analysis tables."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import pandas as pd

CASE_NUMBER_PATTERN = re.compile(r"\(([A-Z]{2,3}[\s-]?\d+[-–]\d{2})\)")
INCIDENT_DATE_PATTERN = re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4})")
DEFAULT_PATTERNS = {"ghost_gun": r"ghost[\s-]?gun"}


def parse_incident_date(title: str) -> str | None:
    """Extract an ISO date from an OIS title when one is present."""
    match = INCIDENT_DATE_PATTERN.search(title)
    if not match:
        return None
    value = match.group(1)
    for date_format in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def parse_cases(
    videos: list[dict[str, Any]],
    transcripts: Mapping[str, Mapping[str, Any]],
    patterns: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Join OIS videos to transcripts and calculate configured text matches."""
    frame = pd.DataFrame(videos).copy()
    if frame.empty:
        return pd.DataFrame()

    active_patterns = patterns or DEFAULT_PATTERNS
    frame["incident_date"] = frame["title"].map(parse_incident_date)
    frame["case_number"] = frame["title"].str.extract(CASE_NUMBER_PATTERN, expand=False)
    transcript_records = frame["video_id"].map(
        lambda video_id: transcripts.get(video_id, {})
    )
    frame["transcript"] = transcript_records.map(lambda record: record.get("text"))
    frame["transcript_status"] = transcript_records.map(
        lambda record: record.get("status", "not_fetched")
    )
    frame["transcript_error"] = transcript_records.map(
        lambda record: record.get("error")
    )
    frame["has_transcript"] = frame["transcript_status"].eq("fetched")

    incident_year = pd.to_datetime(frame["incident_date"], errors="coerce").dt.year
    upload_year = pd.to_datetime(frame["published_at"], errors="coerce").dt.year
    frame["year"] = incident_year.fillna(upload_year).astype("Int64")

    transcript_text = frame["transcript"].fillna("")
    for name, pattern in active_patterns.items():
        compiled = re.compile(pattern, re.IGNORECASE)
        frame[f"mentions_{name}"] = transcript_text.str.contains(compiled, na=False)
        frame[f"{name}_mentions"] = transcript_text.str.count(compiled)
    return frame


def summarize_by_year(cases: pd.DataFrame) -> pd.DataFrame:
    """Return annual OIS and ghost-gun mention counts."""
    required_columns = {"year", "video_id", "mentions_ghost_gun"}
    if cases.empty or not required_columns.issubset(cases.columns):
        return pd.DataFrame(
            columns=["year", "cases", "ghost_gun_cases", "ghost_gun_share"]
        )
    summary = (
        cases.dropna(subset=["year"])
        .groupby("year", as_index=False)
        .agg(
            cases=("video_id", "count"),
            ghost_gun_cases=("mentions_ghost_gun", "sum"),
        )
    )
    summary["ghost_gun_share"] = (summary["ghost_gun_cases"] / summary["cases"]).round(
        3
    )
    return summary
