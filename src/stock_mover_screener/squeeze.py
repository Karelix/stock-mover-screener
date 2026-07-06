"""Squeeze and shortability risk scoring for pre-market candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "squeeze.json"


def _as_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "t", "yes", "y", "1", "hard"}:
            return True
        if normalized in {"false", "f", "no", "n", "0", "easy"}:
            return False
    return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed):
        return None
    return parsed


def _first_present(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return None


def _pct_change(new_value: float, old_value: float) -> float:
    return ((new_value - old_value) / old_value) * 100.0


@dataclass(frozen=True)
class SqueezeRules:
    moderate_score: int = 4
    high_score: int = 8
    extreme_score: int = 12
    low_float_shares: float = 20_000_000.0
    very_low_float_shares: float = 10_000_000.0
    high_short_interest_pct: float = 20.0
    extreme_short_interest_pct: float = 40.0
    high_days_to_cover: float = 5.0
    high_borrow_fee_pct: float = 20.0
    extreme_borrow_fee_pct: float = 80.0
    low_borrow_available_shares: float = 100_000.0
    extreme_premarket_move_pct: float = 50.0
    high_hype_score: int = 8
    high_call_volume_ratio: float = 3.0
    repeated_halts_count: int = 2
    very_low_float_points: int = 4
    low_float_points: int = 2
    extreme_short_interest_points: int = 4
    high_short_interest_points: int = 3
    high_days_to_cover_points: int = 3
    extreme_borrow_fee_points: int = 4
    high_borrow_fee_points: int = 3
    hard_to_borrow_points: int = 3
    low_borrow_availability_points: int = 2
    no_borrow_available_points: int = 4
    extreme_premarket_move_points: int = 3
    high_hype_points: int = 2
    repeated_halts_points: int = 3
    call_volume_explosion_points: int = 2


@dataclass(frozen=True)
class SqueezeMetrics:
    symbol: str
    float_shares: float | None
    short_interest_pct_float: float | None
    days_to_cover: float | None
    borrow_fee_pct: float | None
    hard_to_borrow: bool | None
    borrow_available_shares: float | None
    premarket_move_pct: float | None
    hype_score: float | None
    halts_count: int | None
    call_volume_ratio: float | None
    assessed_signal_count: int


@dataclass(frozen=True)
class SqueezeAssessment:
    symbol: str
    squeeze_risk_score: int
    risk_level: str
    metrics: SqueezeMetrics
    reasons: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


def load_squeeze_rules(path: str | Path = DEFAULT_CONFIG_PATH) -> SqueezeRules:
    """Load squeeze and shortability risk rules from JSON config."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    thresholds = raw.get("thresholds", {})
    points = raw.get("points", {})
    return SqueezeRules(
        moderate_score=int(thresholds.get("moderate_score", 4)),
        high_score=int(thresholds.get("high_score", 8)),
        extreme_score=int(thresholds.get("extreme_score", 12)),
        low_float_shares=float(thresholds.get("low_float_shares", 20_000_000)),
        very_low_float_shares=float(thresholds.get("very_low_float_shares", 10_000_000)),
        high_short_interest_pct=float(thresholds.get("high_short_interest_pct", 20.0)),
        extreme_short_interest_pct=float(
            thresholds.get("extreme_short_interest_pct", 40.0)
        ),
        high_days_to_cover=float(thresholds.get("high_days_to_cover", 5.0)),
        high_borrow_fee_pct=float(thresholds.get("high_borrow_fee_pct", 20.0)),
        extreme_borrow_fee_pct=float(thresholds.get("extreme_borrow_fee_pct", 80.0)),
        low_borrow_available_shares=float(
            thresholds.get("low_borrow_available_shares", 100_000)
        ),
        extreme_premarket_move_pct=float(
            thresholds.get("extreme_premarket_move_pct", 50.0)
        ),
        high_hype_score=int(thresholds.get("high_hype_score", 8)),
        high_call_volume_ratio=float(thresholds.get("high_call_volume_ratio", 3.0)),
        repeated_halts_count=int(thresholds.get("repeated_halts_count", 2)),
        very_low_float_points=int(points.get("very_low_float", 4)),
        low_float_points=int(points.get("low_float", 2)),
        extreme_short_interest_points=int(points.get("extreme_short_interest", 4)),
        high_short_interest_points=int(points.get("high_short_interest", 3)),
        high_days_to_cover_points=int(points.get("high_days_to_cover", 3)),
        extreme_borrow_fee_points=int(points.get("extreme_borrow_fee", 4)),
        high_borrow_fee_points=int(points.get("high_borrow_fee", 3)),
        hard_to_borrow_points=int(points.get("hard_to_borrow", 3)),
        low_borrow_availability_points=int(points.get("low_borrow_availability", 2)),
        no_borrow_available_points=int(points.get("no_borrow_available", 4)),
        extreme_premarket_move_points=int(points.get("extreme_premarket_move", 3)),
        high_hype_points=int(points.get("high_hype", 2)),
        repeated_halts_points=int(points.get("repeated_halts", 3)),
        call_volume_explosion_points=int(points.get("call_volume_explosion", 2)),
    )


