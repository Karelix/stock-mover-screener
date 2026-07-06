from stock_mover_screener.pipeline import (
    scan_catalyst_premarket_candidates,
    scan_dilution_premarket_candidates,
    scan_fundamental_premarket_candidates,
    scan_hype_premarket_candidates,
    scan_labeled_premarket_candidates,
    scan_squeeze_premarket_candidates,
    scan_tradeable_premarket_candidates,
    scan_universe_premarket_movers,
)


BASE_RECORD = {
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
    "short_interest_pct_float": 45.0,
    "days_to_cover": 7.0,
    "borrow_fee_pct": 120.0,
    "hard_to_borrow": True,
    "borrow_available_shares": 0,
    "halts_count": 3,
    "call_volume_ratio": 5.0,
}


def test_pipeline_applies_universe_before_premarket_scan():
    common_stock = {**BASE_RECORD, "symbol": "MOMO"}
    moving_etf = {**BASE_RECORD, "symbol": "ETFZ", "security_type": "etf"}

    decisions = scan_universe_premarket_movers([moving_etf, common_stock])

    assert [decision.symbol for decision in decisions] == ["MOMO"]


def test_tradeable_pipeline_applies_liquidity_after_premarket_scan():
    liquid = {**BASE_RECORD, "symbol": "MOMO"}
    wide_spread = {
        **BASE_RECORD,
        "symbol": "WIDE",
        "premarket_bid": 9.0,
        "premarket_ask": 12.0,
    }

    candidates = scan_tradeable_premarket_candidates([wide_spread, liquid])

    assert [candidate.symbol for candidate in candidates] == ["MOMO"]


def test_tradeable_pipeline_preserves_low_float_risk_flag():
    low_float = {**BASE_RECORD, "symbol": "LOWF", "float_shares": 8_000_000}

    candidates = scan_tradeable_premarket_candidates([low_float])

    assert len(candidates) == 1
    assert candidates[0].liquidity.risk_flags == ("very_low_float",)


def test_fundamental_pipeline_scores_after_optional_liquidity():
    candidate = {**BASE_RECORD, "symbol": "WEAK"}

    candidates = scan_fundamental_premarket_candidates([candidate])

    assert [item.symbol for item in candidates] == ["WEAK"]
    assert candidates[0].fundamentals.weakness_level == "high"
    assert candidates[0].liquidity is not None


def test_fundamental_pipeline_can_skip_liquidity_filter():
    wide_spread = {
        **BASE_RECORD,
        "symbol": "WIDE",
        "premarket_bid": 9.0,
        "premarket_ask": 12.0,
    }

    with_liquidity = scan_fundamental_premarket_candidates([wide_spread])
    without_liquidity = scan_fundamental_premarket_candidates(
        [wide_spread], use_liquidity=False
    )

    assert with_liquidity == []
    assert [item.symbol for item in without_liquidity] == ["WIDE"]
    assert without_liquidity[0].liquidity is None


def test_dilution_pipeline_scores_after_fundamentals():
    candidate = {**BASE_RECORD, "symbol": "DILU"}

    candidates = scan_dilution_premarket_candidates([candidate])

    assert [item.symbol for item in candidates] == ["DILU"]
    assert candidates[0].fundamentals.weakness_level == "high"
    assert candidates[0].dilution.risk_level == "high"
    assert candidates[0].liquidity is not None


def test_dilution_pipeline_can_skip_liquidity_filter():
    wide_spread = {
        **BASE_RECORD,
        "symbol": "WIDE",
        "premarket_bid": 9.0,
        "premarket_ask": 12.0,
    }

    with_liquidity = scan_dilution_premarket_candidates([wide_spread])
    without_liquidity = scan_dilution_premarket_candidates(
        [wide_spread], use_liquidity=False
    )

    assert with_liquidity == []
    assert [item.symbol for item in without_liquidity] == ["WIDE"]
    assert without_liquidity[0].liquidity is None
    assert without_liquidity[0].dilution.risk_level == "high"


def test_dilution_pipeline_sorts_by_dilution_then_fundamentals():
    lower_risk = {
        **BASE_RECORD,
        "symbol": "LOWR",
        "active_shelf_registration": False,
        "recent_offering": False,
        "atm_offering": False,
        "warrants_outstanding": False,
        "convertible_debt": False,
        "shares_outstanding_growth_pct": 0.0,
        "offering_count_12m": 0,
    }
    higher_risk = {**BASE_RECORD, "symbol": "HIGR"}

    candidates = scan_dilution_premarket_candidates([lower_risk, higher_risk])

    assert [item.symbol for item in candidates] == ["HIGR", "LOWR"]


def test_catalyst_pipeline_scores_after_dilution():
    candidate = {**BASE_RECORD, "symbol": "HYPE"}

    candidates = scan_catalyst_premarket_candidates([candidate])

    assert [item.symbol for item in candidates] == ["HYPE"]
    assert candidates[0].fundamentals.weakness_level == "high"
    assert candidates[0].dilution.risk_level == "high"
    assert candidates[0].catalyst.category == "weak"
    assert candidates[0].liquidity is not None


def test_catalyst_pipeline_can_skip_liquidity_filter():
    wide_spread = {
        **BASE_RECORD,
        "symbol": "WIDE",
        "premarket_bid": 9.0,
        "premarket_ask": 12.0,
    }

    with_liquidity = scan_catalyst_premarket_candidates([wide_spread])
    without_liquidity = scan_catalyst_premarket_candidates(
        [wide_spread], use_liquidity=False
    )

    assert with_liquidity == []
    assert [item.symbol for item in without_liquidity] == ["WIDE"]
    assert without_liquidity[0].liquidity is None
    assert without_liquidity[0].catalyst.category == "weak"


