from datetime import date

import pytest

from stock_mover_screener.providers.finra import (
    FinraApiError,
    FinraShortInterestProvider,
    parse_short_interest_file,
)


SHORT_INTEREST_TEXT = "\n".join(
    [
        "Settlement Date|Market|Issue Symbol|Issue Name|Current Short|Previous Short|Percent Change|Average Daily Share Volume|Days To Cover",
        "20260615|NMS|HYPE|Hype Corp|5,000,000|4,000,000|25.0%|1,000,000|5.0",
        "20260615|NMS|REAL|Real Corp|100,000|90,000|11.1%|500,000|0.2",
    ]
)


class FakeFinraTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, url, headers, params):
        self.calls.append((url, dict(headers), dict(params)))
        if url.endswith("/equity-short-interest/files"):
            return """
            <a href="https://cdn.finra.org/equity/otcmarket/biweekly/shrt20260615.csv">June 15, 2026</a>
            <a href="https://cdn.finra.org/equity/otcmarket/biweekly/shrt20260531.csv">May 31, 2026</a>
            """
        if url.endswith("/shrt20260615.csv"):
            return SHORT_INTEREST_TEXT
        if url.endswith("/shrt20260531.csv"):
            return "Symbol|Current Short\nOLD|1"
        raise AssertionError(f"unexpected FINRA request: {url}")


def test_parse_short_interest_file_accepts_pipe_delimited_finra_rows():
    rows = parse_short_interest_file(SHORT_INTEREST_TEXT)

    assert rows[0] == {
        "symbol": "HYPE",
        "settlement_date": "2026-06-15",
        "market": "NMS",
        "issue_name": "Hype Corp",
        "short_interest_shares": 5_000_000.0,
        "previous_short_interest_shares": 4_000_000.0,
        "short_interest_change_pct": 25.0,
        "average_daily_volume": 1_000_000.0,
        "days_to_cover": 5.0,
    }


def test_parse_short_interest_file_accepts_csv_aliases():
    text = "\n".join(
        [
            "Symbol,Short Interest,Avg Daily Volume,Short Interest Ratio",
            "HYPE,6000000,1200000,5",
        ]
    )

    rows = parse_short_interest_file(text)

    assert rows[0]["symbol"] == "HYPE"
    assert rows[0]["short_interest_shares"] == 6_000_000
    assert rows[0]["average_daily_volume"] == 1_200_000
    assert rows[0]["days_to_cover"] == 5


def test_latest_short_interest_file_url_uses_newest_catalog_link():
    provider = FinraShortInterestProvider(transport=FakeFinraTransport())

    assert provider.latest_short_interest_file_url().endswith("shrt20260615.csv")


def test_short_interest_file_url_formats_settlement_date():
    provider = FinraShortInterestProvider(transport=FakeFinraTransport())

    assert provider.short_interest_file_url(date(2026, 6, 15)).endswith(
        "shrt20260615.csv"
    )
    assert provider.short_interest_file_url("2026-06-15").endswith(
        "shrt20260615.csv"
    )


def test_build_short_interest_records_filters_symbols_and_computes_pct_float():
    provider = FinraShortInterestProvider(transport=FakeFinraTransport())

    records = provider.build_short_interest_records(
        ["hype", "miss"],
        settlement_date="2026-06-15",
        float_shares_by_symbol={"HYPE": 10_000_000},
    )

    assert len(records) == 1
    record = records[0]
    assert record["symbol"] == "HYPE"
    assert record["finra_provider"] == "short_interest_file"
    assert record["short_interest_settlement_date"] == "2026-06-15"
    assert record["short_interest_shares"] == 5_000_000
    assert record["short_interest_pct_float"] == 50.0
    assert record["days_to_cover"] == 5.0
    assert record["short_interest_average_daily_volume"] == 1_000_000
    assert record["short_interest_market"] == "NMS"
    assert record["short_interest_issue_name"] == "Hype Corp"


def test_build_short_interest_records_derives_days_to_cover_when_file_omits_it():
    text = "Symbol|Current Short\nHYPE|5,000,000"

    def transport(url, headers, params):
        return text

    provider = FinraShortInterestProvider(transport=transport)

    record = provider.build_short_interest_records(
        ["HYPE"],
        settlement_date="20260615",
        average_volume_by_symbol={"HYPE": 1_000_000},
    )[0]

    assert record["days_to_cover"] == 5.0


def test_latest_short_interest_file_url_raises_when_catalog_has_no_links():
    def transport(url, headers, params):
        return "<html>No files</html>"

    provider = FinraShortInterestProvider(transport=transport)

    with pytest.raises(FinraApiError):
        provider.latest_short_interest_file_url()
