import pytest

from stock_mover_screener.dilution import (
    DilutionRules,
    evaluate_dilution,
    evaluate_dilution_batch,
    load_dilution_rules,
)


DILUTIVE_RECORD = {
    "symbol": "DILU",
    "active_shelf_registration": True,
    "recent_offering": True,
    "atm_offering": True,
    "registered_direct_offering": True,
    "private_placement": False,
    "warrants_outstanding": True,
    "convertible_debt": True,
    "equity_line": True,
    "shares_outstanding_growth_pct": 75.0,
    "offering_count_12m": 3,
}


def test_dilution_risk_scores_high_from_explicit_flags():
    assessment = evaluate_dilution(DILUTIVE_RECORD)

    assert assessment.risk_level == "high"
    assert assessment.dilution_risk_score >= 8
    assert "active_shelf_registration" in assessment.reasons
    assert "recent_offering" in assessment.reasons
    assert "atm_offering" in assessment.reasons
    assert "registered_direct_offering" in assessment.reasons
    assert "warrants_outstanding" in assessment.reasons
    assert "convertible_debt" in assessment.reasons
    assert "equity_line" in assessment.reasons
    assert "large_share_growth" in assessment.reasons
    assert "repeated_offering_history" in assessment.reasons


def test_filing_text_can_create_dilution_signals():
    record = {
        "symbol": "FILE",
        "recent_filings": [
            {"form": "S-3", "description": "Shelf registration statement"},
            "424B5 prospectus supplement for at-the-market offering",
            "Registered direct offering with warrants",
            "Convertible notes and equity purchase agreement",
        ],
    }

    assessment = evaluate_dilution(record)

    assert assessment.risk_level == "high"
    assert "active_shelf_registration" in assessment.reasons
    assert "recent_offering" in assessment.reasons
    assert "s1_s3_registration" in assessment.reasons
    assert "prospectus_supplement" in assessment.reasons
    assert "atm_offering" in assessment.reasons
    assert "registered_direct_offering" in assessment.reasons
    assert "warrants_outstanding" in assessment.reasons
    assert "convertible_debt" in assessment.reasons
    assert "equity_line" in assessment.reasons
    assert assessment.metrics.filing_match_count >= 6


def test_convertible_amount_sets_convertible_debt_signal():
    record = {"symbol": "NOTE", "convertible_debt_amount": 2_500_000}

    assessment = evaluate_dilution(record)

    assert assessment.metrics.convertible_debt is True
    assert "convertible_debt" in assessment.reasons


def test_share_growth_and_repeated_offerings_score_moderate():
    record = {
        "symbol": "GROW",
        "shares_outstanding_growth_pct": 40.0,
        "offering_count_12m": 2,
    }

    assessment = evaluate_dilution(record)

    assert assessment.risk_level == "moderate"
    assert "large_share_growth" in assessment.reasons
    assert "repeated_offering_history" in assessment.reasons


def test_no_dilution_signals_score_low_when_data_is_available():
    record = {
        "symbol": "CLEAN",
        "active_shelf_registration": False,
        "recent_offering": False,
        "atm_offering": False,
        "registered_direct_offering": False,
        "private_placement": False,
        "warrants_outstanding": False,
        "convertible_debt": False,
        "equity_line": False,
        "shares_outstanding_growth_pct": 2.0,
        "offering_count_12m": 0,
        "recent_filings": [],
    }

    assessment = evaluate_dilution(record)

    assert assessment.risk_level == "low"
    assert assessment.dilution_risk_score == 0
    assert assessment.reasons == ()


def test_missing_dilution_data_is_unknown_not_failure():
    assessment = evaluate_dilution({"symbol": "MISS"})

    assert assessment.risk_level == "unknown"
    assert assessment.dilution_risk_score == 0
    assert "dilution_data_missing" in assessment.warnings


def test_rules_load_from_config():
    rules = load_dilution_rules()

    assert isinstance(rules, DilutionRules)
    assert rules.high_score == 8
    assert rules.large_share_growth_pct == pytest.approx(20.0)


def test_batch_evaluation_scores_every_record():
    assessments = evaluate_dilution_batch([DILUTIVE_RECORD, {"symbol": "MISS"}])

    assert [assessment.symbol for assessment in assessments] == ["DILU", "MISS"]
