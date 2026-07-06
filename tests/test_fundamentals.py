import pytest

from stock_mover_screener.fundamentals import (
    FundamentalRules,
    evaluate_fundamentals,
    evaluate_fundamentals_batch,
    load_fundamental_rules,
)


WEAK_RECORD = {
    "symbol": "WEAK",
    "market_cap": 250_000_000,
    "revenue_ttm": 500_000,
    "prior_year_revenue": 1_000_000,
    "net_income": -5_000_000,
    "operating_cash_flow": -4_000_000,
    "free_cash_flow": -6_000_000,
    "cash_and_equivalents": 2_000_000,
    "current_ratio": 0.7,
    "total_debt": 30_000_000,
    "total_equity": 10_000_000,
}


def test_weak_fundamentals_score_high():
    assessment = evaluate_fundamentals(WEAK_RECORD)

    assert assessment.weakness_level == "high"
    assert assessment.weakness_score >= 8
    assert "negative_net_income" in assessment.reasons
    assert "negative_operating_cash_flow" in assessment.reasons
    assert "negative_free_cash_flow" in assessment.reasons
    assert "declining_revenue_yoy" in assessment.reasons
    assert "weak_current_ratio" in assessment.reasons
    assert "high_debt_to_equity" in assessment.reasons
    assert "low_cash_runway" in assessment.reasons
    assert "no_meaningful_revenue" in assessment.reasons
    assert "high_price_to_sales" in assessment.reasons
    assert assessment.metrics.cash_runway_years == pytest.approx(0.3333333333)
    assert assessment.metrics.price_to_sales == pytest.approx(500.0)


def test_healthy_fundamentals_score_low():
    record = {
        "symbol": "GOOD",
        "market_cap": 500_000_000,
        "revenue_ttm": 100_000_000,
        "prior_year_revenue": 80_000_000,
        "net_income": 10_000_000,
        "operating_cash_flow": 12_000_000,
        "free_cash_flow": 8_000_000,
        "current_ratio": 2.0,
        "debt_to_equity": 0.3,
        "price_to_sales": 5.0,
    }

    assessment = evaluate_fundamentals(record)

    assert assessment.weakness_level == "low"
    assert assessment.weakness_score == 0
    assert assessment.reasons == ()


def test_missing_fundamental_data_is_unknown_not_failure():
    assessment = evaluate_fundamentals({"symbol": "MISS"})

    assert assessment.weakness_level == "unknown"
    assert assessment.weakness_score == 0
    assert "fundamental_data_missing" in assessment.warnings


def test_free_cash_flow_can_be_computed_from_capex():
    record = {
        "symbol": "CAPX",
        "operating_cash_flow": 1_000_000,
        "capital_expenditure": -2_500_000,
    }

    assessment = evaluate_fundamentals(record)

    assert assessment.metrics.free_cash_flow == pytest.approx(-1_500_000)
    assert "negative_free_cash_flow" in assessment.reasons


def test_ratios_can_be_computed_from_balance_sheet_fields():
    record = {
        "symbol": "RATIO",
        "current_assets": 5_000_000,
        "current_liabilities": 10_000_000,
        "total_debt": 30_000_000,
        "total_equity": 10_000_000,
    }

    assessment = evaluate_fundamentals(record)

    assert assessment.metrics.current_ratio == pytest.approx(0.5)
    assert assessment.metrics.debt_to_equity == pytest.approx(3.0)
    assert "weak_current_ratio" in assessment.reasons
    assert "high_debt_to_equity" in assessment.reasons


def test_rules_load_from_config():
    rules = load_fundamental_rules()

    assert isinstance(rules, FundamentalRules)
    assert rules.high_score == 8
    assert rules.high_price_to_sales == pytest.approx(20.0)


def test_batch_evaluation_scores_every_record():
    assessments = evaluate_fundamentals_batch([WEAK_RECORD, {"symbol": "MISS"}])

    assert [assessment.symbol for assessment in assessments] == ["WEAK", "MISS"]
