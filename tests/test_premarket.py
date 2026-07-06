import pytest

from stock_mover_screener.premarket import (
    PremarketScanRules,
    evaluate_premarket_mover,
    load_premarket_scan_rules,
    scan_premarket_movers,
)


BASE_RECORD = {
    "symbol": "MOMO",
    "premarket_price": 12.0,
    "previous_close": 10.0,
    "premarket_open": 11.2,
    "premarket_volume": 200_000,
    "average_premarket_volume": 50_000,
    "atr_14_pct": 5.0,
}


def test_abnormal_upside_premarket_mover_passes():
    decision = evaluate_premarket_mover(BASE_RECORD)

    assert decision.passed
    assert decision.reasons == ()
    assert decision.metrics is not None
    assert decision.metrics.premarket_move_pct == pytest.approx(20.0)
    assert decision.metrics.gap_pct == pytest.approx(12.0)
    assert decision.metrics.premarket_dollar_volume == pytest.approx(2_400_000)
    assert decision.metrics.relative_volume == pytest.approx(4.0)
    assert decision.metrics.atr_adjusted_move == pytest.approx(4.0)


def test_explicit_relative_and_dollar_volume_can_be_used():
    record = {
        "symbol": "FAST",
        "premarket_price": 18.0,
        "previous_close": 15.0,
        "premarket_volume": 1,
        "premarket_dollar_volume": 3_500_000,
        "premarket_relative_volume": 6.0,
        "atr_14": 1.5,
    }

    decision = evaluate_premarket_mover(record)

    assert decision.passed
    assert decision.metrics is not None
    assert decision.metrics.atr_14_pct == pytest.approx(10.0)
    assert decision.metrics.premarket_dollar_volume == pytest.approx(3_500_000)
    assert decision.metrics.relative_volume == pytest.approx(6.0)


def test_small_move_is_rejected_with_clear_reasons():
    record = {**BASE_RECORD, "premarket_price": 10.5, "premarket_open": 10.4}

    decision = evaluate_premarket_mover(record)

    assert not decision.passed
    assert "premarket_move_below_minimum" in decision.reasons
    assert "gap_below_minimum" in decision.reasons
    assert "atr_adjusted_move_below_minimum" in decision.reasons


def test_downside_move_is_not_an_upside_mover():
    record = {**BASE_RECORD, "premarket_price": 9.0, "premarket_open": 9.0}

    decision = evaluate_premarket_mover(record)

    assert not decision.passed
    assert "not_upside_move" in decision.reasons


def test_missing_average_volume_is_rejected_when_no_explicit_rvol_exists():
    record = {**BASE_RECORD}
    record.pop("average_premarket_volume")

    decision = evaluate_premarket_mover(record)

    assert not decision.passed
    assert decision.metrics is None
    assert "missing_or_invalid_average_volume" in decision.reasons


def test_scan_returns_passing_movers_sorted_by_score():
    stronger = {
        **BASE_RECORD,
        "symbol": "HIGH",
        "premarket_price": 14.0,
        "premarket_open": 13.0,
        "premarket_volume": 400_000,
    }
    weaker = {**BASE_RECORD, "symbol": "LOW"}
    rejected = {**BASE_RECORD, "symbol": "FLAT", "premarket_price": 10.2}

    decisions = scan_premarket_movers([weaker, rejected, stronger])

    assert [decision.symbol for decision in decisions] == ["HIGH", "LOW"]


def test_rules_load_from_config():
    rules = load_premarket_scan_rules()

    assert isinstance(rules, PremarketScanRules)
    assert rules.min_premarket_move_pct == pytest.approx(10.0)
    assert rules.require_positive_move is True