def evaluate_squeeze(
    record: Mapping[str, Any], rules: SqueezeRules | None = None
) -> SqueezeAssessment:
    """Score squeeze and shortability danger without filtering the record out."""

    active_rules = rules or SqueezeRules()
    symbol = str(record.get("symbol") or record.get("ticker") or "").strip().upper()
    reasons: list[str] = []
    warnings: list[str] = []
    score = 0
    assessed_signal_count = 0

    float_shares = _as_float(
        _first_present(record, "float_shares", "shares_float", "public_float", "float")
    )
    short_interest_pct_float = _as_float(
        _first_present(
            record,
            "short_interest_pct_float",
            "short_percent_float",
            "short_interest_pct",
            "short_float_pct",
        )
    )
    days_to_cover = _as_float(
        _first_present(record, "days_to_cover", "short_interest_days_to_cover")
    )
    borrow_fee_pct = _as_float(
        _first_present(record, "borrow_fee_pct", "borrow_rate_pct", "stock_loan_fee_pct")
    )
    hard_to_borrow = _as_bool(
        _first_present(record, "hard_to_borrow", "htb", "is_hard_to_borrow")
    )
    borrow_available_shares = _as_float(
        _first_present(
            record,
            "borrow_available_shares",
            "shares_available_to_borrow",
            "shortable_shares_available",
        )
    )
    premarket_move_pct = _as_float(
        _first_present(record, "premarket_move_pct", "premarket_change_pct")
    )
    premarket_price = _as_float(
        _first_present(record, "premarket_price", "premarket_last", "price")
    )
    previous_close = _as_float(
        _first_present(record, "previous_close", "prev_close", "prior_close")
    )
    hype_score = _as_float(_first_present(record, "hype_score"))
    halts_count_float = _as_float(
        _first_present(record, "halts_count", "intraday_halts_count", "halt_count")
    )
    halts_count = int(halts_count_float) if halts_count_float is not None else None
    call_volume_ratio = _as_float(
        _first_present(
            record,
            "call_volume_ratio",
            "options_call_volume_ratio",
            "call_volume_relative",
        )
    )
    call_volume = _as_float(_first_present(record, "call_volume", "options_call_volume"))
    average_call_volume = _as_float(
        _first_present(record, "average_call_volume", "avg_call_volume")
    )

    if premarket_move_pct is None and premarket_price is not None and previous_close:
        premarket_move_pct = _pct_change(premarket_price, previous_close)

    if call_volume_ratio is None and call_volume is not None and average_call_volume:
        call_volume_ratio = call_volume / average_call_volume

    if not symbol:
        warnings.append("missing_symbol")

    def add_reason(reason: str, points: int) -> None:
        nonlocal score
        score += points
        reasons.append(reason)

    if float_shares is None:
        warnings.append("missing_float_shares")
    else:
        assessed_signal_count += 1
        if float_shares <= active_rules.very_low_float_shares:
            add_reason("very_low_float", active_rules.very_low_float_points)
        elif float_shares <= active_rules.low_float_shares:
            add_reason("low_float", active_rules.low_float_points)

    if short_interest_pct_float is None:
        warnings.append("missing_short_interest_pct_float")
    else:
        assessed_signal_count += 1
        if short_interest_pct_float >= active_rules.extreme_short_interest_pct:
            add_reason(
                "extreme_short_interest",
                active_rules.extreme_short_interest_points,
            )
        elif short_interest_pct_float >= active_rules.high_short_interest_pct:
            add_reason("high_short_interest", active_rules.high_short_interest_points)

    if days_to_cover is None:
        warnings.append("missing_days_to_cover")
    else:
        assessed_signal_count += 1
        if days_to_cover >= active_rules.high_days_to_cover:
            add_reason("high_days_to_cover", active_rules.high_days_to_cover_points)

    if borrow_fee_pct is None:
        warnings.append("missing_borrow_fee_pct")
    else:
        assessed_signal_count += 1
        if borrow_fee_pct >= active_rules.extreme_borrow_fee_pct:
            add_reason("extreme_borrow_fee", active_rules.extreme_borrow_fee_points)
        elif borrow_fee_pct >= active_rules.high_borrow_fee_pct:
            add_reason("high_borrow_fee", active_rules.high_borrow_fee_points)

    if hard_to_borrow is None:
        warnings.append("missing_hard_to_borrow")
    else:
        assessed_signal_count += 1
        if hard_to_borrow:
            add_reason("hard_to_borrow", active_rules.hard_to_borrow_points)

    if borrow_available_shares is None:
        warnings.append("missing_borrow_available_shares")
    else:
        assessed_signal_count += 1
        if borrow_available_shares <= 0:
            add_reason("no_borrow_available", active_rules.no_borrow_available_points)
        elif borrow_available_shares <= active_rules.low_borrow_available_shares:
            add_reason(
                "low_borrow_availability",
                active_rules.low_borrow_availability_points,
            )

    if premarket_move_pct is None:
        warnings.append("missing_premarket_move_pct")
    else:
        assessed_signal_count += 1
        if premarket_move_pct >= active_rules.extreme_premarket_move_pct:
            add_reason(
                "extreme_premarket_move",
                active_rules.extreme_premarket_move_points,
            )

    if hype_score is None:
        warnings.append("missing_hype_score")
    else:
        assessed_signal_count += 1
        if hype_score >= active_rules.high_hype_score:
            add_reason("high_hype", active_rules.high_hype_points)

    if halts_count is None:
        warnings.append("missing_halts_count")
    else:
        assessed_signal_count += 1
        if halts_count >= active_rules.repeated_halts_count:
            add_reason("repeated_halts", active_rules.repeated_halts_points)

    if call_volume_ratio is None:
        warnings.append("missing_call_volume_ratio")
    else:
        assessed_signal_count += 1
        if call_volume_ratio >= active_rules.high_call_volume_ratio:
            add_reason(
                "call_volume_explosion",
                active_rules.call_volume_explosion_points,
            )

    if assessed_signal_count == 0:
        risk_level = "unknown"
        warnings.append("squeeze_data_missing")
    elif score >= active_rules.extreme_score:
        risk_level = "extreme"
    elif score >= active_rules.high_score:
        risk_level = "high"
    elif score >= active_rules.moderate_score:
        risk_level = "moderate"
    else:
        risk_level = "low"

    metrics = SqueezeMetrics(
        symbol=symbol,
        float_shares=float_shares,
        short_interest_pct_float=short_interest_pct_float,
        days_to_cover=days_to_cover,
        borrow_fee_pct=borrow_fee_pct,
        hard_to_borrow=hard_to_borrow,
        borrow_available_shares=borrow_available_shares,
        premarket_move_pct=premarket_move_pct,
        hype_score=hype_score,
        halts_count=halts_count,
        call_volume_ratio=call_volume_ratio,
        assessed_signal_count=assessed_signal_count,
    )

    return SqueezeAssessment(
        symbol=symbol,
        squeeze_risk_score=score,
        risk_level=risk_level,
        metrics=metrics,
        reasons=tuple(dict.fromkeys(reasons)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def evaluate_squeeze_batch(
    records: Iterable[Mapping[str, Any]], rules: SqueezeRules | None = None
) -> list[SqueezeAssessment]:
    """Score squeeze and shortability risk for a batch of normalized records."""

    active_rules = rules or SqueezeRules()
    return [evaluate_squeeze(record, active_rules) for record in records]
