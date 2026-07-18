from lapd_shootings.parse import (
    find_divisions,
    parse_cases,
    parse_incident_date,
    parse_title_division,
    summarize_by_year,
)


def test_parse_incident_date_accepts_two_and_four_digit_years() -> None:
    assert parse_incident_date("Newton OIS 6/9/2026") == "2026-06-09"
    assert parse_incident_date("Newton OIS 6/13/26") == "2026-06-13"
    assert parse_incident_date("Newton OIS") is None


def test_parse_title_division_reads_leading_area() -> None:
    assert parse_title_division("Hollenbeck Area (Newton) OIS 6/9/2026") == "Hollenbeck"
    assert parse_title_division("77th Area OIS 1/2/24 (NRF001-24)") == "77th Street"
    assert parse_title_division("North Hollywood Division OIS") == "North Hollywood"
    assert parse_title_division("WLA Division (SWAT) OIS") == "West Los Angeles"
    assert parse_title_division("Off-Duty LAPD OIS") is None


def test_find_divisions_handles_narration_and_caption_errors() -> None:
    assert find_divisions(
        "involved shooting that occurred in the city of Los Angeles involving "
        "officers from both Hollandbeck and Newton divisions"
    ) == ["Hollenbeck", "Newton"]
    assert find_divisions(
        "officer-involved shooting that occurred in Pacific Division in the city"
    ) == ["Pacific"]
    assert find_divisions(
        "shooting that occurred in 77 Street Division in the city of Los Angeles"
    ) == ["77th Street"]
    assert find_divisions(
        "at around 12:45 p.m., Mission Patrol Division officers responded"
    ) == ["Mission"]
    # Plain words should not match without a Division/Area anchor.
    assert find_divisions("officers responded to the central mission district") == []


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
