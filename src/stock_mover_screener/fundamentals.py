"""Fundamental weakness scoring for pre-market short-candidate research."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "fundamentals.json"
)


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


def _free_cash_flow(
    explicit_free_cash_flow: float | None,
    operating_cash_flow: float | None,
    capital_expenditure: float | None,
) -> float | None:
    if explicit_free_cash_flow is not None:
        return explicit_free_cash_flow
    if operating_cash_flow is None or capital_expenditure is None:
        return None
    if capital_expenditure < 0:
        return operating_cash_flow + capital_expenditure
    return operating_cash_flow - capital_expenditure


@dataclass(frozen=True)
class FundamentalRules:
    moderate_score: int = 4
    high_score: int = 8
    weak_current_ratio: float = 1.0
    high_debt_to_equity: float = 2.0
    low_cash_runway_years: float = 1.0
    min_meaningful_revenue: float = 1_000_000.0
    high_price_to_sales: float = 20.0
    negative_net_income_points: int = 2
    negative_operating_cash_flow_points: int = 2
    negative_free_cash_flow_points: int = 2
    declining_revenue_yoy_points: int = 1
    weak_current_ratio_points: int = 1
    high_debt_to_equity_points: int = 1
    low_cash_runway_points: int = 2
    no_meaningful_revenue_points: int = 2
    high_price_to_sales_points: int = 1


@dataclass(frozen=True)
class FundamentalMetrics:
    symbol: str
    net_income: float | None
    operating_cash_flow: float | None
    free_cash_flow: float | None
    revenue: float | None
    revenue_growth_yoy_pct: float | None
    current_ratio: float | None
    debt_to_equity: float | None
    cash_runway_years: float | None
    price_to_sales: float | None
    assessed_signal_count: int


@dataclass(frozen=True)
class FundamentalAssessment:
    symbol: str
    weakness_score: int
    weakness_level: str
    metrics: FundamentalMetrics
    reasons: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


def load_fundamental_rules(
    path: str | Path = DEFAULT_CONFIG_PATH,
) -> FundamentalRules:
    """Load fundamental weakness scoring rules from JSON config."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    thresholds = raw.get("thresholds", {})
    points = raw.get("points", {})
    return FundamentalRules(
        moderate_score=int(thresholds.get("moderate_score", 4)),
        high_score=int(thresholds.get("high_score", 8)),
        weak_current_ratio=float(thresholds.get("weak_current_ratio", 1.0)),
        high_debt_to_equity=float(thresholds.get("high_debt_to_equity", 2.0)),
        low_cash_runway_years=float(
            thresholds.get("low_cash_runway_years", 1.0)
        ),
        min_meaningful_revenue=float(
            thresholds.get("min_meaningful_revenue", 1_000_000)
        ),
        high_price_to_sales=float(thresholds.get("high_price_to_sales", 20.0)),
        negative_net_income_points=int(points.get("negative_net_income", 2)),
        negative_operating_cash_flow_points=int(
            points.get("negative_operating_cash_flow", 2)
        ),
        negative_free_cash_flow_points=int(points.get("negative_free_cash_flow", 2)),
        declining_revenue_yoy_points=int(points.get("declining_revenue_yoy", 1)),
        weak_current_ratio_points=int(points.get("weak_current_ratio", 1)),
        high_debt_to_equity_points=int(points.get("high_debt_to_equity", 1)),
        low_cash_runway_points=int(points.get("low_cash_runway", 2)),
        no_meaningful_revenue_points=int(points.get("no_meaningful_revenue", 2)),
        high_price_to_sales_points=int(points.get("high_price_to_sales", 1)),
    )


