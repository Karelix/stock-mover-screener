"""Small orchestration helpers for scanner phases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from stock_mover_screener.catalyst import (
    CatalystAssessment,
    CatalystRules,
    evaluate_catalyst,
)
from stock_mover_screener.dilution import (
    DilutionAssessment,
    DilutionRules,
    evaluate_dilution,
)
from stock_mover_screener.fundamentals import (
    FundamentalAssessment,
    FundamentalRules,
    evaluate_fundamentals,
)
from stock_mover_screener.hype import HypeAssessment, HypeRules, evaluate_hype
from stock_mover_screener.labels import (
    LABEL_PRIORITY,
    LabelRules,
    PreMarketLabel,
    evaluate_pre_market_label,
)
from stock_mover_screener.liquidity import (
    LiquidityDecision,
    LiquidityRules,
    evaluate_liquidity,
)
from stock_mover_screener.premarket import (
    PremarketMoverDecision,
    PremarketScanRules,
    evaluate_premarket_mover,
    scan_premarket_movers,
)
from stock_mover_screener.squeeze import (
    SqueezeAssessment,
    SqueezeRules,
    evaluate_squeeze,
)
from stock_mover_screener.universe import UniverseRules, filter_universe


@dataclass(frozen=True)
class PremarketCandidate:
    symbol: str
    premarket: PremarketMoverDecision
    liquidity: LiquidityDecision


@dataclass(frozen=True)
class FundamentalPremarketCandidate:
    symbol: str
    premarket: PremarketMoverDecision
    fundamentals: FundamentalAssessment
    liquidity: LiquidityDecision | None = None


@dataclass(frozen=True)
class DilutionPremarketCandidate:
    symbol: str
    premarket: PremarketMoverDecision
    fundamentals: FundamentalAssessment
    dilution: DilutionAssessment
    liquidity: LiquidityDecision | None = None


@dataclass(frozen=True)
class CatalystPremarketCandidate:
    symbol: str
    premarket: PremarketMoverDecision
    fundamentals: FundamentalAssessment
    dilution: DilutionAssessment
    catalyst: CatalystAssessment
    liquidity: LiquidityDecision | None = None


@dataclass(frozen=True)
class HypePremarketCandidate:
    symbol: str
    premarket: PremarketMoverDecision
    fundamentals: FundamentalAssessment
    dilution: DilutionAssessment
    catalyst: CatalystAssessment
    hype: HypeAssessment
    liquidity: LiquidityDecision | None = None


@dataclass(frozen=True)
class SqueezePremarketCandidate:
    symbol: str
    premarket: PremarketMoverDecision
    fundamentals: FundamentalAssessment
    dilution: DilutionAssessment
    catalyst: CatalystAssessment
    hype: HypeAssessment
    squeeze: SqueezeAssessment
    liquidity: LiquidityDecision | None = None


@dataclass(frozen=True)
class LabeledPremarketCandidate:
    symbol: str
    premarket: PremarketMoverDecision
    fundamentals: FundamentalAssessment
    dilution: DilutionAssessment
    catalyst: CatalystAssessment
    hype: HypeAssessment
    squeeze: SqueezeAssessment
    label: PreMarketLabel
    liquidity: LiquidityDecision | None = None


def scan_universe_premarket_movers(
    records: Iterable[Mapping[str, Any]],
    universe_rules: UniverseRules | None = None,
    premarket_rules: PremarketScanRules | None = None,
) -> list[PremarketMoverDecision]:
    """Apply the base universe filter, then rank passing pre-market movers."""

    universe_records = filter_universe(records, universe_rules)
    return scan_premarket_movers(universe_records, premarket_rules)


def scan_tradeable_premarket_candidates(
    records: Iterable[Mapping[str, Any]],
    universe_rules: UniverseRules | None = None,
    premarket_rules: PremarketScanRules | None = None,
    liquidity_rules: LiquidityRules | None = None,
) -> list[PremarketCandidate]:
    """Apply universe, pre-market mover, and liquidity filters in order."""

    universe_records = filter_universe(records, universe_rules)
    candidates: list[PremarketCandidate] = []
    for record in universe_records:
        premarket_decision = evaluate_premarket_mover(record, premarket_rules)
        if not premarket_decision.passed:
            continue

        liquidity_decision = evaluate_liquidity(record, liquidity_rules)
        if not liquidity_decision.passed:
            continue

        candidates.append(
            PremarketCandidate(
                symbol=premarket_decision.symbol,
                premarket=premarket_decision,
                liquidity=liquidity_decision,
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.premarket.metrics.mover_score
            if candidate.premarket.metrics
            else 0.0
        ),
        reverse=True,
    )


def scan_fundamental_premarket_candidates(
    records: Iterable[Mapping[str, Any]],
    universe_rules: UniverseRules | None = None,
    premarket_rules: PremarketScanRules | None = None,
    fundamental_rules: FundamentalRules | None = None,
    liquidity_rules: LiquidityRules | None = None,
    use_liquidity: bool = True,
) -> list[FundamentalPremarketCandidate]:
    """Apply universe and mover filters, optionally liquidity, then score fundamentals."""

    universe_records = filter_universe(records, universe_rules)
    candidates: list[FundamentalPremarketCandidate] = []
    for record in universe_records:
        premarket_decision = evaluate_premarket_mover(record, premarket_rules)
        if not premarket_decision.passed:
            continue

        liquidity_decision = None
        if use_liquidity:
            liquidity_decision = evaluate_liquidity(record, liquidity_rules)
            if not liquidity_decision.passed:
                continue

        fundamental_assessment = evaluate_fundamentals(record, fundamental_rules)
        candidates.append(
            FundamentalPremarketCandidate(
                symbol=premarket_decision.symbol,
                premarket=premarket_decision,
                fundamentals=fundamental_assessment,
                liquidity=liquidity_decision,
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.fundamentals.weakness_score,
            candidate.premarket.metrics.mover_score
            if candidate.premarket.metrics
            else 0.0,
        ),
        reverse=True,
    )


def scan_dilution_premarket_candidates(
    records: Iterable[Mapping[str, Any]],
    universe_rules: UniverseRules | None = None,
    premarket_rules: PremarketScanRules | None = None,
    fundamental_rules: FundamentalRules | None = None,
    dilution_rules: DilutionRules | None = None,
    liquidity_rules: LiquidityRules | None = None,
    use_liquidity: bool = True,
) -> list[DilutionPremarketCandidate]:
    """Apply universe and mover filters, optionally liquidity, then score fundamentals and dilution."""

    universe_records = filter_universe(records, universe_rules)
    candidates: list[DilutionPremarketCandidate] = []
    for record in universe_records:
        premarket_decision = evaluate_premarket_mover(record, premarket_rules)
        if not premarket_decision.passed:
            continue

        liquidity_decision = None
        if use_liquidity:
            liquidity_decision = evaluate_liquidity(record, liquidity_rules)
            if not liquidity_decision.passed:
                continue

        fundamental_assessment = evaluate_fundamentals(record, fundamental_rules)
        dilution_assessment = evaluate_dilution(record, dilution_rules)
        candidates.append(
            DilutionPremarketCandidate(
                symbol=premarket_decision.symbol,
                premarket=premarket_decision,
                fundamentals=fundamental_assessment,
                dilution=dilution_assessment,
                liquidity=liquidity_decision,
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.dilution.dilution_risk_score,
            candidate.fundamentals.weakness_score,
            candidate.premarket.metrics.mover_score
            if candidate.premarket.metrics
            else 0.0,
        ),
        reverse=True,
    )


def scan_catalyst_premarket_candidates(
    records: Iterable[Mapping[str, Any]],
    universe_rules: UniverseRules | None = None,
    premarket_rules: PremarketScanRules | None = None,
    fundamental_rules: FundamentalRules | None = None,
    dilution_rules: DilutionRules | None = None,
    catalyst_rules: CatalystRules | None = None,
    liquidity_rules: LiquidityRules | None = None,
    use_liquidity: bool = True,
) -> list[CatalystPremarketCandidate]:
    """Apply universe and mover filters, optionally liquidity, then score fundamentals, dilution, and catalyst quality."""

    universe_records = filter_universe(records, universe_rules)
    candidates: list[CatalystPremarketCandidate] = []
    for record in universe_records:
        premarket_decision = evaluate_premarket_mover(record, premarket_rules)
        if not premarket_decision.passed:
            continue

        liquidity_decision = None
        if use_liquidity:
            liquidity_decision = evaluate_liquidity(record, liquidity_rules)
            if not liquidity_decision.passed:
                continue

        fundamental_assessment = evaluate_fundamentals(record, fundamental_rules)
        dilution_assessment = evaluate_dilution(record, dilution_rules)
        catalyst_assessment = evaluate_catalyst(record, catalyst_rules)
        candidates.append(
            CatalystPremarketCandidate(
                symbol=premarket_decision.symbol,
                premarket=premarket_decision,
                fundamentals=fundamental_assessment,
                dilution=dilution_assessment,
                catalyst=catalyst_assessment,
                liquidity=liquidity_decision,
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.catalyst.weak_catalyst_score,
            candidate.dilution.dilution_risk_score,
            candidate.fundamentals.weakness_score,
            candidate.premarket.metrics.mover_score
            if candidate.premarket.metrics
            else 0.0,
        ),
        reverse=True,
    )


def scan_hype_premarket_candidates(
    records: Iterable[Mapping[str, Any]],
    universe_rules: UniverseRules | None = None,
    premarket_rules: PremarketScanRules | None = None,
    fundamental_rules: FundamentalRules | None = None,
    dilution_rules: DilutionRules | None = None,
    catalyst_rules: CatalystRules | None = None,
    hype_rules: HypeRules | None = None,
    liquidity_rules: LiquidityRules | None = None,
    use_liquidity: bool = True,
) -> list[HypePremarketCandidate]:
    """Apply universe and mover filters, optionally liquidity, then score fundamentals, dilution, catalyst quality, and hype."""

    universe_records = filter_universe(records, universe_rules)
    candidates: list[HypePremarketCandidate] = []
    for record in universe_records:
        premarket_decision = evaluate_premarket_mover(record, premarket_rules)
        if not premarket_decision.passed:
            continue

        liquidity_decision = None
        if use_liquidity:
            liquidity_decision = evaluate_liquidity(record, liquidity_rules)
            if not liquidity_decision.passed:
                continue

        fundamental_assessment = evaluate_fundamentals(record, fundamental_rules)
        dilution_assessment = evaluate_dilution(record, dilution_rules)
        catalyst_assessment = evaluate_catalyst(record, catalyst_rules)
        hype_assessment = evaluate_hype(record, hype_rules)
        candidates.append(
            HypePremarketCandidate(
                symbol=premarket_decision.symbol,
                premarket=premarket_decision,
                fundamentals=fundamental_assessment,
                dilution=dilution_assessment,
                catalyst=catalyst_assessment,
                hype=hype_assessment,
                liquidity=liquidity_decision,
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.hype.hype_score,
            candidate.catalyst.weak_catalyst_score,
            candidate.dilution.dilution_risk_score,
            candidate.fundamentals.weakness_score,
            candidate.premarket.metrics.mover_score
            if candidate.premarket.metrics
            else 0.0,
        ),
        reverse=True,
    )


def scan_squeeze_premarket_candidates(
    records: Iterable[Mapping[str, Any]],
    universe_rules: UniverseRules | None = None,
    premarket_rules: PremarketScanRules | None = None,
    fundamental_rules: FundamentalRules | None = None,
    dilution_rules: DilutionRules | None = None,
    catalyst_rules: CatalystRules | None = None,
    hype_rules: HypeRules | None = None,
    squeeze_rules: SqueezeRules | None = None,
    liquidity_rules: LiquidityRules | None = None,
    use_liquidity: bool = True,
) -> list[SqueezePremarketCandidate]:
    """Apply universe and mover filters, optionally liquidity, then score all thesis and danger layers."""

    universe_records = filter_universe(records, universe_rules)
    candidates: list[SqueezePremarketCandidate] = []
    for record in universe_records:
        premarket_decision = evaluate_premarket_mover(record, premarket_rules)
        if not premarket_decision.passed:
            continue

        liquidity_decision = None
        if use_liquidity:
            liquidity_decision = evaluate_liquidity(record, liquidity_rules)
            if not liquidity_decision.passed:
                continue

        fundamental_assessment = evaluate_fundamentals(record, fundamental_rules)
        dilution_assessment = evaluate_dilution(record, dilution_rules)
        catalyst_assessment = evaluate_catalyst(record, catalyst_rules)
        hype_assessment = evaluate_hype(record, hype_rules)
        squeeze_record = {
            **dict(record),
            "hype_score": hype_assessment.hype_score,
            "hype_level": hype_assessment.hype_level,
        }
        squeeze_assessment = evaluate_squeeze(squeeze_record, squeeze_rules)
        candidates.append(
            SqueezePremarketCandidate(
                symbol=premarket_decision.symbol,
                premarket=premarket_decision,
                fundamentals=fundamental_assessment,
                dilution=dilution_assessment,
                catalyst=catalyst_assessment,
                hype=hype_assessment,
                squeeze=squeeze_assessment,
                liquidity=liquidity_decision,
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.squeeze.squeeze_risk_score,
            candidate.hype.hype_score,
            candidate.catalyst.weak_catalyst_score,
            candidate.dilution.dilution_risk_score,
            candidate.fundamentals.weakness_score,
            candidate.premarket.metrics.mover_score
            if candidate.premarket.metrics
            else 0.0,
        ),
        reverse=True,
    )


def scan_labeled_premarket_candidates(
    records: Iterable[Mapping[str, Any]],
    universe_rules: UniverseRules | None = None,
    premarket_rules: PremarketScanRules | None = None,
    fundamental_rules: FundamentalRules | None = None,
    dilution_rules: DilutionRules | None = None,
    catalyst_rules: CatalystRules | None = None,
    hype_rules: HypeRules | None = None,
    squeeze_rules: SqueezeRules | None = None,
    label_rules: LabelRules | None = None,
    liquidity_rules: LiquidityRules | None = None,
    use_liquidity: bool = True,
) -> list[LabeledPremarketCandidate]:
    """Run the full pre-market pipeline and add final human-readable labels."""

    squeeze_candidates = scan_squeeze_premarket_candidates(
        records,
        universe_rules=universe_rules,
        premarket_rules=premarket_rules,
        fundamental_rules=fundamental_rules,
        dilution_rules=dilution_rules,
        catalyst_rules=catalyst_rules,
        hype_rules=hype_rules,
        squeeze_rules=squeeze_rules,
        liquidity_rules=liquidity_rules,
        use_liquidity=use_liquidity,
    )
    labeled_candidates: list[LabeledPremarketCandidate] = []
    for candidate in squeeze_candidates:
        label = evaluate_pre_market_label(
            symbol=candidate.symbol,
            premarket=candidate.premarket,
            fundamentals=candidate.fundamentals,
            dilution=candidate.dilution,
            catalyst=candidate.catalyst,
            hype=candidate.hype,
            squeeze=candidate.squeeze,
            liquidity=candidate.liquidity,
            rules=label_rules,
        )
        labeled_candidates.append(
            LabeledPremarketCandidate(
                symbol=candidate.symbol,
                premarket=candidate.premarket,
                fundamentals=candidate.fundamentals,
                dilution=candidate.dilution,
                catalyst=candidate.catalyst,
                hype=candidate.hype,
                squeeze=candidate.squeeze,
                label=label,
                liquidity=candidate.liquidity,
            )
        )

    return sorted(
        labeled_candidates,
        key=lambda candidate: (
            LABEL_PRIORITY.get(candidate.label.final_label, 99),
            -candidate.label.thesis_score,
            candidate.label.danger_score,
            -candidate.premarket.metrics.mover_score
            if candidate.premarket.metrics
            else 0.0,
        ),
    )
