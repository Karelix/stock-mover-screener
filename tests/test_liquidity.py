import pytest

from stock_mover_screener.liquidity import (
    LiquidityRules,
    evaluate_liquidity,
    filter_liquid_records,
    load_liquidity_rules,
)


BASE_RECORD = {
    "symbol": "MOMO",
    "premarket_price": 12.0,
    "premarket_volume": 200_000,
    "average_dollar_volume": 12_000_000,
    "premarket_bid": 11.95,
    "premarket_ask": 12.05,
    "float_shares": 45_000_000,
}


def test_liquid_candidate_passes():
    decision = evaluate_liquidity(BASE_RECORD)

    assert decision.passed
    assert decision.reasons == ()
    assert decision.risk_flags == ()
    assert decision.metrics is not None
    assert decision.metrics.premarket_dollar_volume == pytest.approx(2_400_000)
    assert decision.metrics.spread_pct == pytest.approx(0.8333333333)


def test_explicit_premarket_dollar_volume_can_be_used():
    record = {
        **BASE_RECORD,
        "premarket_volume": 1,
        "premarket_dollar_volume": 1_500_000,
    }

    decision = evaluate_liquidity(record, LiquidityRules(min_premarket_volume=1))

    assert decision.passed
    assert decision.metrics is not None
    assert decision.metrics.premarket_dollar_volume == pytest.approx(1_500_000)


def test_wide_spread_is_rejected_when_spread_data_exists():
    record = {**BASE_RECORD, "premarket_bid": 10.0, "premarket_ask": 12.0}

    decision = evaluate_liquidity(record)

    assert not decision.passed
    assert "spread_above_maximum" in decision.reasons


def test_missing_spread_is_allowed_with_warning_by_default():
    record = {**BASE_RECORD}
    record.pop("premarket_bid")
    record.pop("premarket_ask")

    decision = evaluate_liquidity(record)

    assert decision.passed
    assert "spread_data_missing" in decision.warnings


def test_missing_spread_can_be_required():
    record = {**BASE_RECORD}
    record.pop("premarket_bid")
    record.pop("premarket_ask")

    decision = evaluate_liquidity(record, LiquidityRules(allow_missing_spread=False))

    assert not decision.passed
    assert "missing_spread_data" in decision.reasons


def test_low_float_is_flagged_not_excluded():
    record = {**BASE_RECORD, "float_shares": 12_000_000}

    decision = evaluate_liquidity(record)

    assert decision.passed
    assert decision.risk_flags == ("low_float",)


def test_very_low_float_is_flagged_not_excluded():
    record = {**BASE_RECORD, "float_shares": 5_000_000}

    decision = evaluate_liquidity(record)

    assert decision.passed
    assert decision.risk_flags == ("very_low_float",)


def test_thin_premarket_volume_is_rejected():
    record = {**BASE_RECORD, "premarket_volume": 10_000}

    decision = evaluate_liquidity(record)

    assert not decision.passed
    assert "premarket_volume_below_minimum" in decision.reasons
    assert "premarket_dollar_volume_below_minimum" in decision.reasons


def test_filter_liquid_records_keeps_only_passing_records():
    wide_spread = {**BASE_RECORD, "symbol": "WIDE", "premarket_bid": 8.0}

    records = filter_liquid_records([BASE_RECORD, wide_spread])

    assert [record["symbol"] for record in records] == ["MOMO"]


def test_rules_load_from_config():
    rules = load_liquidity_rules()

    assert isinstance(rules, LiquidityRules)
    assert rules.max_spread_pct == pytest.approx(3.0)
    assert rules.allow_missing_spread is True
