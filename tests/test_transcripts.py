from pathlib import Path

from lapd_shootings.storage import read_json
from lapd_shootings.transcripts import fetch_transcripts


class FakeTranscript:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeClient:
    def __init__(self) -> None:
        self.requests: list[str] = []

    def fetch(self, video_id: str) -> list[FakeTranscript]:
        self.requests.append(video_id)
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
