import csv
import io

from stock_mover_screener.runner import (
    scan_csv_text,
    summary_rows_to_csv,
)
from tests.test_cli import BASE_RECORD


def test_scan_csv_text_keeps_summary_and_full_details():
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=BASE_RECORD.keys())
    writer.writeheader()
    writer.writerow(BASE_RECORD)

    result = scan_csv_text(handle.getvalue())

    assert [row["symbol"] for row in result.summary_rows] == ["HYPE"]
    assert result.summary_rows[0]["final_label"] == "Too Dangerous"
    assert result.full_details[0]["label"]["final_label"] == "Too Dangerous"
    assert result.full_details[0]["squeeze"]["risk_level"] == "extreme"


def test_summary_rows_to_csv_uses_stable_field_order():
    csv_text = summary_rows_to_csv(
        [
            {
                "symbol": "HYPE",
                "final_label": "Too Dangerous",
                "confidence": 95,
            }
        ]
    )

    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert rows[0]["symbol"] == "HYPE"
    assert rows[0]["final_label"] == "Too Dangerous"
    assert "premarket_move_pct" in rows[0]
