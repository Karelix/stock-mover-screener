from datetime import date

import pytest

from stock_mover_screener.providers.sec_edgar import (
    SecEdgarConfig,
    SecEdgarProvider,
    SecTickerNotFoundError,
    SecUserAgentMissingError,
)


class FakeSecTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, url, headers, params):
        self.calls.append((url, dict(headers), dict(params)))
        assert headers["User-Agent"] == "Test User test@example.com"

        if url.endswith("/files/company_tickers.json"):
            return {
                "0": {"cik_str": 1234567, "ticker": "HYPE", "title": "Hype Corp"}
            }

        if url.endswith("/submissions/CIK0001234567.json"):
            return {
                "cik": "0001234567",
                "name": "Hype Corp",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001", "0002", "0003", "0004"],
                        "filingDate": [
                            "2026-06-15",
                            "2026-05-20",
                            "2026-03-01",
                            "2024-01-01",
                        ],
                        "reportDate": [
                            "2026-06-15",
                            "2026-05-20",
                            "2025-12-31",
                            "2023-12-31",
                        ],
                        "form": ["S-3", "424B5", "10-K", "S-1"],
                        "primaryDocument": [
                            "s3.htm",
                            "424b5.htm",
                            "10k.htm",
                            "s1.htm",
                        ],
                        "primaryDocDescription": [
                            "Shelf registration statement",
                            "Prospectus supplement",
                            "Annual report",
                            "Registration statement",
                        ],
                    }
                },
            }

        if url.endswith("/api/xbrl/companyfacts/CIK0001234567.json"):
            return _company_facts()

        raise AssertionError(f"unexpected SEC request: {url}")


def _fact(val, end, *, start="2025-01-01", form="10-K", fp="FY", filed=None):
    return {
        "val": val,
        "start": start,
        "end": end,
        "form": form,
        "fp": fp,
        "filed": filed or end,
    }


def _instant_fact(val, end, *, filed=None):
    return {"val": val, "end": end, "form": "10-K", "filed": filed or end}


def _company_facts():
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            _fact(1_000_000, "2024-12-31", start="2024-01-01"),
                            _fact(500_000, "2025-12-31"),
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {"USD": [_fact(-5_000_000, "2025-12-31")]}
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {"USD": [_fact(-4_000_000, "2025-12-31")]}
                },
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {"USD": [_fact(2_000_000, "2025-12-31")]}
                },
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {"USD": [_instant_fact(2_000_000, "2025-12-31")]}
                },
                "AssetsCurrent": {
                    "units": {"USD": [_instant_fact(7_000_000, "2025-12-31")]}
                },
                "LiabilitiesCurrent": {
                    "units": {"USD": [_instant_fact(10_000_000, "2025-12-31")]}
                },
                "LongTermDebt": {
                    "units": {"USD": [_instant_fact(30_000_000, "2025-12-31")]}
                },
                "StockholdersEquity": {
                    "units": {"USD": [_instant_fact(10_000_000, "2025-12-31")]}
                },
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            _instant_fact(10_000_000, "2024-12-31"),
                            _instant_fact(20_000_000, "2025-12-31"),
                        ]
                    }
                },
            }
        }
    }


def test_from_env_loads_user_agent_from_dotenv(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("SEC_USER_AGENT='Test User test@example.com'", encoding="utf-8")
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)

    provider = SecEdgarProvider.from_env(
        env_path=env_path,
        transport=FakeSecTransport(),
    )

    assert provider.config.user_agent == "Test User test@example.com"


def test_from_env_requires_sec_user_agent(tmp_path, monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)

    with pytest.raises(SecUserAgentMissingError):
        SecEdgarProvider.from_env(env_path=tmp_path / ".env")


def test_build_company_records_normalizes_fundamentals_and_filings():
    provider = SecEdgarProvider(
        SecEdgarConfig(user_agent="Test User test@example.com"),
        transport=FakeSecTransport(),
    )

    records = provider.build_company_records(["hype"], as_of=date(2026, 7, 3))

    assert len(records) == 1
    record = records[0]
    assert record["symbol"] == "HYPE"
    assert record["cik"] == "0001234567"
    assert record["company_name"] == "Hype Corp"
    assert record["country"] == "US"
    assert record["sec_provider"] == "edgar"
    assert record["revenue_ttm"] == 500_000
    assert record["prior_year_revenue"] == 1_000_000
    assert record["net_income"] == -5_000_000
    assert record["operating_cash_flow"] == -4_000_000
    assert record["capital_expenditure"] == 2_000_000
    assert record["cash_and_equivalents"] == 2_000_000
    assert record["current_ratio"] == 0.7
    assert record["total_debt"] == 30_000_000
    assert record["total_equity"] == 10_000_000
    assert record["debt_to_equity"] == 3.0
    assert record["shares_outstanding"] == 20_000_000
    assert record["shares_outstanding_growth_pct"] == 100.0
    assert record["active_shelf_registration"] is True
    assert record["recent_offering"] is True
    assert record["offering_count_12m"] == 2
    assert [filing["form"] for filing in record["recent_filings"]] == [
        "S-3",
        "424B5",
        "10-K",
    ]
    assert record["recent_filings"][0]["title"] == "S-3 shelf registration"
    assert record["recent_filings"][1]["title"] == "424B5 prospectus supplement"


def test_get_cik_for_symbol_raises_for_missing_ticker():
    provider = SecEdgarProvider(
        SecEdgarConfig(user_agent="Test User test@example.com"),
        transport=FakeSecTransport(),
    )

    with pytest.raises(SecTickerNotFoundError):
        provider.get_cik_for_symbol("MISS")
