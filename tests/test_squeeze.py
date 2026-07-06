import pytest

from stock_mover_screener.squeeze import (
    SqueezeRules,
    evaluate_squeeze,
    evaluate_squeeze_batch,
    load_squeeze_rules,
)


EXTREME_RECORD = {
    "symbol": "SQZ",
    "float_shares": 5_000_000,
    "short_interest_pct_float": 45.0,
    "days_to_cover": 7.0,
    "borrow_fee_pct": 120.0,
    "hard_to_borrow": True,
    "borrow_available_shares": 0,
    "premarket_move_pct": 65.0,
    "hype_score": 10,
    "halts_count": 3,
    "call_volume_ratio": 5.0,
}


def test_extreme_squeeze_risk_scores_from_shortability_inputs():
    assessment = evaluate_squeeze(EXTREME_RECORD)

    assert assessment.risk_level == "extreme"
    assert assessment.squeeze_risk_score >= 12
    assert "very_low_float" in assessment.reasons
    assert "extreme_short_interest" in assessment.reasons
    assert "high_days_to_cover" in assessment.reasons
    assert "extreme_borrow_fee" in assessment.reasons
    assert "hard_to_borrow" in assessment.reasons
    assert "no_borrow_available" in assessment.reasons
    assert "extreme_premarket_move" in assessment.reasons
    assert "high_hype" in assessment.reasons
    assert "repeated_halts" in assessment.reasons
    assert "call_volume_explosion" in assessment.reasons


def test_high_borrow_fee_and_low_availability_score_high():
    record = {
        "symbol": "HTB",
        "float_shares": 30_000_000,
        "borrow_fee_pct": 30.0,
        "hard_to_borrow": True,
        "borrow_available_shares": 50_000,
    }

    assessment = evaluate_squeeze(record)

    assert assessment.risk_level == "high"
    assert "high_borrow_fee" in assessment.reasons
    assert "hard_to_borrow" in assessment.reasons
    assert "low_borrow_availability" in assessment.reasons


def test_low_risk_when_data_is_available_and_benign():
    record = {
        "symbol": "CALM",
        "float_shares": 80_000_000,
        "short_interest_pct_float": 3.0,
        "days_to_cover": 1.0,
        "borrow_fee_pct": 1.5,
        "hard_to_borrow": False,
        "borrow_available_shares": 5_000_000,
        "premarket_move_pct": 8.0,
        "hype_score": 0,
        "halts_count": 0,
        "call_volume_ratio": 1.0,
    }

    assessment = evaluate_squeeze(record)

    assert assessment.risk_level == "low"
    assert assessment.squeeze_risk_score == 0
    assert assessment.reasons == ()


def test_missing_squeeze_data_is_unknown_not_failure():
    assessment = evaluate_squeeze({"symbol": "MISS"})

    assert assessment.risk_level == "unknown"
    assert assessment.squeeze_risk_score == 0
    assert "squeeze_data_missing" in assessment.warnings


def test_premarket_move_and_call_ratio_can_be_computed():
    record = {
        "symbol": "CALC",
        "premarket_price": 18.0,
        "previous_close": 10.0,
        "call_volume": 9000,
        "average_call_volume": 1000,
    }

    assessment = evaluate_squeeze(record)

    assert assessment.metrics.premarket_move_pct == pytest.approx(80.0)
    assert assessment.metrics.call_volume_ratio == pytest.approx(9.0)
    assert "extreme_premarket_move" in assessment.reasons
    assert "call_volume_explosion" in assessment.reasons


def test_rules_load_from_config():
    rules = load_squeeze_rules()

    assert isinstance(rules, SqueezeRules)
    assert rules.extreme_score == 12
    assert rules.high_borrow_fee_pct == pytest.approx(20.0)


def test_batch_evaluation_scores_every_record():
    assessments = evaluate_squeeze_batch([EXTREME_RECORD, {"symbol": "MISS"}])

    assert [assessment.symbol for assessment in assessments] == ["SQZ", "MISS"]
