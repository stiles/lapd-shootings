from lapd_shootings.parse import parse_cases, parse_incident_date, summarize_by_year


def test_parse_incident_date_accepts_two_and_four_digit_years() -> None:
    assert parse_incident_date("Newton OIS 6/9/2026") == "2026-06-09"
    assert parse_incident_date("Newton OIS 6/13/26") == "2026-06-13"
    assert parse_incident_date("Newton OIS") is None


def test_parse_cases_extracts_metadata_and_transcript_findings() -> None:
    videos = [
        {
            "video_id": "one",
            "title": "Newton OIS 6/9/2026 (NRF026-26)",
            "published_at": "2026-06-10T00:00:00Z",
        },
        {
            "video_id": "two",
            "title": "Central OIS (DR123-24)",
            "published_at": "2024-02-03T00:00:00Z",
        },
    ]
    transcripts = {
        "one": {
            "status": "fetched",
            "text": "A ghost gun and another ghost-gun were recovered.",
            "error": None,
        },
        "two": {"status": "unavailable", "text": None, "error": "NoTranscript"},
    }

    cases = parse_cases(videos, transcripts)

    first = cases.iloc[0]
    assert first["incident_date"] == "2026-06-09"
    assert first["case_number"] == "NRF026-26"
    assert first["year"] == 2026
    assert first["has_transcript"]
    assert first["mentions_ghost_gun"]
    assert first["ghost_gun_mentions"] == 2

    second = cases.iloc[1]
    assert second["year"] == 2024
    assert not second["has_transcript"]
    assert second["transcript_error"] == "NoTranscript"


def test_summarize_by_year_counts_cases_and_mentions() -> None:
    cases = parse_cases(
        [
            {
                "video_id": "one",
                "title": "OIS 1/1/2024",
                "published_at": "2024-01-01T00:00:00Z",
            },
            {
                "video_id": "two",
                "title": "OIS 2/1/2024",
                "published_at": "2024-02-01T00:00:00Z",
            },
        ],
        {
            "one": {"status": "fetched", "text": "ghost gun"},
            "two": {"status": "fetched", "text": "no match"},
        },
    )

    summary = summarize_by_year(cases)

    assert summary.to_dict("records") == [
        {
            "year": 2024,
            "cases": 2,
            "ghost_gun_cases": 1,
            "ghost_gun_share": 0.5,
        }
    ]