def evaluate_fundamentals(
    record: Mapping[str, Any], rules: FundamentalRules | None = None
) -> FundamentalAssessment:
    """Score fundamental weakness without filtering the record out."""

    active_rules = rules or FundamentalRules()
    symbol = str(record.get("symbol") or record.get("ticker") or "").strip().upper()
    reasons: list[str] = []
    warnings: list[str] = []
    score = 0
    assessed_signal_count = 0

    net_income = _as_float(
        _first_present(record, "net_income_ttm", "net_income", "net_income_latest")
    )
    operating_cash_flow = _as_float(
        _first_present(
            record,
            "operating_cash_flow_ttm",
            "operating_cash_flow",
            "cash_flow_from_operations",
        )
    )
    capital_expenditure = _as_float(
        _first_present(record, "capital_expenditure_ttm", "capital_expenditure", "capex")
    )
    explicit_free_cash_flow = _as_float(
        _first_present(record, "free_cash_flow_ttm", "free_cash_flow", "fcf")
    )
    free_cash_flow = _free_cash_flow(
        explicit_free_cash_flow, operating_cash_flow, capital_expenditure
    )
    revenue = _as_float(
        _first_present(record, "revenue_ttm", "total_revenue", "revenue")
    )
    prior_revenue = _as_float(
        _first_present(
            record,
            "prior_year_revenue",
            "revenue_prior_year",
            "revenue_ttm_prior_year",
        )
    )
    revenue_growth_yoy_pct = _as_float(
        _first_present(record, "revenue_growth_yoy_pct", "revenue_growth_pct")
    )
    current_ratio = _as_float(_first_present(record, "current_ratio"))
    current_assets = _as_float(_first_present(record, "current_assets"))
    current_liabilities = _as_float(_first_present(record, "current_liabilities"))
    total_debt = _as_float(_first_present(record, "total_debt", "debt"))
    total_equity = _as_float(
        _first_present(record, "total_equity", "shareholders_equity", "stockholders_equity")
    )
    debt_to_equity = _as_float(_first_present(record, "debt_to_equity"))
    cash = _as_float(
        _first_present(record, "cash_and_equivalents", "cash", "cash_and_short_term_investments")
    )
    market_cap = _as_float(record.get("market_cap"))
    price_to_sales = _as_float(_first_present(record, "price_to_sales", "ps_ratio"))

    if revenue_growth_yoy_pct is None and revenue is not None and prior_revenue:
        revenue_growth_yoy_pct = ((revenue - prior_revenue) / prior_revenue) * 100.0

    if current_ratio is None and current_assets is not None and current_liabilities:
        current_ratio = current_assets / current_liabilities

    if debt_to_equity is None and total_debt is not None and total_equity is not None:
        debt_to_equity = math.inf if total_equity <= 0 and total_debt > 0 else (
            total_debt / total_equity if total_equity > 0 else None
        )

    if price_to_sales is None and market_cap is not None and revenue is not None:
        price_to_sales = market_cap / revenue if revenue > 0 else None

    cash_runway_years = None
    if free_cash_flow is not None and free_cash_flow < 0 and cash is not None:
        cash_runway_years = cash / abs(free_cash_flow)

    if not symbol:
        warnings.append("missing_symbol")

    if net_income is None:
        warnings.append("missing_net_income")
    else:
        assessed_signal_count += 1
        if net_income < 0:
            score += active_rules.negative_net_income_points
            reasons.append("negative_net_income")

    if operating_cash_flow is None:
        warnings.append("missing_operating_cash_flow")
    else:
        assessed_signal_count += 1
        if operating_cash_flow < 0:
            score += active_rules.negative_operating_cash_flow_points
            reasons.append("negative_operating_cash_flow")

    if free_cash_flow is None:
        warnings.append("missing_free_cash_flow")
    else:
        assessed_signal_count += 1
        if free_cash_flow < 0:
            score += active_rules.negative_free_cash_flow_points
            reasons.append("negative_free_cash_flow")

    if revenue is None:
        warnings.append("missing_revenue")
    else:
        assessed_signal_count += 1
        if revenue < active_rules.min_meaningful_revenue:
            score += active_rules.no_meaningful_revenue_points
            reasons.append("no_meaningful_revenue")

    if revenue_growth_yoy_pct is None:
        warnings.append("missing_revenue_growth")
    else:
        assessed_signal_count += 1
        if revenue_growth_yoy_pct < 0:
            score += active_rules.declining_revenue_yoy_points
            reasons.append("declining_revenue_yoy")

    if current_ratio is None:
        warnings.append("missing_current_ratio")
    else:
        assessed_signal_count += 1
        if current_ratio < active_rules.weak_current_ratio:
            score += active_rules.weak_current_ratio_points
            reasons.append("weak_current_ratio")

    if debt_to_equity is None:
        warnings.append("missing_debt_to_equity")
    else:
        assessed_signal_count += 1
        if debt_to_equity > active_rules.high_debt_to_equity:
            score += active_rules.high_debt_to_equity_points
            reasons.append("high_debt_to_equity")

    if free_cash_flow is not None and free_cash_flow < 0:
        if cash_runway_years is None:
            warnings.append("missing_cash_for_runway")
        else:
            assessed_signal_count += 1
            if cash_runway_years < active_rules.low_cash_runway_years:
                score += active_rules.low_cash_runway_points
                reasons.append("low_cash_runway")

    if price_to_sales is None:
        warnings.append("missing_price_to_sales")
    else:
        assessed_signal_count += 1
        if price_to_sales > active_rules.high_price_to_sales:
            score += active_rules.high_price_to_sales_points
            reasons.append("high_price_to_sales")

    if assessed_signal_count == 0:
        weakness_level = "unknown"
        warnings.append("fundamental_data_missing")
    elif score >= active_rules.high_score:
        weakness_level = "high"
    elif score >= active_rules.moderate_score:
        weakness_level = "moderate"
    else:
        weakness_level = "low"

    metrics = FundamentalMetrics(
        symbol=symbol,
        net_income=net_income,
        operating_cash_flow=operating_cash_flow,
        free_cash_flow=free_cash_flow,
        revenue=revenue,
        revenue_growth_yoy_pct=revenue_growth_yoy_pct,
        current_ratio=current_ratio,
        debt_to_equity=debt_to_equity,
        cash_runway_years=cash_runway_years,
        price_to_sales=price_to_sales,
        assessed_signal_count=assessed_signal_count,
    )

    return FundamentalAssessment(
        symbol=symbol,
        weakness_score=score,
        weakness_level=weakness_level,
        metrics=metrics,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def evaluate_fundamentals_batch(
    records: Iterable[Mapping[str, Any]], rules: FundamentalRules | None = None
) -> list[FundamentalAssessment]:
    """Score fundamental weakness for a batch of normalized records."""

    active_rules = rules or FundamentalRules()
    return [evaluate_fundamentals(record, active_rules) for record in records]
