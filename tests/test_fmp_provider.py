import pytest

from stock_mover_screener.providers.fmp import (
    FmpApiError,
    FmpCredentialsMissingError,
    FmpReferenceConfig,
    FmpReferenceProvider,
)


class FakeFmpTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, url, headers, params):
        self.calls.append((url, dict(headers), dict(params)))
        assert params["apikey"] == "key"

        if url.endswith("/profile"):
            return [
                {
                    "symbol": "HYPE",
                    "companyName": "Hype Corp",
                    "country": "US",
                    "price": 12.0,
                    "mktCap": 250_000_000,
                    "volAvg": 1_000_000,
                    "isEtf": False,
                    "isFund": False,
                    "exchange": "NASDAQ",
                    "sector": "Technology",
                    "industry": "Software",
                }
            ]

        if url.endswith("/shares-float"):
            return [
                {
                    "symbol": "HYPE",
                    "floatShares": 5_000_000,
                    "outstandingShares": 20_000_000,
                }
            ]

        if url.endswith("/income-statement"):
            return [
                {"date": "2025-12-31", "revenue": 500_000, "netIncome": -5_000_000},
                {"date": "2024-12-31", "revenue": 1_000_000, "netIncome": 100_000},
            ]

        if url.endswith("/balance-sheet-statement"):
            return [
                {
                    "date": "2025-12-31",
                    "cashAndCashEquivalents": 2_000_000,
                    "totalCurrentAssets": 7_000_000,
                    "totalCurrentLiabilities": 10_000_000,
                    "totalDebt": 30_000_000,
                    "totalStockholdersEquity": 10_000_000,
                }
            ]

        if url.endswith("/cash-flow-statement"):
            return [
                {
                    "date": "2025-12-31",
                    "operatingCashFlow": -4_000_000,
                    "capitalExpenditure": -2_000_000,
                    "freeCashFlow": -6_000_000,
                }
            ]

        raise AssertionError(f"unexpected FMP request: {url}")


def test_from_env_loads_api_key_from_dotenv(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "FMP_API_KEY='key'",
                "FMP_BASE_URL=https://financialmodelingprep.com/stable",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.delenv("FMP_BASE_URL", raising=False)

    provider = FmpReferenceProvider.from_env(
        env_path=env_path,
        transport=FakeFmpTransport(),
    )

    assert provider.config.api_key == "key"
    assert provider.config.base_url == "https://financialmodelingprep.com/stable"


def test_from_env_requires_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    with pytest.raises(FmpCredentialsMissingError):
        FmpReferenceProvider.from_env(env_path=tmp_path / ".env")


def test_build_reference_records_normalizes_profile_float_and_financials():
    provider = FmpReferenceProvider(
        FmpReferenceConfig(api_key="key"),
        transport=FakeFmpTransport(),
    )

    records = provider.build_reference_records(["hype"])

    assert len(records) == 1
    record = records[0]
    assert record["symbol"] == "HYPE"
    assert record["country"] == "US"
    assert record["company_name"] == "Hype Corp"
    assert record["security_type"] == "common_stock"
    assert record["exchange"] == "NASDAQ"
    assert record["sector"] == "Technology"
    assert record["industry"] == "Software"
    assert record["fmp_provider"] == "financial_modeling_prep"
    assert record["price"] == 12.0
    assert record["market_cap"] == 250_000_000
    assert record["average_volume"] == 1_000_000
    assert record["average_dollar_volume"] == 12_000_000
    assert record["float_shares"] == 5_000_000
    assert record["shares_outstanding"] == 20_000_000
    assert record["revenue_ttm"] == 500_000
    assert record["prior_year_revenue"] == 1_000_000
    assert record["net_income"] == -5_000_000
    assert record["operating_cash_flow"] == -4_000_000
    assert record["capital_expenditure"] == -2_000_000
    assert record["free_cash_flow"] == -6_000_000
    assert record["cash_and_equivalents"] == 2_000_000
    assert record["current_assets"] == 7_000_000
    assert record["current_liabilities"] == 10_000_000
    assert record["current_ratio"] == 0.7
    assert record["total_debt"] == 30_000_000
    assert record["total_equity"] == 10_000_000
    assert record["debt_to_equity"] == 3.0


def test_build_reference_records_can_skip_financial_statements():
    provider = FmpReferenceProvider(
        FmpReferenceConfig(api_key="key"),
        transport=FakeFmpTransport(),
    )

    record = provider.build_reference_records(
        ["HYPE"],
        include_financials=False,
    )[0]

    assert record["float_shares"] == 5_000_000
    assert "revenue_ttm" not in record


def test_security_type_marks_etfs():
    def transport(url, headers, params):
        if url.endswith("/profile"):
            return [{"symbol": "ETFZ", "country": "US", "isEtf": True}]
        if url.endswith("/shares-float"):
            return []
        if url.endswith("/market-capitalization"):
            return []
        raise AssertionError(f"unexpected FMP request: {url}")

    provider = FmpReferenceProvider(
        FmpReferenceConfig(api_key="key"),
        transport=transport,
    )

    record = provider.build_reference_records(
        ["ETFZ"],
        include_financials=False,
    )[0]

    assert record["security_type"] == "etf"


def test_market_cap_endpoint_used_when_profile_lacks_market_cap():
    def transport(url, headers, params):
        if url.endswith("/profile"):
            return [{"symbol": "HYPE", "country": "US", "price": 10, "volAvg": 100}]
        if url.endswith("/shares-float"):
            return []
        if url.endswith("/market-capitalization"):
            return [{"date": "2026-01-01", "marketCap": 123_000_000}]
        raise AssertionError(f"unexpected FMP request: {url}")

    provider = FmpReferenceProvider(
        FmpReferenceConfig(api_key="key"),
        transport=transport,
    )

    record = provider.build_reference_records(
        ["HYPE"],
        include_financials=False,
    )[0]

    assert record["market_cap"] == 123_000_000


def test_fmp_error_response_raises():
    def transport(url, headers, params):
        return {"Error Message": "Invalid API key"}

    provider = FmpReferenceProvider(
        FmpReferenceConfig(api_key="key"),
        transport=transport,
    )

    with pytest.raises(FmpApiError):
        provider.get_profile("HYPE")
