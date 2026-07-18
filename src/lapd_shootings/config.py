"""Project paths and source constants."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

LAPD_CHANNEL_ID = "UCager4c99nqQAmdiB7WMZhQ"
LAPD_CHANNEL_URL = "https://www.youtube.com/@LAPDHQ/videos"


@dataclass(frozen=True)
class ProjectPaths:
    """Locations for pipeline inputs, caches and outputs."""

    root: Path

    @property
    def raw_videos(self) -> Path:
        return self.root / "data" / "raw" / "lapd_videos.json"

    @property
    def ois_videos(self) -> Path:
        return self.root / "data" / "interim" / "lapd_ois_videos.json"

    @property
    def transcripts(self) -> Path:
        return self.root / "data" / "interim" / "lapd_ois_transcripts.json"

    @property
    def cases(self) -> Path:
        return self.root / "data" / "processed" / "lapd_ois_cases.json"

    @property
    def cases_csv(self) -> Path:
        return self.root / "data" / "processed" / "lapd_ois_cases.csv"

    @property
    def yearly_summary(self) -> Path:
        return self.root / "data" / "processed" / "lapd_ois_cases_by_year.csv"

    @property
    def chart(self) -> Path:
        return self.root / "visuals" / "lapd_ois_videos_by_year.png"

    def create_directories(self) -> None:
        """Create parent directories for all pipeline files."""
        for path in (
            self.raw_videos,
            self.ois_videos,
            self.transcripts,
            self.cases,
            self.chart,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