def test_catalyst_pipeline_sorts_by_weak_catalyst_first():
    strong = {
        **BASE_RECORD,
        "symbol": "STRG",
        "headlines": ["Company reports earnings beat and raises guidance"],
    }
    weak = {**BASE_RECORD, "symbol": "WEAK"}

    candidates = scan_catalyst_premarket_candidates([strong, weak])

    assert [item.symbol for item in candidates] == ["WEAK", "STRG"]


def test_hype_pipeline_scores_after_catalyst():
    candidate = {**BASE_RECORD, "symbol": "HYPE"}

    candidates = scan_hype_premarket_candidates([candidate])

    assert [item.symbol for item in candidates] == ["HYPE"]
    assert candidates[0].fundamentals.weakness_level == "high"
    assert candidates[0].dilution.risk_level == "high"
    assert candidates[0].catalyst.category == "weak"
    assert candidates[0].hype.hype_level == "high"
    assert candidates[0].liquidity is not None


def test_hype_pipeline_can_skip_liquidity_filter():
    wide_spread = {
        **BASE_RECORD,
        "symbol": "WIDE",
        "premarket_bid": 9.0,
        "premarket_ask": 12.0,
    }

    with_liquidity = scan_hype_premarket_candidates([wide_spread])
    without_liquidity = scan_hype_premarket_candidates(
        [wide_spread], use_liquidity=False
    )

    assert with_liquidity == []
    assert [item.symbol for item in without_liquidity] == ["WIDE"]
    assert without_liquidity[0].liquidity is None
    assert without_liquidity[0].hype.hype_level == "high"


def test_hype_pipeline_sorts_by_hype_first():
    low_hype = {
        **BASE_RECORD,
        "symbol": "LOWH",
        "headlines": ["Company announces routine investor conference schedule"],
        "social_mentions": 80,
        "average_social_mentions": 100,
        "headline_count_today": 1,
        "average_headline_count": 1,
    }
    high_hype = {**BASE_RECORD, "symbol": "HIGH"}

    candidates = scan_hype_premarket_candidates([low_hype, high_hype])

    assert [item.symbol for item in candidates] == ["HIGH", "LOWH"]


def test_squeeze_pipeline_scores_after_hype():
    candidate = {**BASE_RECORD, "symbol": "SQZ", "float_shares": 5_000_000}

    candidates = scan_squeeze_premarket_candidates([candidate])

    assert [item.symbol for item in candidates] == ["SQZ"]
    assert candidates[0].fundamentals.weakness_level == "high"
    assert candidates[0].dilution.risk_level == "high"
    assert candidates[0].catalyst.category == "weak"
    assert candidates[0].hype.hype_level == "high"
    assert candidates[0].squeeze.risk_level == "extreme"
    assert candidates[0].liquidity is not None


def test_squeeze_pipeline_can_skip_liquidity_filter():
    wide_spread = {
        **BASE_RECORD,
        "symbol": "WIDE",
        "premarket_bid": 9.0,
        "premarket_ask": 12.0,
    }

    with_liquidity = scan_squeeze_premarket_candidates([wide_spread])
    without_liquidity = scan_squeeze_premarket_candidates(
        [wide_spread], use_liquidity=False
    )

    assert with_liquidity == []
    assert [item.symbol for item in without_liquidity] == ["WIDE"]
    assert without_liquidity[0].liquidity is None
    assert without_liquidity[0].squeeze.risk_level == "extreme"


def test_squeeze_pipeline_sorts_by_squeeze_risk_first():
    lower_risk = {
        **BASE_RECORD,
        "symbol": "LOWR",
        "short_interest_pct_float": 2.0,
        "days_to_cover": 1.0,
        "borrow_fee_pct": 1.0,
        "hard_to_borrow": False,
        "borrow_available_shares": 5_000_000,
        "halts_count": 0,
        "call_volume_ratio": 1.0,
    }
    higher_risk = {**BASE_RECORD, "symbol": "HIGR", "float_shares": 5_000_000}

    candidates = scan_squeeze_premarket_candidates([lower_risk, higher_risk])

    assert [item.symbol for item in candidates] == ["HIGR", "LOWR"]


def test_labeled_pipeline_adds_final_label_after_squeeze():
    candidate = {**BASE_RECORD, "symbol": "LBL", "float_shares": 5_000_000}

    candidates = scan_labeled_premarket_candidates([candidate])

    assert [item.symbol for item in candidates] == ["LBL"]
    assert candidates[0].label.final_label == "Too Dangerous"
    assert candidates[0].squeeze.risk_level == "extreme"
    assert candidates[0].hype.hype_level == "high"


def test_labeled_pipeline_can_skip_liquidity_filter():
    wide_spread = {
        **BASE_RECORD,
        "symbol": "WIDE",
        "premarket_bid": 9.0,
        "premarket_ask": 12.0,
    }

    with_liquidity = scan_labeled_premarket_candidates([wide_spread])
    without_liquidity = scan_labeled_premarket_candidates(
        [wide_spread], use_liquidity=False
    )

    assert with_liquidity == []
    assert [item.symbol for item in without_liquidity] == ["WIDE"]
    assert without_liquidity[0].liquidity is None
    assert "liquidity_filter_not_applied" in without_liquidity[0].label.warnings
