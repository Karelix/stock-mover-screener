"""Pre-market mover scan metrics and filters."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "premarket_scan.json"
)


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


def _pct_change(new_value: float, old_value: float) -> float:
    return ((new_value - old_value) / old_value) * 100.0


def _capped_ratio(value: float, baseline: float, cap: float = 3.0) -> float:
    if baseline <= 0:
        return 0.0
    return min(max(value / baseline, 0.0), cap)


@dataclass(frozen=True)
class PremarketScanRules:
    min_premarket_move_pct: float = 10.0
    min_gap_pct: float = 8.0
    min_premarket_dollar_volume: float = 1_000_000.0
    min_relative_volume: float = 2.0
    min_atr_adjusted_move: float = 2.0
    require_positive_move: bool = True


@dataclass(frozen=True)
class PremarketMetrics:
    symbol: str
    premarket_price: float
    previous_close: float
    gap_price: float
    premarket_move_pct: float
    gap_pct: float
    premarket_volume: float
    premarket_dollar_volume: float
    relative_volume: float
    atr_14_pct: float
    atr_adjusted_move: float
    mover_score: float


@dataclass(frozen=True)
class PremarketMoverDecision:
    symbol: str
    passed: bool
    metrics: PremarketMetrics | None = None
    reasons: tuple[str, ...] = field(default_factory=tuple)


def load_premarket_scan_rules(
    path: str | Path = DEFAULT_CONFIG_PATH,
) -> PremarketScanRules:
    """Load pre-market scan thresholds from JSON config."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    filters = raw.get("filters", {})
    return PremarketScanRules(
        min_premarket_move_pct=float(filters.get("min_premarket_move_pct", 10.0)),
        min_gap_pct=float(filters.get("min_gap_pct", 8.0)),
        min_premarket_dollar_volume=float(
            filters.get("min_premarket_dollar_volume", 1_000_000)
        ),
        min_relative_volume=float(filters.get("min_relative_volume", 2.0)),
        min_atr_adjusted_move=float(filters.get("min_atr_adjusted_move", 2.0)),
        require_positive_move=bool(filters.get("require_positive_move", True)),
    )


