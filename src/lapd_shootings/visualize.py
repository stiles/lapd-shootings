"""Charts for parsed LAPD OIS briefing data."""

from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd


def save_annual_chart(cases: pd.DataFrame, output_path: Path) -> None:
    """Save a stacked annual OIS chart as a PNG."""
    if cases.empty:
        raise ValueError("Cannot create a chart without parsed OIS cases.")

    chart_data = cases.assign(
        category=cases["mentions_ghost_gun"].map(
            {True: "Mentions ghost gun", False: "No mention"}
        )
    )
    chart = (
        alt.Chart(chart_data)
        .mark_bar()
        .encode(
            x=alt.X("year:O", title=""),
            y=alt.Y("count():Q", title="Videos"),
            color=alt.Color(
                "category:N",
                title="",
                scale=alt.Scale(
                    domain=["No mention", "Mentions ghost gun"],
                    range=["#cccccc", "#d95f02"],
                ),
            ),
        )
        .properties(
            title="LAPD officer-involved shooting briefing videos, by year",
            width=650,
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    chart.save(output_path)
