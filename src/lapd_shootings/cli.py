"""Command-line interface for the LAPD shooting video pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .config import ProjectPaths
from .parse import parse_cases, summarize_by_year
from .storage import read_json, write_json
from .transcripts import fetch_age_restricted, fetch_transcripts, transcript_client
from .visualize import save_annual_chart
from .youtube import fetch_uploads, filter_ois_videos, require_youtube_key


def build_parser() -> argparse.ArgumentParser:
    """Build the command parser."""
    parser = argparse.ArgumentParser(
        description="Fetch and analyze LAPD OIS briefing videos."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help=(
            "Project directory containing data and visuals "
            "(default: current directory)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command's outputs without reading credentials or APIs.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    fetch_videos_parser = commands.add_parser(
        "fetch-videos", help="Fetch video metadata and select OIS briefings."
    )
    fetch_videos_parser.add_argument(
        "--limit", type=int, help="Keep only the first N fetched videos."
    )

    fetch_transcripts_parser = commands.add_parser(
        "fetch-transcripts", help="Fetch and cache OIS video transcripts."
    )
    _add_transcript_options(fetch_transcripts_parser)

    commands.add_parser("parse", help="Join video metadata and transcript records.")
    commands.add_parser("visualize", help="Generate charts from parsed cases.")

    run_parser = commands.add_parser("run", help="Run every pipeline stage.")
    run_parser.add_argument(
        "--limit", type=int, help="Keep only the first N fetched videos."
    )
    _add_transcript_options(run_parser)
    return parser


def _add_transcript_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Fetch directly instead of using the ScrapeOps proxy.",
    )
    parser.add_argument(
        "--residential",
        action="store_true",
        help="Route proxy requests through residential IP pools (10 credits each).",
    )
    parser.add_argument(
        "--passes", type=int, default=5, help="Maximum passes for blocked videos."
    )
    parser.add_argument(
        "--batch-size", type=int, default=25, help="Records to fetch before saving."
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds to wait after each transcript request.",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=5.0,
        help="Initial seconds to wait before retrying transient request failures.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Seconds before an unresponsive transcript request is abandoned.",
    )
    parser.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help=(
            "Retry age-restricted videos with yt-dlp, using the YouTube login "
            "session from this browser (chrome, safari, firefox, ...)."
        ),
    )


def run_fetch_videos(paths: ProjectPaths, limit: int | None = None) -> None:
    """Fetch the channel catalog and write raw and OIS records."""
    videos = fetch_uploads(require_youtube_key())
    if limit is not None:
        videos = videos[:limit]
    ois_videos = filter_ois_videos(videos)
    write_json(paths.raw_videos, videos)
    write_json(paths.ois_videos, ois_videos)
    print(f"Saved {len(videos)} videos and {len(ois_videos)} OIS videos.")


def run_fetch_transcripts(args: argparse.Namespace, paths: ProjectPaths) -> None:
    """Fetch transcripts for the saved OIS catalog."""
    videos = _require_records(paths.ois_videos, "Run fetch-videos first.")
    cache = read_json(paths.transcripts, {})
    fetch_transcripts(
        (video["video_id"] for video in videos),
        cache,
        str(paths.transcripts),
        client=transcript_client(
            use_proxy=not args.no_proxy,
            residential=args.residential,
            timeout=args.timeout,
        ),
        passes=args.passes,
        batch_size=args.batch_size,
        sleep_seconds=args.delay,
        retry_delay=args.retry_delay,
    )
    if args.cookies_from_browser:
        age_restricted = [
            video["video_id"]
            for video in videos
            if str(cache.get(video["video_id"], {}).get("error", "")).startswith(
                ("AgeRestricted", "yt-dlp: ERROR", "yt-dlp: HTTP")
            )
        ]
        if age_restricted:
            print(
                f"Retrying {len(age_restricted)} age-restricted videos with "
                f"{args.cookies_from_browser} cookies"
            )
            fetch_age_restricted(
                age_restricted,
                cache,
                str(paths.transcripts),
                browser=args.cookies_from_browser,
                sleep_seconds=max(args.delay, 5.0),
            )

    fetched = sum(record.get("status") == "fetched" for record in cache.values())
    deferred = sum(record.get("status") == "retryable" for record in cache.values())
    print(f"Cached {fetched} fetched transcripts for {len(videos)} OIS videos.")
    if deferred:
        print(
            f"Deferred {deferred} transient network or blocking failures. "
            "Run this command again after the proxy recovers."
        )


def run_parse(paths: ProjectPaths) -> None:
    """Create video-level and annual analysis outputs."""
    videos = _require_records(paths.ois_videos, "Run fetch-videos first.")
    transcripts = read_json(paths.transcripts, {})
    cases = parse_cases(videos, transcripts)
    summary = summarize_by_year(cases)
    write_json(paths.cases, _frame_to_records(cases))
    cases.drop(columns="transcript", errors="ignore").to_csv(
        paths.cases_csv, index=False
    )
    summary.to_csv(paths.yearly_summary, index=False)
    print(f"Saved {len(cases)} parsed OIS cases.")


def run_visualize(paths: ProjectPaths) -> None:
    """Create charts from parsed case data."""
    records = _require_records(paths.cases, "Run parse first.")
    save_annual_chart(pd.DataFrame(records), paths.chart)
    print(f"Saved chart to {paths.chart}.")


def _require_records(path: Path, message: str) -> list[dict[str, Any]]:
    if not path.exists():
        raise RuntimeError(message)
    records = read_json(path, [])
    if not isinstance(records, list):
        raise RuntimeError(f"Expected a list of records in {path}.")
    return records


def _frame_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def _show_dry_run(command: str, paths: ProjectPaths) -> None:
    outputs = {
        "fetch-videos": [paths.raw_videos, paths.ois_videos],
        "fetch-transcripts": [paths.transcripts],
        "parse": [paths.cases, paths.cases_csv, paths.yearly_summary],
        "visualize": [paths.chart],
        "run": [
            paths.raw_videos,
            paths.ois_videos,
            paths.transcripts,
            paths.cases,
            paths.cases_csv,
            paths.yearly_summary,
            paths.chart,
        ],
    }
    print(f"Dry run: {command} writes:")
    for path in outputs[command]:
        print(f"  {path}")


def main(argv: list[str] | None = None) -> int:
    """Run the selected command and return a shell-compatible status."""
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = ProjectPaths(args.root.resolve())
    if args.dry_run:
        _show_dry_run(args.command, paths)
        return 0

    paths.create_directories()
    try:
        if args.command == "fetch-videos":
            run_fetch_videos(paths, args.limit)
        elif args.command == "fetch-transcripts":
            run_fetch_transcripts(args, paths)
        elif args.command == "parse":
            run_parse(paths)
        elif args.command == "visualize":
            run_visualize(paths)
        elif args.command == "run":
            run_fetch_videos(paths, args.limit)
            run_fetch_transcripts(args, paths)
            run_parse(paths)
            run_visualize(paths)
    except RuntimeError as error:
        parser.error(str(error))
    return 0
