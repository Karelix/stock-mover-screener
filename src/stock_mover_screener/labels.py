"""Final pre-market candidate labels and serialization helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import json
from pathlib import Path
from typing import Any

from stock_mover_screener.catalyst import CatalystAssessment
from stock_mover_screener.dilution import DilutionAssessment
from stock_mover_screener.fundamentals import FundamentalAssessment
from stock_mover_screener.hype import HypeAssessment
from stock_mover_screener.liquidity import LiquidityDecision
from stock_mover_screener.premarket import PremarketMoverDecision
from stock_mover_screener.squeeze import SqueezeAssessment


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "labels.json"


THESIS_LEVEL_POINTS = {
    "high": 3,
    "moderate": 2,
    "weak": 3,
    "none": 2,
    "low": 0,
    "medium": 0,
    "strong": -4,
    "unknown": 0,
}

DANGER_LEVEL_POINTS = {
    "extreme": 4,
    "high": 3,
    "moderate": 2,
    "low": 0,
    "unknown": 1,
}

LABEL_PRIORITY = {
    "Prime Watch": 0,
    "Watch Only": 1,
    "Too Dangerous": 2,
    "Needs More Data": 3,
    "Likely Real Catalyst": 4,
    "Ignore": 5,
}


@dataclass(frozen=True)
class LabelRules:
    prime_watch_thesis_score: int = 8
    watch_only_thesis_score: int = 5
    needs_more_data_unknown_layers: int = 3
    likely_real_catalyst_max_thesis_score: int = 4
    confidence_base: int = 35
    confidence_known_layer_points: int = 8
    confidence_thesis_score_points: int = 3
    confidence_danger_score_points: int = 2
    confidence_missing_layer_penalty: int = 10
    confidence_minimum: int = 20
    confidence_maximum: int = 95


@dataclass(frozen=True)
class PreMarketLabel:
    symbol: str
    final_label: str
    confidence: int
    thesis_score: int
    danger_score: int
    summary: str
    reasons: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


def load_label_rules(path: str | Path = DEFAULT_CONFIG_PATH) -> LabelRules:
    """Load final label rules from JSON config."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    thresholds = raw.get("thresholds", {})
    confidence = raw.get("confidence", {})
    return LabelRules(
        prime_watch_thesis_score=int(thresholds.get("prime_watch_thesis_score", 8)),
        watch_only_thesis_score=int(thresholds.get("watch_only_thesis_score", 5)),
        needs_more_data_unknown_layers=int(
            thresholds.get("needs_more_data_unknown_layers", 3)
        ),
        likely_real_catalyst_max_thesis_score=int(
            thresholds.get("likely_real_catalyst_max_thesis_score", 4)
        ),
        confidence_base=int(confidence.get("base", 35)),
        confidence_known_layer_points=int(confidence.get("known_layer_points", 8)),
        confidence_thesis_score_points=int(confidence.get("thesis_score_points", 3)),
        confidence_danger_score_points=int(confidence.get("danger_score_points", 2)),
        confidence_missing_layer_penalty=int(
            confidence.get("missing_layer_penalty", 10)
        ),
        confidence_minimum=int(confidence.get("minimum", 20)),
        confidence_maximum=int(confidence.get("maximum", 95)),
    )


def _level_points(level: str, points: dict[str, int]) -> int:
    return points.get(str(level or "unknown").lower(), 0)


def _confidence(
    rules: LabelRules,
    thesis_score: int,
    danger_score: int,
    known_layers: int,
    unknown_layers: int,
) -> int:
    raw = (
        rules.confidence_base
        + known_layers * rules.confidence_known_layer_points
        + max(thesis_score, 0) * rules.confidence_thesis_score_points
        + danger_score * rules.confidence_danger_score_points
        - unknown_layers * rules.confidence_missing_layer_penalty
    )
    return max(rules.confidence_minimum, min(rules.confidence_maximum, raw))


