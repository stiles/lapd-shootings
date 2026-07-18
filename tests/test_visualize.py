from pathlib import Path

import pandas as pd

from lapd_shootings.visualize import save_annual_chart


def test_save_annual_chart_writes_png(tmp_path: Path) -> None:
    output_path = tmp_path / "chart.png"
    cases = pd.DataFrame(
        {
            "year": [2024, 2024],
            "mentions_ghost_gun": [False, True],
        }
    )

    save_annual_chart(cases, output_path)

    assert output_path.is_file()
    assert output_path.stat().st_size > 0
