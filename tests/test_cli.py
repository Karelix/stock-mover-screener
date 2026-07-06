import csv
import io

from stock_mover_screener import cli


BASE_RECORD = {
    "symbol": "HYPE",
    "country": "US",
    "security_type": "common_stock",
    "price": "12.0",
    "market_cap": "250000000",
    "average_dollar_volume": "12000000",
    "premarket_price": "12.0",
    "previous_close": "10.0",
    "premarket_open": "11.2",
    "premarket_volume": "200000",
    "average_premarket_volume": "50000",
    "atr_14_pct": "5.0",
    "premarket_bid": "11.95",
    "premarket_ask": "12.05",
    "float_shares": "5000000",
    "revenue_ttm": "500000",
    "prior_year_revenue": "1000000",
    "net_income": "-5000000",
    "operating_cash_flow": "-4000000",
    "free_cash_flow": "-6000000",
    "cash_and_equivalents": "2000000",
    "current_ratio": "0.7",
    "total_debt": "30000000",
    "total_equity": "10000000",
    "active_shelf_registration": "true",
    "recent_offering": "true",
    "atm_offering": "true",
    "warrants_outstanding": "true",
    "convertible_debt": "true",
    "shares_outstanding_growth_pct": "75.0",
    "offering_count_12m": "3",
    "headlines": (
        "Company announces AI partnership with unnamed partner; "
        "No financial terms disclosed; Reddit traders cite short squeeze"
    ),
    "social_mentions": "900",
    "average_social_mentions": "100",
    "headline_count_today": "4",
    "average_headline_count": "1",
    "short_interest_pct_float": "45.0",
    "days_to_cover": "7.0",
    "borrow_fee_pct": "120.0",
    "hard_to_borrow": "true",
    "borrow_available_shares": "0",
    "halts_count": "3",
    "call_volume_ratio": "5.0",
}


def _write_records(path, records):
    fieldnames = sorted({key for record in records for key in record})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def test_scan_csv_returns_summary_rows_for_passing_candidates(tmp_path):
    csv_path = tmp_path / "input.csv"
    etf = {**BASE_RECORD, "symbol": "ETFZ", "security_type": "etf"}
    _write_records(csv_path, [etf, BASE_RECORD])

    rows = cli.scan_csv(csv_path)

    assert [row["symbol"] for row in rows] == ["HYPE"]
    assert rows[0]["final_label"] == "Too Dangerous"
    assert rows[0]["squeeze_level"] == "extreme"


def test_main_writes_output_csv(tmp_path):
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "results.csv"
    _write_records(input_path, [BASE_RECORD])

    stderr = io.StringIO()
    exit_code = cli.main(
        ["scan", str(input_path), "--output", str(output_path)],
        stderr=stderr,
    )

    assert exit_code == 0
    assert "Wrote 1 candidate" in stderr.getvalue()
    with output_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["symbol"] == "HYPE"
    assert rows[0]["final_label"] == "Too Dangerous"


def test_main_prints_csv_to_stdout_when_output_is_omitted(tmp_path):
    input_path = tmp_path / "input.csv"
    _write_records(input_path, [BASE_RECORD])

    stdout = io.StringIO()
    exit_code = cli.main(["scan", str(input_path)], stdout=stdout)

    assert exit_code == 0
    rows = list(csv.DictReader(io.StringIO(stdout.getvalue())))
    assert rows[0]["symbol"] == "HYPE"
