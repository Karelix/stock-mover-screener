from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from stock_mover_screener.providers.alpaca import (
    AlpacaCredentialsMissingError,
    AlpacaMarketDataConfig,
    AlpacaMarketDataProvider,
)


NY_TZ = ZoneInfo("America/New_York")


class FakeAlpacaTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, url, headers, params):
        self.calls.append((url, dict(headers), dict(params)))
        assert headers["APCA-API-KEY-ID"] == "key"
        assert headers["APCA-API-SECRET-KEY"] == "secret"

        if url.endswith("/v2/stocks/quotes/latest"):
            return {"quotes": {"HYPE": {"bp": 12.45, "ap": 12.55}}}

        if url.endswith("/v1beta1/news"):
            return {
                "news": [
                    {
                        "symbols": ["HYPE"],
                        "headline": "HYPE announces AI partnership",
                    },
                    {
                        "symbols": ["OTHER"],
                        "headline": "Other ticker headline",
                    },
                ]
            }

        if url.endswith("/v2/stocks/bars"):
            timeframe = params["timeframe"]
            if timeframe == "1Day":
                return {"bars": {"HYPE": _daily_bars()}}
            if timeframe == "1Min" and str(params["start"]).startswith("2026-07-03T"):
                return {
                    "bars": {
                        "HYPE": [
                            {
                                "t": "2026-07-03T08:00:00Z",
                                "o": 11.0,
                                "h": 11.6,
                                "l": 10.9,
                                "c": 11.5,
                                "v": 1000,
                            },
                            {
                                "t": "2026-07-03T13:00:00Z",
                                "o": 12.0,
                                "h": 12.6,
                                "l": 11.9,
                                "c": 12.5,
                                "v": 2000,
                            },
                        ]
                    }
                }
            if timeframe == "1Min":
                return {
                    "bars": {
                        "HYPE": [
                            {
                                "t": "2026-07-01T08:00:00Z",
                                "o": 10.0,
                                "h": 10.2,
                                "l": 9.8,
                                "c": 10.1,
                                "v": 3000,
                            },
                            {
                                "t": "2026-07-02T08:00:00Z",
                                "o": 10.0,
                                "h": 10.2,
                                "l": 9.8,
                                "c": 10.1,
                                "v": 1000,
                            },
                        ]
                    }
                }

        raise AssertionError(f"unexpected request: {url} {params}")


def _daily_bars():
    bars = []
    for day in range(12, 31):
        bars.append(
            {
                "t": f"2026-06-{day:02d}T13:30:00Z",
                "o": 10.0,
                "h": 10.5,
                "l": 9.5,
                "c": 10.0,
                "v": 1_000_000,
            }
        )
    bars.append(
        {
            "t": "2026-07-02T13:30:00Z",
            "o": 10.0,
            "h": 10.5,
            "l": 9.5,
            "c": 10.0,
            "v": 1_000_000,
        }
    )
    return bars


def test_from_env_loads_credentials_from_dotenv(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "ALPACA_API_KEY_ID=key",
                "ALPACA_API_SECRET_KEY='secret'",
                "ALPACA_DATA_FEED=sip",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    monkeypatch.delenv("ALPACA_DATA_FEED", raising=False)

    provider = AlpacaMarketDataProvider.from_env(
        env_path=env_path,
        transport=FakeAlpacaTransport(),
    )

    assert provider.config.api_key_id == "key"
    assert provider.config.api_secret_key == "secret"
    assert provider.config.feed == "sip"


def test_from_env_requires_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)

    with pytest.raises(AlpacaCredentialsMissingError):
        AlpacaMarketDataProvider.from_env(env_path=tmp_path / ".env")


def test_build_premarket_records_normalizes_alpaca_market_data():
    transport = FakeAlpacaTransport()
    provider = AlpacaMarketDataProvider(
        AlpacaMarketDataConfig(api_key_id="key", api_secret_key="secret"),
        transport=transport,
    )

    records = provider.build_premarket_records(
        ["hype"],
        as_of=datetime(2026, 7, 3, 9, 0, tzinfo=NY_TZ),
    )

    assert len(records) == 1
    record = records[0]
    assert record["symbol"] == "HYPE"
    assert record["country"] == "US"
    assert record["data_provider"] == "alpaca"
    assert record["previous_close"] == 10.0
    assert record["premarket_open"] == 11.0
    assert record["premarket_price"] == 12.5
    assert record["premarket_volume"] == 3000.0
    assert record["premarket_dollar_volume"] == 37_500.0
    assert record["average_premarket_volume"] == 2000.0
    assert record["premarket_relative_volume"] == 1.5
    assert record["average_dollar_volume"] == 10_000_000
    assert record["atr_14_pct"] == 10.0
    assert record["premarket_bid"] == 12.45
    assert record["premarket_ask"] == 12.55
    assert record["headlines"] == ["HYPE announces AI partnership"]
    assert record["headline_count_today"] == 1


def test_get_bars_follows_alpaca_pagination():
    calls = []

    def transport(url, headers, params):
        calls.append(dict(params))
        if "page_token" not in params:
            return {
                "bars": {"HYPE": [{"t": "2026-07-03T08:00:00Z", "c": 10}]},
                "next_page_token": "next",
            }
        return {"bars": {"HYPE": [{"t": "2026-07-03T08:01:00Z", "c": 11}]}}

    provider = AlpacaMarketDataProvider(
        AlpacaMarketDataConfig(api_key_id="key", api_secret_key="secret"),
        transport=transport,
    )

    bars = provider.get_bars(
        ["HYPE"],
        timeframe="1Min",
        start=datetime(2026, 7, 3, 4, 0, tzinfo=NY_TZ),
        end=datetime(2026, 7, 3, 9, 30, tzinfo=NY_TZ),
    )

    assert [bar["c"] for bar in bars["HYPE"]] == [10, 11]
    assert calls[1]["page_token"] == "next"
