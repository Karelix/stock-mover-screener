"""Financial Modeling Prep reference-data adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import math
import os
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from stock_mover_screener.providers.env import load_env_file


JsonTransport = Callable[[str, Mapping[str, str], Mapping[str, Any]], Any]


class FmpApiError(RuntimeError):
    """Raised when FMP returns an error or an invalid response."""


class FmpCredentialsMissingError(ValueError):
    """Raised when FMP credentials are not available."""


@dataclass(frozen=True)
class FmpReferenceConfig:
    api_key: str
    base_url: str = "https://financialmodelingprep.com/stable"
    timeout_seconds: float = 30.0


class FmpReferenceProvider:
    """Fetch and normalize FMP profile, float, and statement data."""

    def __init__(
        self,
        config: FmpReferenceConfig,
        *,
        transport: JsonTransport | None = None,
    ) -> None:
        if not config.api_key.strip():
            raise FmpCredentialsMissingError("FMP_API_KEY is required")
        self.config = config
        self._transport = transport or self._urlopen_json

    @classmethod
    def from_env(
        cls,
        *,
        env_path: str | Path = ".env",
        load_env: bool = True,
        transport: JsonTransport | None = None,
    ) -> "FmpReferenceProvider":
        """Create a provider from FMP_API_KEY in the environment or .env."""

        if load_env:
            load_env_file(env_path)

        api_key = os.environ.get("FMP_API_KEY", "").strip()
        if not api_key:
            raise FmpCredentialsMissingError("FMP_API_KEY is required")

        config = FmpReferenceConfig(
            api_key=api_key,
            base_url=os.environ.get(
                "FMP_BASE_URL", FmpReferenceConfig.base_url
            ).rstrip("/"),
        )
        return cls(config, transport=transport)

    def build_reference_records(
        self,
        symbols: Iterable[str],
        *,
        include_financials: bool = True,
    ) -> list[dict[str, Any]]:
        """Return provider-normalized records for scanner enrichment."""

        records: list[dict[str, Any]] = []
        for symbol in _normalize_symbols(symbols):
            profile = _first_item(self.get_profile(symbol))
            share_float = _first_item(self.get_shares_float(symbol))
            market_cap = _market_cap_from_profile(profile)
            if market_cap is None:
                market_cap = _market_cap_from_response(self.get_market_cap(symbol))

            income_statements: list[dict[str, Any]] = []
            balance_sheets: list[dict[str, Any]] = []
            cash_flow_statements: list[dict[str, Any]] = []
            if include_financials:
                income_statements = self.get_income_statements(symbol, limit=2)
                balance_sheets = self.get_balance_sheets(symbol, limit=1)
                cash_flow_statements = self.get_cash_flow_statements(symbol, limit=1)

            latest_income = _latest_statement(income_statements)
            prior_income = _prior_statement(income_statements, latest_income)
            latest_balance = _latest_statement(balance_sheets)
            latest_cash_flow = _latest_statement(cash_flow_statements)
            price = _first_float(profile, "price", "lastPrice")
            average_volume = _first_float(profile, "volAvg", "avgVolume", "volumeAvg")
            average_dollar_volume = (
                price * average_volume
                if price is not None and average_volume is not None
                else None
            )
            current_assets = _first_float(
                latest_balance,
                "totalCurrentAssets",
                "totalCurrentAssetsUSD",
            )
            current_liabilities = _first_float(
                latest_balance,
                "totalCurrentLiabilities",
                "totalCurrentLiabilitiesUSD",
            )
            total_debt = _first_float(latest_balance, "totalDebt", "netDebt")
            total_equity = _first_float(
                latest_balance,
                "totalStockholdersEquity",
                "totalEquity",
                "stockholdersEquity",
            )

            record = {
                "symbol": symbol,
                "country": _country(profile),
                "company_name": _first_present(profile, "companyName", "company_name"),
                "exchange": _first_present(profile, "exchange", "exchangeShortName"),
                "sector": _first_present(profile, "sector"),
                "industry": _first_present(profile, "industry"),
                "security_type": _security_type(profile),
                "fmp_provider": "financial_modeling_prep",
                "price": price,
                "market_cap": market_cap,
                "average_volume": average_volume,
                "average_dollar_volume": average_dollar_volume,
                "float_shares": _first_float(
                    share_float,
                    "floatShares",
                    "freeFloatShares",
                    "publicFloat",
                    "float",
                ),
                "shares_outstanding": _first_float(
                    share_float,
                    "outstandingShares",
                    "sharesOutstanding",
                    "sharesOut",
                )
                or _first_float(profile, "sharesOutstanding", "sharesOut"),
                "revenue_ttm": _first_float(latest_income, "revenue"),
                "prior_year_revenue": _first_float(prior_income, "revenue"),
                "net_income": _first_float(latest_income, "netIncome"),
                "operating_cash_flow": _first_float(
                    latest_cash_flow,
                    "operatingCashFlow",
                    "netCashProvidedByOperatingActivities",
                ),
                "capital_expenditure": _first_float(
                    latest_cash_flow,
                    "capitalExpenditure",
                    "capitalExpenditures",
                ),
                "free_cash_flow": _first_float(latest_cash_flow, "freeCashFlow"),
                "cash_and_equivalents": _first_float(
                    latest_balance,
                    "cashAndCashEquivalents",
                    "cashAndShortTermInvestments",
                ),
                "current_assets": current_assets,
                "current_liabilities": current_liabilities,
                "total_debt": total_debt,
                "total_equity": total_equity,
            }
            if current_assets is not None and current_liabilities:
                record["current_ratio"] = current_assets / current_liabilities
            if total_debt is not None and total_equity is not None:
                record["debt_to_equity"] = _debt_to_equity(total_debt, total_equity)

            records.append(
                {key: value for key, value in record.items() if value is not None}
            )
        return records

    def get_profile(self, symbol: str) -> list[dict[str, Any]]:
        return _as_list(self._get_json("/profile", {"symbol": _normalize_symbol(symbol)}))

    def get_shares_float(self, symbol: str) -> list[dict[str, Any]]:
        return _as_list(
            self._get_json("/shares-float", {"symbol": _normalize_symbol(symbol)})
        )

    def get_market_cap(self, symbol: str) -> list[dict[str, Any]]:
        return _as_list(
            self._get_json(
                "/market-capitalization",
                {"symbol": _normalize_symbol(symbol)},
            )
        )

    def get_income_statements(
        self, symbol: str, *, period: str = "annual", limit: int = 2
    ) -> list[dict[str, Any]]:
        return _as_list(
            self._get_json(
                "/income-statement",
                {"symbol": _normalize_symbol(symbol), "period": period, "limit": limit},
            )
        )

    def get_balance_sheets(
        self, symbol: str, *, period: str = "annual", limit: int = 1
    ) -> list[dict[str, Any]]:
        return _as_list(
            self._get_json(
                "/balance-sheet-statement",
                {"symbol": _normalize_symbol(symbol), "period": period, "limit": limit},
            )
        )

    def get_cash_flow_statements(
        self, symbol: str, *, period: str = "annual", limit: int = 1
    ) -> list[dict[str, Any]]:
        return _as_list(
            self._get_json(
                "/cash-flow-statement",
                {"symbol": _normalize_symbol(symbol), "period": period, "limit": limit},
            )
        )

    def _get_json(self, path: str, params: Mapping[str, Any]) -> Any:
        active_params = {**dict(params), "apikey": self.config.api_key}
        response = self._transport(self._url(path), {}, active_params)
        if isinstance(response, Mapping) and _fmp_error_message(response):
            raise FmpApiError(str(_fmp_error_message(response)))
        if not isinstance(response, (list, Mapping)):
            raise FmpApiError("FMP response was not JSON list/object")
        return response

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
            raise FmpApiError(f"FMP HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise FmpApiError(f"FMP request failed: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise FmpApiError("FMP response was not valid JSON") from exc

    def _url(self, path: str) -> str:
        return f"{self.config.base_url}{path}"


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    return [
        symbol
        for symbol in dict.fromkeys(_normalize_symbol(item) for item in symbols)
        if symbol
    ]


def _normalize_symbol(symbol: Any) -> str:
    return str(symbol or "").strip().upper()


def _first_item(items: list[dict[str, Any]]) -> dict[str, Any]:
    return dict(items[0]) if items else {}


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    if isinstance(value, Mapping):
        return [dict(value)]
    return []


def _latest_statement(items: list[dict[str, Any]]) -> dict[str, Any]:
    return max(items, key=lambda item: _parse_date(item.get("date")), default={})


def _prior_statement(
    items: list[dict[str, Any]], latest_item: Mapping[str, Any]
) -> dict[str, Any]:
    latest_date = _parse_date(latest_item.get("date"))
    prior_items = [item for item in items if _parse_date(item.get("date")) < latest_date]
    return _latest_statement(prior_items)


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if not value:
        return date.min
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return date.min


def _country(profile: Mapping[str, Any]) -> str | None:
    country = _first_present(profile, "country")
    return str(country).strip().upper() if country else None


def _security_type(profile: Mapping[str, Any]) -> str:
    if _as_bool(_first_present(profile, "isEtf", "isETF")):
        return "etf"
    if _as_bool(_first_present(profile, "isFund")):
        return "fund"
    if _as_bool(_first_present(profile, "isAdr", "isADR")):
        return "adr"
    return "common_stock"


def _market_cap_from_profile(profile: Mapping[str, Any]) -> float | None:
    return _first_float(profile, "mktCap", "marketCap", "marketCapitalization")


def _market_cap_from_response(items: list[dict[str, Any]]) -> float | None:
    latest_item = _latest_statement(items)
    return _first_float(latest_item, "marketCap", "marketCapitalization", "mktCap")


def _debt_to_equity(total_debt: float, total_equity: float) -> float | None:
    if total_equity > 0:
        return total_debt / total_equity
    if total_equity <= 0 and total_debt > 0:
        return math.inf
    return None


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return None


def _first_float(record: Mapping[str, Any], *keys: str) -> float | None:
    return _as_float(_first_present(record, *keys))


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "t", "yes", "y", "1"}
    return False


def _fmp_error_message(response: Mapping[str, Any]) -> Any:
    for key in ("Error Message", "error", "message"):
        value = response.get(key)
        if value:
            return value
    return None


def _with_query(url: str, params: Mapping[str, Any]) -> str:
    query = urlencode(
        {
            key: value
            for key, value in params.items()
            if value is not None and value != ""
        }
    )
    return f"{url}?{query}" if query else url
