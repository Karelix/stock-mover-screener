"""SEC EDGAR adapter for fundamentals and filings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
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

REVENUE_CONCEPTS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
NET_INCOME_CONCEPTS = ("NetIncomeLoss",)
OPERATING_CASH_FLOW_CONCEPTS = (
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
)
CAPEX_CONCEPTS = (
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
)
CASH_CONCEPTS = (
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
)
CURRENT_ASSETS_CONCEPTS = ("AssetsCurrent",)
CURRENT_LIABILITIES_CONCEPTS = ("LiabilitiesCurrent",)
DEBT_CONCEPTS = (
    "DebtAndFinanceLeaseObligations",
    "LongTermDebtAndFinanceLeaseObligations",
    "LongTermDebt",
)
EQUITY_CONCEPTS = (
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
)
SHARES_OUTSTANDING_CONCEPTS = ("EntityCommonStockSharesOutstanding",)

REGISTRATION_FORMS = {"S-1", "S-3", "S-3ASR", "F-1", "F-3"}
OFFERING_FORMS = REGISTRATION_FORMS | {
    "424B1",
    "424B2",
    "424B3",
    "424B4",
    "424B5",
    "424B7",
    "424B8",
    "FWP",
}


class SecEdgarApiError(RuntimeError):
    """Raised when an SEC EDGAR request fails or returns invalid data."""


class SecUserAgentMissingError(ValueError):
    """Raised when SEC_USER_AGENT is not configured."""


class SecTickerNotFoundError(LookupError):
    """Raised when a ticker cannot be mapped to a CIK."""


@dataclass(frozen=True)
class SecEdgarConfig:
    user_agent: str
    data_base_url: str = "https://data.sec.gov"
    www_base_url: str = "https://www.sec.gov"
    timeout_seconds: float = 30.0


class SecEdgarProvider:
    """Fetch and normalize SEC company facts and filing metadata."""

    def __init__(
        self,
        config: SecEdgarConfig,
        *,
        transport: JsonTransport | None = None,
    ) -> None:
        if not config.user_agent.strip():
            raise SecUserAgentMissingError("SEC_USER_AGENT is required")
        self.config = config
        self._transport = transport or self._urlopen_json
        self._ticker_index: dict[str, dict[str, Any]] | None = None

    @classmethod
    def from_env(
        cls,
        *,
        env_path: str | Path = ".env",
        load_env: bool = True,
        transport: JsonTransport | None = None,
    ) -> "SecEdgarProvider":
        """Create a provider from SEC_USER_AGENT in the environment or .env."""

        if load_env:
            load_env_file(env_path)

        user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
        if not user_agent:
            raise SecUserAgentMissingError("SEC_USER_AGENT is required")

        config = SecEdgarConfig(
            user_agent=user_agent,
            data_base_url=os.environ.get(
                "SEC_DATA_BASE_URL", SecEdgarConfig.data_base_url
            ).rstrip("/"),
            www_base_url=os.environ.get(
                "SEC_WWW_BASE_URL", SecEdgarConfig.www_base_url
            ).rstrip("/"),
        )
        return cls(config, transport=transport)

    def build_company_records(
        self,
        symbols: Iterable[str],
        *,
        as_of: date | datetime | None = None,
        recent_filing_days: int = 365,
        include_company_facts: bool = True,
    ) -> list[dict[str, Any]]:
        """Return provider-normalized SEC records for the requested symbols."""

        active_as_of = _coerce_date(as_of)
        records: list[dict[str, Any]] = []
        for symbol in _normalize_symbols(symbols):
            cik = self.get_cik_for_symbol(symbol)
            submissions = self.get_submissions(cik)
            company_name = submissions.get("name")
            filings = _recent_filings(
                submissions,
                as_of=active_as_of,
                lookback_days=recent_filing_days,
            )

            record: dict[str, Any] = {
                "symbol": symbol,
                "cik": cik,
                "company_name": company_name,
                "country": "US",
                "sec_provider": "edgar",
                "recent_filings": filings,
                **_filing_signal_fields(filings),
            }

            if include_company_facts:
                record.update(_fundamental_fields(self.get_company_facts(cik)))

            records.append(
                {key: value for key, value in record.items() if value is not None}
            )
        return records

    def get_cik_for_symbol(self, symbol: str) -> str:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise SecTickerNotFoundError("empty ticker symbol")
        ticker_index = self._get_ticker_index()
        ticker = ticker_index.get(normalized_symbol)
        if ticker is None:
            raise SecTickerNotFoundError(f"ticker not found in SEC index: {symbol}")
        return _format_cik(ticker["cik_str"])

    def get_submissions(self, cik: str) -> dict[str, Any]:
        return self._get_json(self._data_url(f"/submissions/CIK{_format_cik(cik)}.json"))

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return self._get_json(
            self._data_url(f"/api/xbrl/companyfacts/CIK{_format_cik(cik)}.json")
        )

    def get_company_tickers(self) -> dict[str, Any]:
        return self._get_json(self._www_url("/files/company_tickers.json"))

    def _get_ticker_index(self) -> dict[str, dict[str, Any]]:
        if self._ticker_index is None:
            raw = self.get_company_tickers()
            self._ticker_index = {
                str(item.get("ticker") or "").strip().upper(): dict(item)
                for item in raw.values()
                if isinstance(item, Mapping) and item.get("ticker")
            }
        return self._ticker_index

    def _get_json(
        self, url: str, params: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "application/json",
        }
        response = self._transport(url, headers, dict(params or {}))
        if not isinstance(response, Mapping):
            raise SecEdgarApiError("SEC response was not a JSON object")
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
            raise SecEdgarApiError(f"SEC HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise SecEdgarApiError(f"SEC request failed: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise SecEdgarApiError("SEC response was not valid JSON") from exc

    def _data_url(self, path: str) -> str:
        return f"{self.config.data_base_url}{path}"

    def _www_url(self, path: str) -> str:
        return f"{self.config.www_base_url}{path}"


def _fundamental_fields(company_facts: Mapping[str, Any]) -> dict[str, Any]:
    facts = company_facts.get("facts", {}).get("us-gaap", {})
    revenue_items = _fact_items(facts, REVENUE_CONCEPTS, unit="USD")
    share_items = _fact_items(facts, SHARES_OUTSTANDING_CONCEPTS, unit="shares")

    latest_revenue = _latest_annual_or_duration(revenue_items)
    prior_revenue = _prior_annual(revenue_items, latest_revenue)
    latest_shares = _latest_fact(share_items)
    prior_shares = _prior_fact(share_items, latest_shares)

    current_assets = _latest_value(facts, CURRENT_ASSETS_CONCEPTS)
    current_liabilities = _latest_value(facts, CURRENT_LIABILITIES_CONCEPTS)
    total_debt = _latest_value(facts, DEBT_CONCEPTS)
    total_equity = _latest_value(facts, EQUITY_CONCEPTS)

    fields = {
        "revenue_ttm": _value(latest_revenue),
        "prior_year_revenue": _value(prior_revenue),
        "net_income": _latest_value(facts, NET_INCOME_CONCEPTS),
        "operating_cash_flow": _latest_value(facts, OPERATING_CASH_FLOW_CONCEPTS),
        "capital_expenditure": _latest_value(facts, CAPEX_CONCEPTS),
        "cash_and_equivalents": _latest_value(facts, CASH_CONCEPTS),
        "current_assets": current_assets,
        "current_liabilities": current_liabilities,
        "total_debt": total_debt,
        "total_equity": total_equity,
        "shares_outstanding": _value(latest_shares),
    }
    if current_assets is not None and current_liabilities:
        fields["current_ratio"] = current_assets / current_liabilities
    if total_debt is not None and total_equity is not None:
        fields["debt_to_equity"] = (
            math.inf
            if total_equity <= 0 and total_debt > 0
            else total_debt / total_equity
            if total_equity > 0
            else None
        )
    share_growth = _pct_change(_value(latest_shares), _value(prior_shares))
    if share_growth is not None:
        fields["shares_outstanding_growth_pct"] = share_growth
    return fields


def _latest_value(
    facts: Mapping[str, Any], concepts: Iterable[str], *, unit: str = "USD"
) -> float | None:
    return _value(_latest_annual_or_duration(_fact_items(facts, concepts, unit=unit)))


def _fact_items(
    facts: Mapping[str, Any], concepts: Iterable[str], *, unit: str
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for concept in concepts:
        concept_data = facts.get(concept, {})
        for item in concept_data.get("units", {}).get(unit, []):
            if _as_float(item.get("val")) is None:
                continue
            items.append({**dict(item), "concept": concept})
    return items


def _latest_annual_or_duration(
    items: list[dict[str, Any]]
) -> dict[str, Any] | None:
    annual_items = [
        item
        for item in items
        if str(item.get("fp") or "").upper() == "FY"
        or _duration_days(item) >= 300
    ]
    return _latest_fact(annual_items or items)


def _prior_annual(
    items: list[dict[str, Any]], latest_item: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    if latest_item is None:
        return None
    latest_end = _parse_date(latest_item.get("end"))
    prior_items = [
        item
        for item in items
        if (
            str(item.get("fp") or "").upper() == "FY"
            or _duration_days(item) >= 300
        )
        and _parse_date(item.get("end")) < latest_end
    ]
    return _latest_fact(prior_items)


def _prior_fact(
    items: list[dict[str, Any]], latest_item: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    if latest_item is None:
        return None
    latest_end = _parse_date(latest_item.get("end"))
    return _latest_fact(
        [item for item in items if _parse_date(item.get("end")) < latest_end]
    )


def _latest_fact(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None
    return max(
        items,
        key=lambda item: (
            _parse_date(item.get("end")),
            _parse_date(item.get("filed")),
        ),
    )


def _recent_filings(
    submissions: Mapping[str, Any], *, as_of: date, lookback_days: int
) -> list[dict[str, Any]]:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = list(recent.get("form", []))
    filing_dates = list(recent.get("filingDate", []))
    accession_numbers = list(recent.get("accessionNumber", []))
    report_dates = list(recent.get("reportDate", []))
    primary_documents = list(recent.get("primaryDocument", []))
    primary_descriptions = list(recent.get("primaryDocDescription", []))

    cutoff = as_of - timedelta(days=lookback_days)
    filings: list[dict[str, Any]] = []
    for index, form in enumerate(forms):
        filing_date = _parse_date(_list_get(filing_dates, index))
        if filing_date < cutoff or filing_date > as_of:
            continue

        normalized_form = str(form or "").strip().upper()
        description = str(_list_get(primary_descriptions, index) or "").strip()
        title = _filing_title(normalized_form, description)
        filings.append(
            {
                "form": normalized_form,
                "filing_date": filing_date.isoformat(),
                "report_date": _list_get(report_dates, index),
                "accession_number": _list_get(accession_numbers, index),
                "primary_document": _list_get(primary_documents, index),
                "title": title,
                "description": description or title,
            }
        )
    return filings


def _filing_signal_fields(filings: list[dict[str, Any]]) -> dict[str, Any]:
    forms = [str(filing.get("form") or "").upper() for filing in filings]
    offering_count = sum(1 for form in forms if form in OFFERING_FORMS)
    return {
        "active_shelf_registration": any(form in REGISTRATION_FORMS for form in forms),
        "recent_offering": any(form in OFFERING_FORMS for form in forms),
        "offering_count_12m": offering_count,
    }


def _filing_title(form: str, description: str) -> str:
    description_text = f" {description.lower()} "
    if form in {"S-3", "S-3ASR", "F-3"}:
        return f"{form} shelf registration"
    if form in {"S-1", "F-1"}:
        return f"{form} registration statement"
    if form.startswith("424B"):
        return f"{form} prospectus supplement"
    if form == "FWP":
        return "FWP free writing prospectus"
    if "atm" in description_text or "at-the-market" in description_text:
        return f"{form} at-the-market offering"
    return f"{form} {description}".strip()


def _coerce_date(value: date | datetime | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    return value


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    return [
        symbol
        for symbol in dict.fromkeys(str(item).strip().upper() for item in symbols)
        if symbol
    ]


def _format_cik(value: Any) -> str:
    return str(int(str(value).strip())).zfill(10)


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if not value:
        return date.min
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return date.min


def _duration_days(item: Mapping[str, Any]) -> int:
    start = _parse_date(item.get("start"))
    end = _parse_date(item.get("end"))
    if start == date.min or end == date.min:
        return 0
    return max((end - start).days, 0)


def _value(item: Mapping[str, Any] | None) -> float | None:
    return _as_float(item.get("val")) if item else None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def _pct_change(new_value: float | None, old_value: float | None) -> float | None:
    if new_value is None or old_value is None or old_value == 0:
        return None
    return ((new_value - old_value) / old_value) * 100.0


def _list_get(items: list[Any], index: int) -> Any:
    return items[index] if index < len(items) else None


def _with_query(url: str, params: Mapping[str, Any]) -> str:
    query = urlencode(
        {
            key: value
            for key, value in params.items()
            if value is not None and value != ""
        }
    )
    return f"{url}?{query}" if query else url