def evaluate_pre_market_label(
    *,
    symbol: str,
    premarket: PremarketMoverDecision,
    fundamentals: FundamentalAssessment,
    dilution: DilutionAssessment,
    catalyst: CatalystAssessment,
    hype: HypeAssessment,
    squeeze: SqueezeAssessment,
    liquidity: LiquidityDecision | None = None,
    rules: LabelRules | None = None,
) -> PreMarketLabel:
    """Create a final pre-market label while keeping all underlying scores available."""

    active_rules = rules or LabelRules()
    reasons: list[str] = []
    warnings: list[str] = []

    fundamentals_points = _level_points(
        fundamentals.weakness_level, THESIS_LEVEL_POINTS
    )
    dilution_points = _level_points(dilution.risk_level, THESIS_LEVEL_POINTS)
    catalyst_points = _level_points(catalyst.category, THESIS_LEVEL_POINTS)
    hype_points = _level_points(hype.hype_level, THESIS_LEVEL_POINTS)
    danger_score = _level_points(squeeze.risk_level, DANGER_LEVEL_POINTS)
    thesis_score = fundamentals_points + dilution_points + catalyst_points + hype_points

    layer_levels = {
        "fundamentals": fundamentals.weakness_level,
        "dilution": dilution.risk_level,
        "catalyst": catalyst.category,
        "hype": hype.hype_level,
        "squeeze": squeeze.risk_level,
    }
    unknown_layers = tuple(
        layer for layer, level in layer_levels.items() if level == "unknown"
    )
    known_layers = len(layer_levels) - len(unknown_layers)

    if fundamentals.weakness_level in {"moderate", "high"}:
        reasons.append(f"fundamentals_{fundamentals.weakness_level}")
    if dilution.risk_level in {"moderate", "high"}:
        reasons.append(f"dilution_{dilution.risk_level}")
    if catalyst.category in {"weak", "none", "strong"}:
        reasons.append(f"catalyst_{catalyst.category}")
    if hype.hype_level in {"moderate", "high"}:
        reasons.append(f"hype_{hype.hype_level}")
    if squeeze.risk_level in {"moderate", "high", "extreme"}:
        reasons.append(f"squeeze_{squeeze.risk_level}")

    if liquidity is None:
        warnings.append("liquidity_filter_not_applied")
    elif liquidity.warnings:
        warnings.extend(f"liquidity:{warning}" for warning in liquidity.warnings)

    for layer in unknown_layers:
        warnings.append(f"{layer}_unknown")

    if len(unknown_layers) >= active_rules.needs_more_data_unknown_layers:
        final_label = "Needs More Data"
    elif (
        catalyst.category == "strong"
        and thesis_score <= active_rules.likely_real_catalyst_max_thesis_score
    ):
        final_label = "Likely Real Catalyst"
    elif (
        squeeze.risk_level == "extreme"
        and thesis_score >= active_rules.watch_only_thesis_score
    ):
        final_label = "Too Dangerous"
    elif (
        thesis_score >= active_rules.prime_watch_thesis_score
        and squeeze.risk_level != "extreme"
    ):
        final_label = "Prime Watch"
    elif thesis_score >= active_rules.watch_only_thesis_score:
        final_label = "Watch Only"
    else:
        final_label = "Ignore"

    confidence = _confidence(
        active_rules,
        thesis_score=thesis_score,
        danger_score=danger_score,
        known_layers=known_layers,
        unknown_layers=len(unknown_layers),
    )

    move_text = "unknown move"
    if premarket.metrics:
        move_text = f"{premarket.metrics.premarket_move_pct:.1f}% pre-market move"

    summary = (
        f"{final_label}: {move_text}; thesis score {thesis_score}; "
        f"squeeze risk {squeeze.risk_level}."
    )

    return PreMarketLabel(
        symbol=symbol,
        final_label=final_label,
        confidence=confidence,
        thesis_score=thesis_score,
        danger_score=danger_score,
        summary=summary,
        reasons=tuple(dict.fromkeys(reasons)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def candidate_to_full_dict(candidate: Any) -> dict[str, Any]:
    """Return every nested dataclass field for full-detail inspection/export."""

    if is_dataclass(candidate):
        return asdict(candidate)
    raise TypeError("candidate_to_full_dict expects a dataclass candidate object")


def candidate_to_summary_row(candidate: Any) -> dict[str, Any]:
    """Return a flat row with labels plus the main scores for tables."""

    premarket = getattr(candidate, "premarket", None)
    premarket_metrics = getattr(premarket, "metrics", None)
    liquidity = getattr(candidate, "liquidity", None)
    liquidity_metrics = getattr(liquidity, "metrics", None)
    fundamentals = getattr(candidate, "fundamentals", None)
    dilution = getattr(candidate, "dilution", None)
    catalyst = getattr(candidate, "catalyst", None)
    hype = getattr(candidate, "hype", None)
    squeeze = getattr(candidate, "squeeze", None)
    label = getattr(candidate, "label", None)

    return {
        "symbol": getattr(candidate, "symbol", ""),
        "final_label": getattr(label, "final_label", None),
        "confidence": getattr(label, "confidence", None),
        "summary": getattr(label, "summary", None),
        "premarket_move_pct": getattr(premarket_metrics, "premarket_move_pct", None),
        "mover_score": getattr(premarket_metrics, "mover_score", None),
        "liquidity_score": getattr(liquidity_metrics, "liquidity_score", None),
        "fundamental_level": getattr(fundamentals, "weakness_level", None),
        "fundamental_score": getattr(fundamentals, "weakness_score", None),
        "dilution_level": getattr(dilution, "risk_level", None),
        "dilution_score": getattr(dilution, "dilution_risk_score", None),
        "catalyst_category": getattr(catalyst, "category", None),
        "weak_catalyst_score": getattr(catalyst, "weak_catalyst_score", None),
        "hype_level": getattr(hype, "hype_level", None),
        "hype_score": getattr(hype, "hype_score", None),
        "squeeze_level": getattr(squeeze, "risk_level", None),
        "squeeze_score": getattr(squeeze, "squeeze_risk_score", None),
    }
