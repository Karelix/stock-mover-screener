import pytest

from stock_mover_screener.hype import (
    HypeRules,
    evaluate_hype,
    evaluate_hype_batch,
    load_hype_rules,
)


HIGH_HYPE_RECORD = {
    "symbol": "HYPE",
    "headlines": [
        "AI blockchain stock goes viral on Reddit and Stocktwits",
        "Retail traders cite short squeeze and meme momentum",
        "Influencer calls for diamond hands and to the moon move",
    ],
    "social_mentions": 900,
    "average_social_mentions": 100,
    "headline_count_today": 5,
    "average_headline_count": 1,
    "float_shares": 8_000_000,
    "premarket_price": 12.0,
    "previous_close": 10.0,
}


def test_high_hype_scores_from_text_and_attention_metrics():
    assessment = evaluate_hype(HIGH_HYPE_RECORD)

    assert assessment.hype_level == "high"
    assert assessment.hype_score >= 8
    assert "meme_keywords" in assessment.reasons
    assert "social_attention" in assessment.reasons
    assert "short_squeeze_language" in assessment.reasons
    assert "buzzword_theme" in assessment.reasons
    assert "abnormal_social_mentions" in assessment.reasons
    assert "abnormal_headline_velocity" in assessment.reasons
    assert "multiple_same_day_headlines" in assessment.reasons
    assert "retail_trader_language" in assessment.reasons
    assert "low_float_hype" in assessment.reasons
    assert "attention_driven_move" in assessment.reasons
    assert assessment.metrics.social_mentions_ratio == pytest.approx(9.0)
    assert assessment.metrics.headline_count_ratio == pytest.approx(5.0)
    assert assessment.metrics.premarket_move_pct == pytest.approx(20.0)


def test_numeric_social_spike_can_score_hype_without_text():
    record = {
        "symbol": "SPIK",
        "social_mentions": 400,
        "average_social_mentions": 100,
        "headline_count": 1,
        "average_headline_count": 1,
        "float_shares": 50_000_000,
        "premarket_move_pct": 5.0,
    }

    assessment = evaluate_hype(record)

    assert assessment.hype_level == "low"
    assert "abnormal_social_mentions" in assessment.reasons


def test_clean_attention_data_scores_low():
    record = {
        "symbol": "CALM",
        "headline": "Company announces routine investor conference schedule",
        "social_mentions": 80,
        "average_social_mentions": 100,
        "headline_count": 1,
        "average_headline_count": 1,
        "float_shares": 80_000_000,
        "premarket_move_pct": 3.0,
    }

    assessment = evaluate_hype(record)

    assert assessment.hype_level == "low"
    assert assessment.hype_score == 0
    assert assessment.reasons == ()


def test_missing_hype_data_is_unknown_not_failure():
    assessment = evaluate_hype({"symbol": "MISS"})

    assert assessment.hype_level == "unknown"
    assert assessment.hype_score == 0
    assert "hype_data_missing" in assessment.warnings


def test_headline_count_can_be_inferred_from_text_count():
    record = {
        "symbol": "TEXT",
        "headlines": ["AI partnership", "Crypto launch", "Reddit buzz"],
        "average_headline_count": 1,
    }

    assessment = evaluate_hype(record)

    assert assessment.metrics.headline_count == pytest.approx(3.0)
    assert "multiple_same_day_headlines" in assessment.reasons
    assert "abnormal_headline_velocity" in assessment.reasons


def test_rules_load_from_config():
    rules = load_hype_rules()

    assert isinstance(rules, HypeRules)
    assert rules.high_score == 8
    assert rules.low_float_shares == pytest.approx(20_000_000)


def test_batch_evaluation_scores_every_record():
    assessments = evaluate_hype_batch([HIGH_HYPE_RECORD, {"symbol": "MISS"}])

    assert [assessment.symbol for assessment in assessments] == ["HYPE", "MISS"]