def evaluate_premarket_mover(
    record: Mapping[str, Any], rules: PremarketScanRules | None = None
) -> PremarketMoverDecision:
    """Evaluate whether a normalized record is an abnormal pre-market upside mover."""

    active_rules = rules or PremarketScanRules()
    symbol = str(record.get("symbol") or record.get("ticker") or "").strip().upper()
    reasons: list[str] = []

    if not symbol:
        reasons.append("missing_symbol")

    premarket_price = _as_float(
        _first_present(
            record,
            "premarket_price",
            "premarket_last",
            "current_price",
            "last_price",
            "price",
        )
    )
    previous_close = _as_float(
        _first_present(record, "previous_close", "prev_close", "prior_close")
    )
    gap_price = _as_float(
        _first_present(
            record,
            "premarket_open",
            "indicative_open",
            "opening_indication",
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
    explicit_dollar_volume = _as_float(
        _first_present(record, "premarket_dollar_volume", "extended_hours_dollar_volume")
    )
    explicit_relative_volume = _as_float(
        _first_present(record, "premarket_relative_volume", "relative_volume", "rvol")
    )
    average_volume = _as_float(
        _first_present(
            record,
            "average_premarket_volume",
            "avg_premarket_volume",
            "average_premarket_volume_to_time",
            "average_volume",
            "avg_volume",
            "avg_daily_volume",
        )
    )
    atr_14_pct = _as_float(_first_present(record, "atr_14_pct", "atr14_pct"))
    atr_14 = _as_float(_first_present(record, "atr_14", "atr14"))

    if premarket_price is None or premarket_price <= 0:
        reasons.append("missing_or_invalid_premarket_price")
    if previous_close is None or previous_close <= 0:
        reasons.append("missing_or_invalid_previous_close")
    if gap_price is None or gap_price <= 0:
        reasons.append("missing_or_invalid_gap_price")
    if premarket_volume is None or premarket_volume < 0:
        reasons.append("missing_or_invalid_premarket_volume")

    if atr_14_pct is None and atr_14 is not None and previous_close and previous_close > 0:
        atr_14_pct = (atr_14 / previous_close) * 100.0
    if atr_14_pct is None or atr_14_pct <= 0:
        reasons.append("missing_or_invalid_atr")

    if explicit_relative_volume is None:
        if average_volume is None or average_volume <= 0:
            reasons.append("missing_or_invalid_average_volume")
        relative_volume = None
    else:
        relative_volume = explicit_relative_volume

    if reasons:
        return PremarketMoverDecision(
            symbol=symbol, passed=False, metrics=None, reasons=tuple(reasons)
        )

    assert premarket_price is not None
    assert previous_close is not None
    assert gap_price is not None
    assert premarket_volume is not None
    assert atr_14_pct is not None

    premarket_dollar_volume = (
        explicit_dollar_volume
        if explicit_dollar_volume is not None
        else premarket_price * premarket_volume
    )
    if relative_volume is None:
        assert average_volume is not None
        relative_volume = premarket_volume / average_volume

    premarket_move_pct = _pct_change(premarket_price, previous_close)
    gap_pct = _pct_change(gap_price, previous_close)
    atr_adjusted_move = premarket_move_pct / atr_14_pct
    mover_score = round(
        35.0
        * _capped_ratio(
            premarket_move_pct, active_rules.min_premarket_move_pct
        )
        + 25.0
        * _capped_ratio(
            premarket_dollar_volume,
            active_rules.min_premarket_dollar_volume,
        )
        + 20.0 * _capped_ratio(relative_volume, active_rules.min_relative_volume)
        + 20.0 * _capped_ratio(
            atr_adjusted_move, active_rules.min_atr_adjusted_move
        ),
        2,
    )

    metrics = PremarketMetrics(
        symbol=symbol,
        premarket_price=premarket_price,
        previous_close=previous_close,
        gap_price=gap_price,
        premarket_move_pct=premarket_move_pct,
        gap_pct=gap_pct,
        premarket_volume=premarket_volume,
        premarket_dollar_volume=premarket_dollar_volume,
        relative_volume=relative_volume,
        atr_14_pct=atr_14_pct,
        atr_adjusted_move=atr_adjusted_move,
        mover_score=mover_score,
    )

    if active_rules.require_positive_move and premarket_move_pct <= 0:
        reasons.append("not_upside_move")
    if premarket_move_pct < active_rules.min_premarket_move_pct:
        reasons.append("premarket_move_below_minimum")
    if gap_pct < active_rules.min_gap_pct:
        reasons.append("gap_below_minimum")
    if premarket_dollar_volume < active_rules.min_premarket_dollar_volume:
        reasons.append("premarket_dollar_volume_below_minimum")
    if relative_volume < active_rules.min_relative_volume:
        reasons.append("relative_volume_below_minimum")
    if atr_adjusted_move < active_rules.min_atr_adjusted_move:
        reasons.append("atr_adjusted_move_below_minimum")

    return PremarketMoverDecision(
        symbol=symbol,
        passed=not reasons,
        metrics=metrics,
        reasons=tuple(reasons),
    )


def evaluate_premarket_movers(
    records: Iterable[Mapping[str, Any]], rules: PremarketScanRules | None = None
) -> list[PremarketMoverDecision]:
    """Evaluate all records and keep pass/fail reasons for auditability."""

    active_rules = rules or PremarketScanRules()
    return [evaluate_premarket_mover(record, active_rules) for record in records]


def scan_premarket_movers(
    records: Iterable[Mapping[str, Any]], rules: PremarketScanRules | None = None
) -> list[PremarketMoverDecision]:
    """Return passing pre-market movers sorted by strongest mover score."""

    decisions = evaluate_premarket_movers(records, rules)
    passed = [decision for decision in decisions if decision.passed]
    return sorted(
        passed,
        key=lambda decision: decision.metrics.mover_score if decision.metrics else 0.0,
        reverse=True,
    )
