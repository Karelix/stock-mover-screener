"""FINRA short-interest file adapter."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
import io
import math
import re
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TextTransport = Callable[[str, Mapping[str, str], Mapping[str, Any]], str]

SHORT_INTEREST_LINK_RE = re.compile(
    r'https?://[^"\']+/shrt(?P<date>\d{8})\.csv|/[^"\']*/shrt(?P<path_date>\d{8})\.csv',
    re.IGNORECASE,
)


class FinraApiError(RuntimeError):
    """Raised when a FINRA download fails or cannot be parsed."""


@dataclass(frozen=True)
class FinraShortInterestConfig:
    catalog_url: str = (
        "https://www.finra.org/finra-data/browse-catalog/equity-short-interest/files"
    )
    file_url_template: str = (
        "https://cdn.finra.org/equity/otcmarket/biweekly/shrt{settlement_date}.csv"
    )
    timeout_seconds: float = 30.0


class FinraShortInterestProvider:
    """Fetch and normalize FINRA short-interest file records."""

    def __init__(
        self,
        config: FinraShortInterestConfig | None = None,
        *,
        transport: TextTransport | None = None,
    ) -> None:
        self.config = config or FinraShortInterestConfig()
        self._transport = transport or self._urlopen_text

    def build_short_interest_records(
        self,
        symbols: Iterable[str],
        *,
        settlement_date: date | str | None = None,
        float_shares_by_symbol: Mapping[str, Any] | None = None,
        average_volume_by_symbol: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return provider-normalized short-interest records for symbols."""

        rows = self.fetch_short_interest_rows(settlement_date=settlement_date)
        rows_by_symbol = {
            str(row.get("symbol") or "").upper(): row
            for row in rows
            if row.get("symbol")
        }
        records: list[dict[str, Any]] = []
        for symbol in _normalize_symbols(symbols):
            row = rows_by_symbol.get(symbol)
            if row is None:
                continue

            float_shares = _lookup_float(float_shares_by_symbol, symbol)
            short_interest_shares = _as_float(row.get("short_interest_shares"))
            short_interest_pct_float = _pct_of(short_interest_shares, float_shares)
            average_daily_volume = _as_float(row.get("average_daily_volume"))
            if average_daily_volume is None:
                average_daily_volume = _lookup_float(average_volume_by_symbol, symbol)
            days_to_cover = _as_float(row.get("days_to_cover"))
            if days_to_cover is None and average_daily_volume:
                days_to_cover = short_interest_shares / average_daily_volume

            record = {
                "symbol": symbol,
                "finra_provider": "short_interest_file",
                "short_interest_settlement_date": row.get("settlement_date"),
                "short_interest_shares": short_interest_shares,
                "short_interest_pct_float": short_interest_pct_float,
                "days_to_cover": days_to_cover,
                "short_interest_average_daily_volume": average_daily_volume,
                "previous_short_interest_shares": row.get(
                    "previous_short_interest_shares"
                ),
                "short_interest_change_pct": row.get("short_interest_change_pct"),
                "short_interest_market": row.get("market"),
                "short_interest_issue_name": row.get("issue_name"),
            }
            records.append(
                {key: value for key, value in record.items() if value is not None}
            )
        return records

    def fetch_short_interest_rows(
        self, *, settlement_date: date | str | None = None
    ) -> list[dict[str, Any]]:
        """Download and parse a FINRA short-interest file."""

        url = (
            self.short_interest_file_url(settlement_date)
            if settlement_date is not None
            else self.latest_short_interest_file_url()
        )
        text = self._get_text(url)
        return parse_short_interest_file(text)

    def latest_short_interest_file_url(self) -> str:
        """Return the newest short-interest file URL linked from the catalog."""

        html = self._get_text(self.config.catalog_url)
        candidates: list[tuple[str, str]] = []
        for match in SHORT_INTEREST_LINK_RE.finditer(html):
            url = match.group(0)
            date_text = match.group("date") or match.group("path_date")
            if url.startswith("/"):
                url = f"https://cdn.finra.org{url}"
            candidates.append((date_text, url))
        if not candidates:
            raise FinraApiError("No FINRA short-interest file links found")
        return max(candidates, key=lambda item: item[0])[1]

    def short_interest_file_url(self, settlement_date: date | str) -> str:
        date_text = (
            settlement_date.strftime("%Y%m%d")
            if isinstance(settlement_date, date)
            else str(settlement_date).replace("-", "")
        )
        if not re.fullmatch(r"\d{8}", date_text):
            raise ValueError("settlement_date must be YYYYMMDD or YYYY-MM-DD")
        return self.config.file_url_template.format(settlement_date=date_text)

    def _get_text(self, url: str, params: Mapping[str, Any] | None = None) -> str:
        response = self._transport(url, {"Accept": "text/plain,text/csv,*/*"}, dict(params or {}))
        if not isinstance(response, str):
            raise FinraApiError("FINRA response was not text")
        return response

    def _urlopen_text(
        self, url: str, headers: Mapping[str, str], params: Mapping[str, Any]
    ) -> str:
        request_url = _with_query(url, params)
        request = Request(request_url, headers=dict(headers))
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                return response.read().decode("utf-8-sig")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise FinraApiError(f"FINRA HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise FinraApiError(f"FINRA request failed: {exc.reason}") from exc


def parse_short_interest_file(text: str) -> list[dict[str, Any]]:
    """Parse a FINRA short-interest file into normalized rows."""

    header_line = text.splitlines()[0] if text.splitlines() else ""
    delimiter = "|" if header_line.count("|") > header_line.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if reader.fieldnames is None:
        raise FinraApiError("FINRA short-interest file has no header")

    normalized_headers = {
        field: _normalize_header(field)
        for field in reader.fieldnames
        if field is not None
    }
    rows: list[dict[str, Any]] = []
    for raw_row in reader:
        row = {
            normalized_headers.get(key, ""): value
            for key, value in raw_row.items()
            if key is not None
        }
        symbol = _first_present(row, "symbol", "issuesymbol", "securitysymbol", "ticker")
        if not symbol:
            continue
        short_interest = _first_float(
            row,
            "currentshort",
            "currentshortinterest",
            "shortinterest",
            "shortinterestshares",
            "sharesshort",
            "current",
        )
        normalized = {
            "symbol": str(symbol).strip().upper(),
            "settlement_date": _date_text(
                _first_present(row, "settlementdate", "settledate", "date")
            ),
            "market": _first_present(row, "market", "exchange", "marketcategory"),
            "issue_name": _first_present(row, "issuename", "securityname", "name"),
            "short_interest_shares": short_interest,
            "previous_short_interest_shares": _first_float(
                row,
                "previousshort",
                "previousshortinterest",
                "priorshortinterest",
                "previous",
            ),
            "short_interest_change_pct": _first_float(
                row,
                "percentchange",
                "pctchange",
                "changepercent",
                "shortinterestchangepct",
            ),
            "average_daily_volume": _first_float(
                row,
                "averagedailysharevolume",
                "averagedailyvolume",
                "avgdailyvolume",
                "adv",
            ),
            "days_to_cover": _first_float(
                row,
                "daystocover",
                "shortinterestratio",
                "dtc",
            ),
        }
        rows.append({key: value for key, value in normalized.items() if value is not None})
    return rows


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    return [
        symbol
        for symbol in dict.fromkeys(str(item or "").strip().upper() for item in symbols)
        if symbol
    ]


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


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
        parsed = float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) else parsed


def _date_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    try:
        return datetime.fromisoformat(text[:10]).date().isoformat()
    except ValueError:
        return text


def _lookup_float(values_by_symbol: Mapping[str, Any] | None, symbol: str) -> float | None:
    if values_by_symbol is None:
        return None
    return _as_float(
        values_by_symbol.get(symbol)
        or values_by_symbol.get(symbol.upper())
        or values_by_symbol.get(symbol.lower())
    )


def _pct_of(value: float | None, denominator: float | None) -> float | None:
    if value is None or denominator is None or denominator == 0:
        return None
    return (value / denominator) * 100.0


def _with_query(url: str, params: Mapping[str, Any]) -> str:
    query = urlencode(
        {
            key: value
            for key, value in params.items()
            if value is not None and value != ""
        }
    )
    return f"{url}?{query}" if query else url
