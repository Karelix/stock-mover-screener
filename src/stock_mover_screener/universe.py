"""Universe filters for the pre-market stock mover screener."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "universe.json"


def _clean(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class UniverseRules:
    """Rules that define the base stock universe.

    Biotech is intentionally not excluded. The rules focus on instrument type,
    country, price, size, and liquidity.
    """

    allowed_countries: tuple[str, ...] = ("US",)
    allowed_security_types: tuple[str, ...] = ("common_stock", "common", "cs")
    excluded_security_types: tuple[str, ...] = (
        "adr",
        "closed_end_fund",
        "cef",
        "etf",
        "fund",
        "preferred",
        "preferred_stock",
        "right",
        "unit",
        "warrant",
    )
    excluded_symbol_patterns: tuple[str, ...] = (
        ".P",
        ".PR",
        ".R",
        ".U",
        ".W",
        ".WS",
        "-P",
        "-PR",
        "-R",
        "-U",
        "-W",
        "-WS",
        " PR",
        " WS",
    )
    min_price: float = 3.0
    min_market_cap: float = 100_000_000.0
    min_average_dollar_volume: float = 5_000_000.0
    include_biotech: bool = True


@dataclass(frozen=True)
class UniverseDecision:
    symbol: str
    passed: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


def load_universe_rules(path: str | Path = DEFAULT_CONFIG_PATH) -> UniverseRules:
    """Load universe rules from JSON config."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    filters = raw.get("filters", {})
    return UniverseRules(
        allowed_countries=tuple(filters.get("allowed_countries", ["US"])),
        allowed_security_types=tuple(
            _clean(item) for item in filters.get("allowed_security_types", [])
        ),
        excluded_security_types=tuple(
            _clean(item) for item in raw.get("excluded_security_types", [])
        ),
        excluded_symbol_patterns=tuple(raw.get("excluded_symbol_patterns", [])),
        min_price=float(filters.get("min_price", 3.0)),
        min_market_cap=float(filters.get("min_market_cap", 100_000_000)),
        min_average_dollar_volume=float(
            filters.get("min_average_dollar_volume", 5_000_000)
        ),
        include_biotech=bool(raw.get("include_biotech", True)),
    )


def evaluate_universe(
    record: Mapping[str, Any], rules: UniverseRules | None = None
) -> UniverseDecision:
    """Evaluate whether a normalized security record belongs in the base universe."""

    rules = rules or UniverseRules()
    symbol = str(record.get("symbol") or record.get("ticker") or "").strip().upper()
    reasons: list[str] = []

    if not symbol:
        reasons.append("missing_symbol")

    country = str(record.get("country") or "").strip().upper()
    if not country:
        reasons.append("missing_country")
    elif country not in {item.upper() for item in rules.allowed_countries}:
        reasons.append("non_us_country")

    security_type = _clean(
        record.get("security_type")
        or record.get("asset_type")
        or record.get("type")
        or record.get("class")
    )
    if not security_type:
        reasons.append("missing_security_type")
    elif security_type in rules.excluded_security_types:
        reasons.append(f"excluded_security_type:{security_type}")
    elif security_type and security_type not in rules.allowed_security_types:
        reasons.append(f"unsupported_security_type:{security_type}")

    if any(pattern.upper() in symbol for pattern in rules.excluded_symbol_patterns):
        reasons.append("excluded_symbol_pattern")

    price = _as_float(record.get("price") or record.get("last_price"))
    if price is None:
        reasons.append("missing_price")
    elif price < rules.min_price:
        reasons.append("price_below_minimum")

    market_cap = _as_float(record.get("market_cap"))
    if market_cap is None:
        reasons.append("missing_market_cap")
    elif market_cap < rules.min_market_cap:
        reasons.append("market_cap_below_minimum")

    average_dollar_volume = _as_float(
        record.get("average_dollar_volume")
        or record.get("avg_dollar_volume")
        or record.get("avg_daily_dollar_volume")
    )
    if average_dollar_volume is None:
        reasons.append("missing_average_dollar_volume")
    elif average_dollar_volume < rules.min_average_dollar_volume:
        reasons.append("average_dollar_volume_below_minimum")

    return UniverseDecision(symbol=symbol, passed=not reasons, reasons=tuple(reasons))


def filter_universe(
    records: Iterable[Mapping[str, Any]], rules: UniverseRules | None = None
) -> list[Mapping[str, Any]]:
    """Return records that pass the base universe filters."""

    active_rules = rules or UniverseRules()
    return [
        record
        for record in records
        if evaluate_universe(record, active_rules).passed
    ]
