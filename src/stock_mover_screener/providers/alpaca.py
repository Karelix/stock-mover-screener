"""Alpaca market-data adapter."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
import math
import os
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from stock_mover_screener.providers.env import load_env_file


NY_TZ = ZoneInfo("America/New_York")
UTC = timezone.utc

JsonTransport = Callable[[str, Mapping[str, str], Mapping[str, Any]], Any]


class AlpacaApiError(RuntimeError):
    """Raised when Alpaca returns an error or an invalid response."""


class AlpacaCredentialsMissingError(ValueError):
    """Raised when Alpaca credentials are not available."""


@dataclass(frozen=True)
class AlpacaMarketDataConfig:
    api_key_id: str
    api_secret_key: str
    base_url: str = "https://paper-api.alpaca.markets"
    data_base_url: str = "https://data.alpaca.markets"
    feed: str = "iex"
    timeout_seconds: float = 30.0


class AlpacaMarketDataProvider:
    """Fetch and normalize Alpaca market data for screener records."""

    def __init__(
        self,
        config: AlpacaMarketDataConfig,
        *,
        transport: JsonTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport or self._urlopen_json

    @classmethod
    def from_env(
        cls,
        *,
        env_path: str | Path = ".env",
        load_env: bool = True,
        transport: JsonTransport | None = None,
    ) -> "AlpacaMarketDataProvider":
        """Create a provider from environment variables or a local .env file."""

        if load_env:
            load_env_file(env_path)

        api_key_id = os.environ.get("ALPACA_API_KEY_ID", "").strip()
        api_secret_key = os.environ.get("ALPACA_API_SECRET_KEY", "").strip()
        if not api_key_id or not api_secret_key:
            raise AlpacaCredentialsMissingError(
                "ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY are required"
            )

        config = AlpacaMarketDataConfig(
            api_key_id=api_key_id,
            api_secret_key=api_secret_key,
            base_url=os.environ.get(
                "ALPACA_BASE_URL", AlpacaMarketDataConfig.base_url
            ).rstrip("/"),
            data_base_url=os.environ.get(
                "ALPACA_DATA_BASE_URL", AlpacaMarketDataConfig.data_base_url
            ).rstrip("/"),
            feed=os.environ.get("ALPACA_DATA_FEED", AlpacaMarketDataConfig.feed),
        )
        return cls(config, transport=transport)

    def build_premarket_records(
        self,
        symbols: list[str],
        *,
        as_of: datetime | None = None,
        average_premarket_days: int = 5,
        daily_lookback_days: int = 60,
        include_news: bool = True,
    ) -> list[dict[str, Any]]:
        """Return provider-normalized market-data records for pre-market scanning."""

        active_symbols = _normalize_symbols(symbols)
        if not active_symbols:
            return []

        active_as_of = _coerce_datetime(as_of)
        session = _premarket_session(active_as_of)
        daily_bars = self.get_bars(
            active_symbols,
            timeframe="1Day",
            start=session.day - timedelta(days=daily_lookback_days),
            end=session.day,
        )
        current_premarket_bars = self.get_bars(
            active_symbols,
            timeframe="1Min",
            start=session.start,
            end=session.end,
        )
        previous_premarket_bars = self.get_bars(
            active_symbols,
            timeframe="1Min",
            start=session.day - timedelta(days=average_premarket_days + 7),
            end=session.day,
        )
        quotes = self.get_latest_quotes(active_symbols)
        news_by_symbol = (
            self.get_news_by_symbol(
                active_symbols,
                start=session.day,
                end=session.end,
            )
            if include_news
            else {}
        )

        records: list[dict[str, Any]] = []
        for symbol in active_symbols:
            daily_metrics = _daily_metrics(daily_bars.get(symbol, []), session.day)
            current_metrics = _premarket_metrics(current_premarket_bars.get(symbol, []))
            average_premarket_volume = _average_prior_premarket_volume(
                previous_premarket_bars.get(symbol, []),
                current_day=session.day,
                max_days=average_premarket_days,
            )
            quote = quotes.get(symbol, {})
            headlines = news_by_symbol.get(symbol, [])

            record = {
                "symbol": symbol,
                "country": "US",
                "data_provider": "alpaca",
                "price": current_metrics.get("premarket_price")
                or daily_metrics.get("previous_close"),
                "premarket_price": current_metrics.get("premarket_price"),
                "premarket_open": current_metrics.get("premarket_open"),
                "premarket_volume": current_metrics.get("premarket_volume"),
                "premarket_dollar_volume": current_metrics.get(
                    "premarket_dollar_volume"
                ),
                "average_premarket_volume": average_premarket_volume,
                "previous_close": daily_metrics.get("previous_close"),
                "average_dollar_volume": daily_metrics.get("average_dollar_volume"),
                "atr_14_pct": daily_metrics.get("atr_14_pct"),
                "premarket_bid": _as_float(quote.get("bp")),
                "premarket_ask": _as_float(quote.get("ap")),
                "headlines": headlines,
                "headline_count_today": len(headlines),
            }
            if average_premarket_volume and current_metrics.get("premarket_volume"):
                record["premarket_relative_volume"] = (
                    current_metrics["premarket_volume"] / average_premarket_volume
                )
            records.append({key: value for key, value in record.items() if value is not None})

        return records

    def get_bars(
        self,
        symbols: list[str],
        *,
        timeframe: str,
        start: date | datetime,
        end: date | datetime,
        adjustment: str = "raw",
        limit: int = 10000,
    ) -> dict[str, list[dict[str, Any]]]:
        params: dict[str, Any] = {
            "symbols": ",".join(_normalize_symbols(symbols)),
            "timeframe": timeframe,
            "start": _format_alpaca_time(start),
            "end": _format_alpaca_time(end),
            "adjustment": adjustment,
            "feed": self.config.feed,
            "limit": limit,
        }
        response = self._paginated_get(self._data_url("/v2/stocks/bars"), params)
        return {
            symbol.upper(): list(bars or [])
            for symbol, bars in response.get("bars", {}).items()
        }

    def get_latest_quotes(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        params = {
            "symbols": ",".join(_normalize_symbols(symbols)),
            "feed": self.config.feed,
        }
        response = self._get_json(self._data_url("/v2/stocks/quotes/latest"), params)
        return {
            symbol.upper(): dict(quote or {})
            for symbol, quote in response.get("quotes", {}).items()
        }

    def get_news_by_symbol(
        self,
        symbols: list[str],
        *,
        start: date | datetime,
        end: date | datetime,
        limit: int = 50,
    ) -> dict[str, list[str]]:
        active_symbols = _normalize_symbols(symbols)
        params = {
            "symbols": ",".join(active_symbols),
            "start": _format_alpaca_time(start),
            "end": _format_alpaca_time(end),
            "limit": limit,
            "sort": "desc",
        }
        response = self._paginated_get(self._data_url("/v1beta1/news"), params)
        headlines_by_symbol: dict[str, list[str]] = {symbol: [] for symbol in active_symbols}
        for item in response.get("news", []):
            headline = item.get("headline") or item.get("title")
            if not headline:
                continue
            item_symbols = _normalize_symbols(item.get("symbols", []))
            target_symbols = item_symbols or active_symbols
            for symbol in target_symbols:
                if symbol in headlines_by_symbol:
                    headlines_by_symbol[symbol].append(str(headline))
        return headlines_by_symbol

    def _paginated_get(
        self, url: str, params: Mapping[str, Any]
    ) -> dict[str, Any]:
        combined: dict[str, Any] = {}
        page_params = dict(params)
        while True:
            response = self._get_json(url, page_params)
            _merge_paginated_response(combined, response)
            next_page_token = response.get("next_page_token")
            if not next_page_token:
                return combined
            page_params["page_token"] = next_page_token

    def _get_json(self, url: str, params: Mapping[str, Any]) -> dict[str, Any]:
        headers = {
            "APCA-API-KEY-ID": self.config.api_key_id,
            "APCA-API-SECRET-KEY": self.config.api_secret_key,
            "Accept": "application/json",
        }
        response = self._transport(url, headers, params)
        if not isinstance(response, Mapping):
            raise AlpacaApiError("Alpaca response was not a JSON object")
        return dict(response)

    def _urlopen_json(
        self, url: str, headers: Mapping[str, str], params: Mapping[str, Any]
    ) -> Any:
        request_url = _with_query(url, params)
        request = Request(request_url, headers=dict(headers))
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AlpacaApiError(f"Alpaca HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise AlpacaApiError(f"Alpaca request failed: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise AlpacaApiError("Alpaca response was not valid JSON") from exc

    def _data_url(self, path: str) -> str:
        return f"{self.config.data_base_url}{path}"


@dataclass(frozen=True)
class _PremarketSession:
    day: date
    start: datetime
    end: datetime


def _premarket_session(as_of: datetime) -> _PremarketSession:
    local_as_of = as_of.astimezone(NY_TZ)
    session_day = local_as_of.date()
    start = datetime.combine(session_day, time(4, 0), NY_TZ)
    regular_open = datetime.combine(session_day, time(9, 30), NY_TZ)
    end = min(max(local_as_of, start), regular_open)
    return _PremarketSession(day=session_day, start=start, end=end)


def _coerce_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(tz=NY_TZ)
    if value.tzinfo is None:
        return value.replace(tzinfo=NY_TZ)
    return value


def _normalize_symbols(symbols: Any) -> list[str]:
    if isinstance(symbols, str):
        raw_symbols = [symbols]
    else:
        raw_symbols = list(symbols or [])
    return [
        symbol
        for symbol in dict.fromkeys(str(item).strip().upper() for item in raw_symbols)
        if symbol
    ]


def _format_alpaca_time(value: date | datetime) -> str:
    if isinstance(value, datetime):
        active_value = value if value.tzinfo else value.replace(tzinfo=NY_TZ)
        return active_value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value.isoformat()


def _with_query(url: str, params: Mapping[str, Any]) -> str:
    query = urlencode(
        {
            key: value
            for key, value in params.items()
            if value is not None and value != ""
        }
    )
    return f"{url}?{query}" if query else url


def _merge_paginated_response(
    combined: dict[str, Any], response: Mapping[str, Any]
) -> None:
    for key, value in response.items():
        if key == "next_page_token":
            continue
        if isinstance(value, Mapping):
            target = combined.setdefault(key, {})
            for nested_key, nested_value in value.items():
                if isinstance(nested_value, list):
                    target.setdefault(nested_key, []).extend(nested_value)
                else:
                    target[nested_key] = nested_value
        elif isinstance(value, list):
            combined.setdefault(key, []).extend(value)
        else:
            combined[key] = value


def _daily_metrics(
    bars: list[dict[str, Any]], current_day: date
) -> dict[str, float | None]:
    prior_bars = [
        bar
        for bar in sorted(bars, key=lambda item: str(item.get("t") or ""))
        if _bar_date(bar) < current_day
    ]
    if not prior_bars:
        return {
            "previous_close": None,
            "average_dollar_volume": None,
            "atr_14_pct": None,
        }

    previous_close = _as_float(prior_bars[-1].get("c"))
    dollar_volumes = [
        close * volume
        for bar in prior_bars[-20:]
        if (close := _as_float(bar.get("c"))) is not None
        and (volume := _as_float(bar.get("v"))) is not None
    ]
    average_dollar_volume = (
        sum(dollar_volumes) / len(dollar_volumes) if dollar_volumes else None
    )

    true_ranges: list[float] = []
    previous_bar_close: float | None = None
    for bar in prior_bars:
        high = _as_float(bar.get("h"))
        low = _as_float(bar.get("l"))
        close = _as_float(bar.get("c"))
        if high is None or low is None:
            previous_bar_close = close
            continue
        if previous_bar_close is None:
            true_range = high - low
        else:
            true_range = max(
                high - low,
                abs(high - previous_bar_close),
                abs(low - previous_bar_close),
            )
        true_ranges.append(true_range)
        previous_bar_close = close

    atr_14_pct = None
    if previous_close and previous_close > 0 and true_ranges:
        atr = sum(true_ranges[-14:]) / min(14, len(true_ranges))
        atr_14_pct = (atr / previous_close) * 100.0

    return {
        "previous_close": previous_close,
        "average_dollar_volume": average_dollar_volume,
        "atr_14_pct": atr_14_pct,
    }


def _premarket_metrics(bars: list[dict[str, Any]]) -> dict[str, float | None]:
    active_bars = sorted(bars, key=lambda item: str(item.get("t") or ""))
    if not active_bars:
        return {
            "premarket_open": None,
            "premarket_price": None,
            "premarket_volume": None,
            "premarket_dollar_volume": None,
        }

    premarket_open = _as_float(active_bars[0].get("o"))
    premarket_price = _as_float(active_bars[-1].get("c"))
    premarket_volume = sum(_as_float(bar.get("v"), default=0.0) or 0.0 for bar in active_bars)
    premarket_dollar_volume = (
        premarket_price * premarket_volume if premarket_price is not None else None
    )
    return {
        "premarket_open": premarket_open,
        "premarket_price": premarket_price,
        "premarket_volume": premarket_volume,
        "premarket_dollar_volume": premarket_dollar_volume,
    }


def _average_prior_premarket_volume(
    bars: list[dict[str, Any]], *, current_day: date, max_days: int
) -> float | None:
    volume_by_day: dict[date, float] = defaultdict(float)
    for bar in bars:
        bar_time = _bar_datetime(bar)
        if bar_time is None:
            continue
        local_time = bar_time.astimezone(NY_TZ)
        if local_time.date() >= current_day:
            continue
        if time(4, 0) <= local_time.time() <= time(9, 30):
            volume_by_day[local_time.date()] += _as_float(bar.get("v"), default=0.0) or 0.0

    day_volumes = [
        volume
        for _, volume in sorted(volume_by_day.items(), reverse=True)[:max_days]
        if volume > 0
    ]
    return sum(day_volumes) / len(day_volumes) if day_volumes else None


def _bar_date(bar: Mapping[str, Any]) -> date:
    bar_datetime = _bar_datetime(bar)
    return bar_datetime.astimezone(NY_TZ).date() if bar_datetime else date.min


def _bar_datetime(bar: Mapping[str, Any]) -> datetime | None:
    timestamp = bar.get("t")
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return None


def _as_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(parsed) else parsed
