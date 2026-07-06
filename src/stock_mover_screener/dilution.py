"""Dilution-risk scoring for pre-market short-candidate research."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "dilution.json"


def _as_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "t", "yes", "y", "1"}:
            return True
        if normalized in {"false", "f", "no", "n", "0"}:
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


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    normalized = text.lower()
    return any(pattern in normalized for pattern in patterns)


def _filing_texts(record: Mapping[str, Any]) -> list[str]:
    raw = _first_present(record, "recent_filings", "sec_filings", "filings") or []
    if isinstance(raw, (str, Mapping)):
        raw = [raw]

    texts: list[str] = []
    for item in raw:
        if isinstance(item, Mapping):
            pieces = [
                str(item.get(key, ""))
                for key in (
                    "form",
                    "form_type",
                    "type",
                    "title",
                    "description",
                    "summary",
                    "headline",
                )
            ]
            texts.append(" ".join(piece for piece in pieces if piece).strip())
        else:
            texts.append(str(item))
    return [text for text in texts if text]


@dataclass(frozen=True)
class DilutionRules:
    moderate_score: int = 4
    high_score: int = 8
    large_share_growth_pct: float = 20.0
    repeated_offering_count: int = 2
    active_shelf_registration_points: int = 3
    recent_offering_points: int = 3
    s1_s3_registration_points: int = 2
    prospectus_supplement_points: int = 2
    atm_offering_points: int = 2
    registered_direct_offering_points: int = 2
    private_placement_points: int = 2
    warrants_outstanding_points: int = 2
    convertible_debt_points: int = 2
    equity_line_points: int = 2
    large_share_growth_points: int = 2
    repeated_offering_history_points: int = 2


@dataclass(frozen=True)
class DilutionMetrics:
    symbol: str
    active_shelf_registration: bool | None
    recent_offering: bool | None
    atm_offering: bool | None
    registered_direct_offering: bool | None
    private_placement: bool | None
    warrants_outstanding: bool | None
    convertible_debt: bool | None
    equity_line: bool | None
    shares_outstanding_growth_pct: float | None
    offering_count: int | None
    filing_match_count: int
    assessed_signal_count: int


@dataclass(frozen=True)
class DilutionAssessment:
    symbol: str
    dilution_risk_score: int
    risk_level: str
    metrics: DilutionMetrics
    reasons: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


def load_dilution_rules(path: str | Path = DEFAULT_CONFIG_PATH) -> DilutionRules:
    """Load dilution-risk scoring rules from JSON config."""

    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    thresholds = raw.get("thresholds", {})
    points = raw.get("points", {})
    return DilutionRules(
        moderate_score=int(thresholds.get("moderate_score", 4)),
        high_score=int(thresholds.get("high_score", 8)),
        large_share_growth_pct=float(thresholds.get("large_share_growth_pct", 20.0)),
        repeated_offering_count=int(thresholds.get("repeated_offering_count", 2)),
        active_shelf_registration_points=int(
            points.get("active_shelf_registration", 3)
        ),
        recent_offering_points=int(points.get("recent_offering", 3)),
        s1_s3_registration_points=int(points.get("s1_s3_registration", 2)),
        prospectus_supplement_points=int(points.get("prospectus_supplement", 2)),
        atm_offering_points=int(points.get("atm_offering", 2)),
        registered_direct_offering_points=int(
            points.get("registered_direct_offering", 2)
        ),
        private_placement_points=int(points.get("private_placement", 2)),
        warrants_outstanding_points=int(points.get("warrants_outstanding", 2)),
        convertible_debt_points=int(points.get("convertible_debt", 2)),
        equity_line_points=int(points.get("equity_line", 2)),
        large_share_growth_points=int(points.get("large_share_growth", 2)),
        repeated_offering_history_points=int(
            points.get("repeated_offering_history", 2)
        ),
    )


def evaluate_dilution(
    record: Mapping[str, Any], rules: DilutionRules | None = None
) -> DilutionAssessment:
    """Score dilution risk without filtering the record out."""

    active_rules = rules or DilutionRules()
    symbol = str(record.get("symbol") or record.get("ticker") or "").strip().upper()
    reasons: list[str] = []
    warnings: list[str] = []
    score = 0
    assessed_signal_count = 0

    active_shelf_registration = _as_bool(
        _first_present(
            record,
            "active_shelf_registration",
            "shelf_registration_active",
            "active_shelf",
        )
    )
    recent_offering = _as_bool(
        _first_present(record, "recent_offering", "offering_recent", "recent_capital_raise")
    )
    atm_offering = _as_bool(
        _first_present(record, "atm_offering", "at_the_market_offering", "active_atm_program")
    )
    registered_direct_offering = _as_bool(
        _first_present(
            record,
            "registered_direct_offering",
            "recent_registered_direct",
        )
    )
    private_placement = _as_bool(
        _first_present(record, "private_placement", "recent_private_placement")
    )
    warrants_outstanding = _as_bool(
        _first_present(record, "warrants_outstanding", "has_warrants")
    )
    convertible_debt = _as_bool(
        _first_present(record, "convertible_debt", "convertible_notes")
    )
    convertible_debt_amount = _as_float(
        _first_present(record, "convertible_debt_amount", "convertible_notes_amount")
    )
    equity_line = _as_bool(
        _first_present(record, "equity_line", "equity_line_facility")
    )
    shares_outstanding_growth_pct = _as_float(
        _first_present(
            record,
            "shares_outstanding_growth_pct",
            "share_count_growth_pct",
            "shares_outstanding_yoy_growth_pct",
        )
    )
    offering_count_raw = _as_float(
        _first_present(
            record,
            "offering_count_12m",
            "offerings_last_12m",
            "recent_offering_count",
        )
    )
    offering_count = int(offering_count_raw) if offering_count_raw is not None else None

    filing_texts = _filing_texts(record)
    filing_match_count = 0

    s1_s3_from_filings = any(
        _contains_any(text, ("s-1", "s1", "s-3", "s3", "shelf registration"))
        for text in filing_texts
    )
    prospectus_from_filings = any(
        _contains_any(
            text,
            (
                "424b",
                "424 b",
                "prospectus supplement",
                "prospectus",
            ),
        )
        for text in filing_texts
    )
    atm_from_filings = any(
        _contains_any(text, ("at-the-market", "at the market", "atm offering"))
        for text in filing_texts
    )
    registered_direct_from_filings = any(
        _contains_any(text, ("registered direct", "registered-direct"))
        for text in filing_texts
    )
    private_placement_from_filings = any(
        _contains_any(text, ("private placement", "private-placement"))
        for text in filing_texts
    )
    warrants_from_filings = any(
        _contains_any(text, ("warrant", "warrants")) for text in filing_texts
    )
    convertible_from_filings = any(
        _contains_any(text, ("convertible note", "convertible debt", "convertible"))
        for text in filing_texts
    )
    equity_line_from_filings = any(
        _contains_any(text, ("equity line", "equity purchase agreement"))
        for text in filing_texts
    )

    filing_flags = (
        s1_s3_from_filings,
        prospectus_from_filings,
        atm_from_filings,
        registered_direct_from_filings,
        private_placement_from_filings,
        warrants_from_filings,
        convertible_from_filings,
        equity_line_from_filings,
    )
    filing_match_count = sum(1 for flag in filing_flags if flag)

    if active_shelf_registration is None and s1_s3_from_filings:
        active_shelf_registration = True
    if recent_offering is None and (
        prospectus_from_filings
        or atm_from_filings
        or registered_direct_from_filings
        or private_placement_from_filings
    ):
        recent_offering = True
    if atm_offering is None and atm_from_filings:
        atm_offering = True
    if registered_direct_offering is None and registered_direct_from_filings:
        registered_direct_offering = True
    if private_placement is None and private_placement_from_filings:
        private_placement = True
    if warrants_outstanding is None and warrants_from_filings:
        warrants_outstanding = True
    if convertible_debt is None and (
        convertible_from_filings
        or (convertible_debt_amount is not None and convertible_debt_amount > 0)
    ):
        convertible_debt = True
    if equity_line is None and equity_line_from_filings:
        equity_line = True

    if not symbol:
        warnings.append("missing_symbol")

    def score_bool(value: bool | None, reason: str, points: int) -> None:
        nonlocal score, assessed_signal_count
        if value is None:
            warnings.append(f"missing_{reason}")
            return
        assessed_signal_count += 1
        if value:
            score += points
            reasons.append(reason)

    score_bool(
        active_shelf_registration,
        "active_shelf_registration",
        active_rules.active_shelf_registration_points,
    )
    score_bool(recent_offering, "recent_offering", active_rules.recent_offering_points)
    score_bool(atm_offering, "atm_offering", active_rules.atm_offering_points)
    score_bool(
        registered_direct_offering,
        "registered_direct_offering",
        active_rules.registered_direct_offering_points,
    )
    score_bool(
        private_placement,
        "private_placement",
        active_rules.private_placement_points,
    )
    score_bool(
        warrants_outstanding,
        "warrants_outstanding",
        active_rules.warrants_outstanding_points,
    )
    score_bool(
        convertible_debt,
        "convertible_debt",
        active_rules.convertible_debt_points,
    )
    score_bool(equity_line, "equity_line", active_rules.equity_line_points)

    if s1_s3_from_filings:
        score += active_rules.s1_s3_registration_points
        reasons.append("s1_s3_registration")
        assessed_signal_count += 1
    elif not filing_texts:
        warnings.append("missing_recent_filings")

    if prospectus_from_filings:
        score += active_rules.prospectus_supplement_points
        reasons.append("prospectus_supplement")
        assessed_signal_count += 1

    if shares_outstanding_growth_pct is None:
        warnings.append("missing_shares_outstanding_growth")
    else:
        assessed_signal_count += 1
        if shares_outstanding_growth_pct >= active_rules.large_share_growth_pct:
            score += active_rules.large_share_growth_points
            reasons.append("large_share_growth")

    if offering_count is None:
        warnings.append("missing_offering_count")
    else:
        assessed_signal_count += 1
        if offering_count >= active_rules.repeated_offering_count:
            score += active_rules.repeated_offering_history_points
            reasons.append("repeated_offering_history")

    if assessed_signal_count == 0:
        risk_level = "unknown"
        warnings.append("dilution_data_missing")
    elif score >= active_rules.high_score:
        risk_level = "high"
    elif score >= active_rules.moderate_score:
        risk_level = "moderate"
    else:
        risk_level = "low"

    metrics = DilutionMetrics(
        symbol=symbol,
        active_shelf_registration=active_shelf_registration,
        recent_offering=recent_offering,
        atm_offering=atm_offering,
        registered_direct_offering=registered_direct_offering,
        private_placement=private_placement,
        warrants_outstanding=warrants_outstanding,
        convertible_debt=convertible_debt,
        equity_line=equity_line,
        shares_outstanding_growth_pct=shares_outstanding_growth_pct,
        offering_count=offering_count,
        filing_match_count=filing_match_count,
        assessed_signal_count=assessed_signal_count,
    )

    return DilutionAssessment(
        symbol=symbol,
        dilution_risk_score=score,
        risk_level=risk_level,
        metrics=metrics,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def evaluate_dilution_batch(
    records: Iterable[Mapping[str, Any]], rules: DilutionRules | None = None
) -> list[DilutionAssessment]:
    """Score dilution risk for a batch of normalized records."""

    active_rules = rules or DilutionRules()
    return [evaluate_dilution(record, active_rules) for record in records]
