from stock_mover_screener.dashboard import (
    filter_summary_rows,
    find_detail,
    label_counts,
)


ROWS = [
    {
        "symbol": "HYPE",
        "final_label": "Too Dangerous",
        "confidence": 95,
        "premarket_move_pct": 20.0,
        "squeeze_level": "extreme",
    },
    {
        "symbol": "REAL",
        "final_label": "Likely Real Catalyst",
        "confidence": 75,
        "premarket_move_pct": 16.7,
        "squeeze_level": "low",
    },
]


def test_filter_summary_rows_applies_dashboard_controls():
    rows = filter_summary_rows(
        ROWS,
        labels=["Too Dangerous"],
        squeeze_levels=["extreme"],
        min_confidence=90,
        min_move_pct=18.0,
    )

    assert [row["symbol"] for row in rows] == ["HYPE"]


def test_label_counts_preserves_known_label_order():
    counts = label_counts(ROWS)

    assert list(counts) == ["Too Dangerous", "Likely Real Catalyst"]
    assert counts["Too Dangerous"] == 1


def test_find_detail_matches_symbols_case_insensitively():
    detail = find_detail(
        [{"symbol": "HYPE", "label": {"final_label": "Too Dangerous"}}],
        "hype",
    )

    assert detail == {"symbol": "HYPE", "label": {"final_label": "Too Dangerous"}}
