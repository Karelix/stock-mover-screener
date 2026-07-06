"""Liquidity filters and float-risk flags for pre-market candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "liquidity.json"


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return None


def _normalized_ratio(value: float, baseline: float) -> float:
    if baseline <= 0:
        return 0.0
    return min(max(value / baseline, 0.0), 3.0) / 3.0


@dataclass(frozen=True)
class LiquidityRules:
    min_premarket_volume: float = 50_000.0
    min_premarket_dollar_volume: float = 1_000_000.0
    min_average_dollar_volume: float = 5_000_000.0
    max_spread_pct: float = 3.0
    allow_missing_spread: bool = True
    low_float_shares: float = 20_000_000.0
    very_low_float_shares: float = 10_000_000.0


@dataclass(frozen=True)
class LiquidityMetrics:
    symbol: str
    price: float
    premarket_volume: float
    premarket_dollar_volume: float
    average_dollar_volume: float
    bid: float | None
    ask: float | None
    spread_pct: float | None
    float_shares: float | None
    liquidity_score: float


@dataclass(frozen=True)
class LiquidityDecision:
    symbol: str
    passed: bool
    metrics: LiquidityMetrics | None = None
    reasons: tuple[str, ...] = field(default_factory=tuple)
    risk_flags: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


def load_liquidity_rules(path: str | Path = DEFAULT_CONFIG_PATH) -> LiquidityRules:
    """Load liquidity thresholds and float-risk cutoffs from JSON config."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    filters = raw.get("filters", {})
    risk_flags = raw.get("risk_flags", {})
    return LiquidityRules(
        min_premarket_volume=float(filters.get("min_premarket_volume", 50_000)),
        min_premarket_dollar_volume=float(
            filters.get("min_premarket_dollar_volume", 1_000_000)
        ),
        min_average_dollar_volume=float(
            filters.get("min_average_dollar_volume", 5_000_000)
        ),
        max_spread_pct=float(filters.get("max_spread_pct", 3.0)),
        allow_missing_spread=bool(filters.get("allow_missing_spread", True)),
        low_float_shares=float(risk_flags.get("low_float_shares", 20_000_000)),
        very_low_float_shares=float(
            risk_flags.get("very_low_float_shares", 10_000_000)
        ),
    )


