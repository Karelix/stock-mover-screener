from stock_mover_screener.universe import UniverseRules, evaluate_universe, filter_universe


BASE_RECORD = {
    "symbol": "ABCD",
    "country": "US",
    "security_type": "common_stock",
    "price": 8.5,
    "market_cap": 250_000_000,
    "average_dollar_volume": 12_000_000,
}


def test_common_stock_passes_base_universe():
    decision = evaluate_universe(BASE_RECORD)

    assert decision.passed
    assert decision.reasons == ()


def test_biotech_is_not_excluded_by_sector():
    record = {**BASE_RECORD, "sector": "Healthcare", "industry": "Biotechnology"}

    decision = evaluate_universe(record)

    assert decision.passed


def test_etfs_are_excluded():
    record = {**BASE_RECORD, "symbol": "SPY", "security_type": "etf"}

    decision = evaluate_universe(record)

    assert not decision.passed
    assert "excluded_security_type:etf" in decision.reasons


def test_low_liquidity_is_excluded():
    record = {**BASE_RECORD, "average_dollar_volume": 500_000}

    decision = evaluate_universe(record)

    assert not decision.passed
    assert "average_dollar_volume_below_minimum" in decision.reasons


def test_unknown_country_or_security_type_is_excluded():
    record = {**BASE_RECORD, "country": "", "security_type": ""}

    decision = evaluate_universe(record)

    assert not decision.passed
    assert "missing_country" in decision.reasons
    assert "missing_security_type" in decision.reasons


def test_filter_universe_keeps_only_passing_records():
    records = [
        BASE_RECORD,
        {**BASE_RECORD, "symbol": "CHEAP", "price": 1.25},
        {**BASE_RECORD, "symbol": "BIOX", "industry": "Biotechnology"},
    ]

    passing = filter_universe(records, UniverseRules())

    assert [record["symbol"] for record in passing] == ["ABCD", "BIOX"]
