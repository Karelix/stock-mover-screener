import pytest

from stock_mover_screener.catalyst import (
    CatalystRules,
    evaluate_catalyst,
    evaluate_catalyst_batch,
    load_catalyst_rules,
)


def test_strong_earnings_guidance_catalyst():
    record = {
        "symbol": "BEAT",
        "headline": "Company reports earnings beat and raises guidance for FY2026",
    }

    assessment = evaluate_catalyst(record)

    assert assessment.category == "strong"
    assert "earnings_guidance" in assessment.reasons
    assert assessment.strong_catalyst_score >= 3


def test_strong_catalyst_can_outweigh_hype_words():
    record = {
        "symbol": "FDAI",
        "headline": "FDA approval for AI-assisted device after phase 3 met primary endpoint",
    }

    assessment = evaluate_catalyst(record)

    assert assessment.category == "strong"
    assert "fda_approval" in assessment.reasons
    assert "vague_ai" in assessment.reasons


def test_medium_catalyst_classification():
    record = {
        "symbol": "UPGD",
        "news": [
            "Analyst upgrade as company announces commercial product launch",
        ],
    }

    assessment = evaluate_catalyst(record)

    assert assessment.category == "medium"
    assert "analyst_upgrade" in assessment.reasons
    assert "product_launch" in assessment.reasons


def test_weak_hype_catalyst_classification():
    record = {
        "symbol": "HYPE",
        "headlines": [
            "Company announces AI partnership with unnamed partner",
            "No financial terms disclosed; Reddit traders cite short squeeze",
            "Non-binding LOI for blockchain initiative",
        ],
    }

    assessment = evaluate_catalyst(record)

    assert assessment.category == "weak"
    assert assessment.weak_catalyst_score >= 3
    assert "vague_ai" in assessment.reasons
    assert "unnamed_partner" in assessment.reasons
    assert "no_financial_terms" in assessment.reasons
    assert "social_media_meme" in assessment.reasons
    assert "short_squeeze" in assessment.reasons
    assert "non_binding_loi" in assessment.reasons
    assert "crypto_blockchain" in assessment.reasons


def test_no_obvious_catalyst_classification():
    assessment = evaluate_catalyst({"symbol": "NONE", "no_obvious_catalyst": True})

    assert assessment.category == "none"
    assert "no_obvious_catalyst" in assessment.reasons


def test_missing_catalyst_data_is_unknown_not_failure():
    assessment = evaluate_catalyst({"symbol": "MISS"})

    assert assessment.category == "unknown"
    assert assessment.weak_catalyst_score == 0
    assert "catalyst_data_missing" in assessment.warnings


def test_explicit_provider_category_is_respected():
    assessment = evaluate_catalyst({"symbol": "EXPL", "catalyst_category": "weak"})

    assert assessment.category == "weak"
    assert "explicit_weak_catalyst" in assessment.reasons


def test_rules_load_from_config():
    rules = load_catalyst_rules()

    assert isinstance(rules, CatalystRules)
    assert rules.weak_score_threshold == 3
    assert rules.fda_approval_points == pytest.approx(4)


def test_batch_evaluation_classifies_every_record():
    assessments = evaluate_catalyst_batch(
        [
            {"symbol": "BEAT", "headline": "earnings beat and raises guidance"},
            {"symbol": "MISS"},
        ]
    )

    assert [assessment.symbol for assessment in assessments] == ["BEAT", "MISS"]
