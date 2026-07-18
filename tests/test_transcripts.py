from pathlib import Path

from requests.exceptions import ProxyError

from lapd_shootings.storage import read_json
from lapd_shootings.transcripts import fetch_transcripts, json3_to_text


class FakeTranscript:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeClient:
    def __init__(self) -> None:
        self.requests: list[str] = []

    def fetch(self, video_id: str) -> list[FakeTranscript]:
        self.requests.append(video_id)
        return [FakeTranscript(f"Transcript for {video_id}")]


class FlakyClient(FakeClient):
    def fetch(self, video_id: str) -> list[FakeTranscript]:
        self.requests.append(video_id)
        if len(self.requests) == 1:
            raise ProxyError("proxy reset")
        return [FakeTranscript(f"Transcript for {video_id}")]


def test_fetch_transcripts_resumes_and_persists_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "transcripts.json"
    cache = {
        "unavailable": {
            "status": "unavailable",
            "text": None,
            "error": "NoTranscript",
            "attempts": 1,
        }
    }
    client = FakeClient()

    result = fetch_transcripts(
        ["new", "unavailable"],
        cache,
        str(cache_path),
        client=client,  # type: ignore[arg-type]
        passes=2,
        batch_size=1,
        sleep_seconds=0,
    )

    assert client.requests == ["new"]
    assert result["new"]["status"] == "fetched"
    assert result["new"]["text"] == "Transcript for new"
    assert read_json(cache_path, {}) == result


def test_json3_to_text_flattens_caption_events() -> None:
    payload = {
        "events": [
            {"segs": [{"utf8": "Hello, my name is"}, {"utf8": " Captain"}]},
            {"segs": [{"utf8": "\n"}]},
            {"aAppend": 1},
            {"segs": [{"utf8": "Kelly Monise."}]},
        ]
    }
    assert json3_to_text(payload) == "Hello, my name is Captain Kelly Monise."


def test_fetch_transcripts_defers_network_failures_until_next_command(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "transcripts.json"
    client = FlakyClient()
    sleeps: list[float] = []

    result = fetch_transcripts(
        ["video"],
        {},
        str(cache_path),
        client=client,  # type: ignore[arg-type]
        passes=2,
        batch_size=1,
        sleep_seconds=0,
        retry_delay=2,
        sleep=sleeps.append,
    )

    assert client.requests == ["video"]
    assert result["video"]["status"] == "retryable"
    assert result["video"]["error"] == "ProxyError"
    assert result["video"]["attempts"] == 1
    assert sleeps == []