def evaluate_liquidity(
    record: Mapping[str, Any], rules: LiquidityRules | None = None
) -> LiquidityDecision:
    """Evaluate whether a pre-market candidate is liquid enough to review."""

    active_rules = rules or LiquidityRules()
    symbol = str(record.get("symbol") or record.get("ticker") or "").strip().upper()
    reasons: list[str] = []
    warnings: list[str] = []
    risk_flags: list[str] = []

    if not symbol:
        reasons.append("missing_symbol")

    price = _as_float(
        _first_present(
            record,
            "premarket_price",
            "premarket_last",
            "current_price",
            "last_price",
            "price",
        )
    )
    premarket_volume = _as_float(
        _first_present(record, "premarket_volume", "extended_hours_volume", "volume")
    )
    premarket_dollar_volume = _as_float(
        _first_present(record, "premarket_dollar_volume", "extended_hours_dollar_volume")
    )
    average_dollar_volume = _as_float(
        _first_present(
            record,
            "average_dollar_volume",
            "avg_dollar_volume",
            "avg_daily_dollar_volume",
        )
    )
    bid = _as_float(_first_present(record, "premarket_bid", "bid", "best_bid"))
    ask = _as_float(_first_present(record, "premarket_ask", "ask", "best_ask"))
    spread_pct = _as_float(_first_present(record, "spread_pct", "premarket_spread_pct"))
    float_shares = _as_float(
        _first_present(record, "float_shares", "shares_float", "public_float", "float")
    )

    if price is None or price <= 0:
        reasons.append("missing_or_invalid_price")
    if premarket_volume is None or premarket_volume < 0:
        reasons.append("missing_or_invalid_premarket_volume")
    if average_dollar_volume is None or average_dollar_volume < 0:
        reasons.append("missing_or_invalid_average_dollar_volume")

    if premarket_dollar_volume is None and price is not None and premarket_volume is not None:
        premarket_dollar_volume = price * premarket_volume
    if premarket_dollar_volume is None or premarket_dollar_volume < 0:
        reasons.append("missing_or_invalid_premarket_dollar_volume")

    if spread_pct is None:
        if bid is not None and ask is not None:
            if bid <= 0 or ask <= 0 or ask < bid:
                reasons.append("invalid_bid_ask_spread")
            else:
                midpoint = (bid + ask) / 2.0
                spread_pct = ((ask - bid) / midpoint) * 100.0
        elif active_rules.allow_missing_spread:
            warnings.append("spread_data_missing")
        else:
            reasons.append("missing_spread_data")

    if float_shares is None:
        warnings.append("float_data_missing")
    elif float_shares <= active_rules.very_low_float_shares:
        risk_flags.append("very_low_float")
    elif float_shares <= active_rules.low_float_shares:
        risk_flags.append("low_float")

    if reasons:
        return LiquidityDecision(
            symbol=symbol,
            passed=False,
            metrics=None,
            reasons=tuple(reasons),
            risk_flags=tuple(risk_flags),
            warnings=tuple(warnings),
        )

    assert price is not None
    assert premarket_volume is not None
    assert premarket_dollar_volume is not None
    assert average_dollar_volume is not None

    if premarket_volume < active_rules.min_premarket_volume:
        reasons.append("premarket_volume_below_minimum")
    if premarket_dollar_volume < active_rules.min_premarket_dollar_volume:
        reasons.append("premarket_dollar_volume_below_minimum")
    if average_dollar_volume < active_rules.min_average_dollar_volume:
        reasons.append("average_dollar_volume_below_minimum")
    if spread_pct is not None and spread_pct > active_rules.max_spread_pct:
        reasons.append("spread_above_maximum")

    spread_component = (
        0.5
        if spread_pct is None
        else max(0.0, 1.0 - (spread_pct / active_rules.max_spread_pct))
    )
    liquidity_score = round(
        40.0
        * _normalized_ratio(
            premarket_dollar_volume, active_rules.min_premarket_dollar_volume
        )
        + 25.0
        * _normalized_ratio(
            average_dollar_volume, active_rules.min_average_dollar_volume
        )
        + 15.0
        * _normalized_ratio(premarket_volume, active_rules.min_premarket_volume)
        + 20.0 * spread_component,
        2,
    )

    metrics = LiquidityMetrics(
        symbol=symbol,
        price=price,
        premarket_volume=premarket_volume,
        premarket_dollar_volume=premarket_dollar_volume,
        average_dollar_volume=average_dollar_volume,
        bid=bid,
        ask=ask,
        spread_pct=spread_pct,
        float_shares=float_shares,
        liquidity_score=liquidity_score,
    )

    return LiquidityDecision(
        symbol=symbol,
        passed=not reasons,
        metrics=metrics,
        reasons=tuple(reasons),
        risk_flags=tuple(risk_flags),
        warnings=tuple(warnings),
    )


def evaluate_liquidity_batch(
    records: Iterable[Mapping[str, Any]], rules: LiquidityRules | None = None
) -> list[LiquidityDecision]:
    """Evaluate liquidity for a batch of normalized records."""

    active_rules = rules or LiquidityRules()
    return [evaluate_liquidity(record, active_rules) for record in records]


def filter_liquid_records(
    records: Iterable[Mapping[str, Any]], rules: LiquidityRules | None = None
) -> list[Mapping[str, Any]]:
    """Return records that pass the Step 3 liquidity screen."""

    active_rules = rules or LiquidityRules()
    return [
        record
        for record in records
        if evaluate_liquidity(record, active_rules).passed
    ]
