# LAPD shooting videos

This project fetches Los Angeles Police Department YouTube uploads, identifies
officer-involved shooting (OIS) briefing videos and analyzes their caption
transcripts.

## Setup

Requires Python 3.11 or later.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install --editable ".[dev]"
```

Set a YouTube Data API key:

```sh
export YOUTUBE_KEY="your-key"
```

Transcript fetching uses the ScrapeOps proxy port by default because YouTube
can block repeated caption requests. Set its key before fetching:

```sh
export SCRAPE_PROXY_KEY="your-key"
```

Datacenter proxies cost 1 API credit per request. Add `--residential` to route
requests through residential IP pools at 10 credits per request if datacenter
requests get blocked. You can also fetch directly without a proxy with
`--no-proxy`. Direct requests may be blocked or rate-limited.

Many LAPD critical incident videos are age-restricted, and YouTube only serves
their captions to logged-in sessions. To fetch those transcripts, sign in to
YouTube in a browser and pass that browser's name so yt-dlp can reuse its
session cookies:

```sh
lapd-shootings fetch-transcripts --cookies-from-browser chrome
```

These requests go directly to YouTube from your IP, not through the proxy.
Automated fetching with account cookies can violate YouTube's terms of
service and may put the account at risk, so consider a secondary account. On
macOS, reading Chrome cookies triggers a keychain permission prompt.

## Usage

Run every stage:

```sh
lapd-shootings run
```

Run a stage on its own:

```sh
lapd-shootings fetch-videos
lapd-shootings fetch-transcripts
lapd-shootings parse
lapd-shootings visualize
```

Use `--dry-run` before a command to list its outputs without reading
credentials or making network requests:

```sh
lapd-shootings --dry-run run
```

Use `--limit 25` with `fetch-videos` or `run` to test a smaller catalog. The
transcript command saves its cache after each batch, preserves fetched and
unavailable records and retries blocked records on each new command
invocation.

## Outputs

- `data/raw/lapd_videos.json`: all fetched public uploads
- `data/interim/lapd_ois_videos.json`: uploads whose titles contain `OIS`
- `data/interim/lapd_ois_transcripts.json`: transcript cache and retrieval
  status
- `data/processed/lapd_ois_cases.json`: video-level data including transcript
  text
- `data/processed/lapd_ois_cases.csv`: video-level data without transcript text
- `data/processed/lapd_ois_cases_by_year.csv`: annual OIS and ghost-gun counts
- `visuals/lapd_ois_videos_by_year.png`: annual stacked bar chart

## Notes on the data

The LAPD channel began posting critical incident briefing videos in 2018, so
these records do not represent the department's complete OIS history. One
video may cover multiple incidents and some incidents may have no posted
video. YouTube captions may be auto-generated and contain transcription
errors.

The current `ghost gun` finding matches `ghost gun` and `ghost-gun` in
transcript text. It signals a narration match, not a verified incident
attribute.
