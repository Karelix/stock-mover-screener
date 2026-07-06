from stock_mover_screener.labels import (
    candidate_to_full_dict,
    candidate_to_summary_row,
    load_label_rules,
)
from stock_mover_screener.pipeline import scan_labeled_premarket_candidates


BASE_RECORD = {
    "symbol": "BASE",
    "country": "US",
    "security_type": "common_stock",
    "price": 12.0,
    "market_cap": 250_000_000,
    "average_dollar_volume": 12_000_000,
    "premarket_price": 12.0,
    "previous_close": 10.0,
    "premarket_open": 11.2,
    "premarket_volume": 200_000,
    "average_premarket_volume": 50_000,
    "atr_14_pct": 5.0,
    "premarket_bid": 11.95,
    "premarket_ask": 12.05,
    "float_shares": 30_000_000,
    "revenue_ttm": 500_000,
    "prior_year_revenue": 1_000_000,
    "net_income": -5_000_000,
    "operating_cash_flow": -4_000_000,
    "free_cash_flow": -6_000_000,
    "cash_and_equivalents": 2_000_000,
    "current_ratio": 0.7,
    "total_debt": 30_000_000,
    "total_equity": 10_000_000,
    "active_shelf_registration": True,
    "recent_offering": True,
    "atm_offering": True,
    "warrants_outstanding": True,
    "convertible_debt": True,
    "shares_outstanding_growth_pct": 75.0,
    "offering_count_12m": 3,
    "headlines": [
        "Company announces AI partnership with unnamed partner",
        "No financial terms disclosed; Reddit traders cite short squeeze",
    ],
    "social_mentions": 900,
    "average_social_mentions": 100,
    "headline_count_today": 4,
    "average_headline_count": 1,
    "short_interest_pct_float": 5.0,
    "days_to_cover": 1.0,
    "borrow_fee_pct": 2.0,
    "hard_to_borrow": False,
    "borrow_available_shares": 5_000_000,
    "halts_count": 0,
    "call_volume_ratio": 1.0,
}


def test_prime_watch_label_preserves_full_assessments():
    candidates = scan_labeled_premarket_candidates([BASE_RECORD])

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.label.final_label == "Prime Watch"
    assert candidate.fundamentals.weakness_level == "high"
    assert candidate.dilution.risk_level == "high"
    assert candidate.catalyst.category == "weak"
    assert candidate.hype.hype_level == "high"
    assert candidate.squeeze.risk_level == "low"


def test_too_dangerous_label_for_extreme_squeeze_risk():
    record = {
        **BASE_RECORD,
        "symbol": "SQZ",
        "float_shares": 5_000_000,
        "short_interest_pct_float": 45.0,
        "days_to_cover": 7.0,
        "borrow_fee_pct": 120.0,
        "hard_to_borrow": True,
        "borrow_available_shares": 0,
        "halts_count": 3,
        "call_volume_ratio": 5.0,
    }

    candidates = scan_labeled_premarket_candidates([record])

    assert candidates[0].label.final_label == "Too Dangerous"
    assert candidates[0].squeeze.risk_level == "extreme"


def test_likely_real_catalyst_label_for_strong_clean_setup():
    record = {
        **BASE_RECORD,
        "symbol": "REAL",
        "revenue_ttm": 100_000_000,
        "prior_year_revenue": 80_000_000,
        "net_income": 10_000_000,
        "operating_cash_flow": 12_000_000,
        "free_cash_flow": 8_000_000,
        "current_ratio": 2.0,
        "debt_to_equity": 0.3,
        "price_to_sales": 5.0,
        "active_shelf_registration": False,
        "recent_offering": False,
        "atm_offering": False,
        "warrants_outstanding": False,
        "convertible_debt": False,
        "shares_outstanding_growth_pct": 2.0,
        "offering_count_12m": 0,
        "headlines": ["Company reports earnings beat and raises guidance"],
        "social_mentions": 80,
        "average_social_mentions": 100,
        "headline_count_today": 1,
        "average_headline_count": 1,
    }

    candidates = scan_labeled_premarket_candidates([record])

    assert candidates[0].label.final_label == "Likely Real Catalyst"
    assert candidates[0].catalyst.category == "strong"


def test_needs_more_data_label_when_many_layers_are_unknown():
    record = {
        "symbol": "MISS",
        "country": "US",
        "security_type": "common_stock",
        "price": 12.0,
        "market_cap": 250_000_000,
        "average_dollar_volume": 12_000_000,
        "premarket_price": 12.0,
        "previous_close": 10.0,
        "premarket_open": 11.2,
        "premarket_volume": 200_000,
        "average_premarket_volume": 50_000,
        "atr_14_pct": 5.0,
        "premarket_bid": 11.95,
        "premarket_ask": 12.05,
        "float_shares": 30_000_000,
    }

    candidates = scan_labeled_premarket_candidates([record])

    assert candidates[0].label.final_label == "Needs More Data"
    assert "fundamentals_unknown" in candidates[0].label.warnings
    assert "dilution_unknown" in candidates[0].label.warnings
    assert "catalyst_unknown" in candidates[0].label.warnings


def test_full_and_summary_exports_keep_label_and_all_nested_info():
    candidate = scan_labeled_premarket_candidates([BASE_RECORD])[0]

    full = candidate_to_full_dict(candidate)
    summary = candidate_to_summary_row(candidate)

    assert full["label"]["final_label"] == "Prime Watch"
    assert full["premarket"]["metrics"]["premarket_move_pct"] == 20.0
    assert full["fundamentals"]["metrics"]["net_income"] == -5_000_000
    assert summary["final_label"] == "Prime Watch"
    assert summary["fundamental_level"] == "high"
    assert summary["squeeze_level"] == "low"


def test_label_rules_load_from_config():
    rules = load_label_rules()

    assert rules.prime_watch_thesis_score == 8
    assert rules.needs_more_data_unknown_layers == 3
