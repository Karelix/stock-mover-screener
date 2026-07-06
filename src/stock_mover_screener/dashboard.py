"""Streamlit dashboard for CSV-backed market mover scans."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from stock_mover_screener.runner import (
    DEFAULT_CONFIG_DIR,
    ScanResult,
    scan_csv,
    scan_csv_text,
    summary_rows_to_csv,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLE_PATH = PROJECT_ROOT / "examples" / "sample_premarket.csv"

LABEL_ORDER = (
    "Prime Watch",
    "Watch Only",
    "Too Dangerous",
    "Needs More Data",
    "Likely Real Catalyst",
    "Ignore",
)
SQUEEZE_LEVEL_ORDER = ("extreme", "high", "moderate", "low", "unknown")


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def filter_summary_rows(
    rows: list[dict[str, Any]],
    *,
    labels: Iterable[str] | None = None,
    squeeze_levels: Iterable[str] | None = None,
    min_confidence: int = 0,
    min_move_pct: float = 0.0,
) -> list[dict[str, Any]]:
    """Filter flat summary rows for dashboard controls."""

    label_set = set(labels or ())
    squeeze_level_set = set(squeeze_levels or ())
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if label_set and row.get("final_label") not in label_set:
            continue
        if squeeze_level_set and row.get("squeeze_level") not in squeeze_level_set:
            continue
        if _as_float(row.get("confidence")) < min_confidence:
            continue
        if _as_float(row.get("premarket_move_pct")) < min_move_pct:
            continue
        filtered.append(row)
    return filtered


def label_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {label: 0 for label in LABEL_ORDER}
    for row in rows:
        label = str(row.get("final_label") or "")
        counts[label] = counts.get(label, 0) + 1
    return {label: count for label, count in counts.items() if count}


def find_detail(
    full_details: list[dict[str, Any]], symbol: str
) -> dict[str, Any] | None:
    normalized_symbol = symbol.strip().upper()
    for detail in full_details:
        if str(detail.get("symbol") or "").strip().upper() == normalized_symbol:
            return detail
    return None


def _load_streamlit():
    try:
        import streamlit as st
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Streamlit is not installed. Install it with "
            '`python -m pip install -e ".[dashboard]"`.'
        ) from exc
    return st


def _load_scan_result(st: Any, use_liquidity: bool) -> ScanResult:
    uploaded_file = st.sidebar.file_uploader("CSV", type=["csv"])
    if uploaded_file is not None:
        csv_text = uploaded_file.getvalue().decode("utf-8-sig")
        return scan_csv_text(
            csv_text,
            config_dir=DEFAULT_CONFIG_DIR,
            use_liquidity=use_liquidity,
            source_name=uploaded_file.name,
        )

    return scan_csv(
        DEFAULT_SAMPLE_PATH,
        config_dir=DEFAULT_CONFIG_DIR,
        use_liquidity=use_liquidity,
    )


def _row_value(row: dict[str, Any], key: str, fallback: str = "-") -> str:
    value = row.get(key)
    if value is None or value == "":
        return fallback
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _render_metric_row(st: Any, rows: list[dict[str, Any]]) -> None:
    counts = label_counts(rows)
    columns = st.columns(5)
    columns[0].metric("Candidates", len(rows))
    columns[1].metric("Prime Watch", counts.get("Prime Watch", 0))
    columns[2].metric("Too Dangerous", counts.get("Too Dangerous", 0))
    max_move = max((_as_float(row.get("premarket_move_pct")) for row in rows), default=0)
    columns[3].metric("Max Move", f"{max_move:.1f}%")
    avg_confidence = (
        sum(_as_float(row.get("confidence")) for row in rows) / len(rows)
        if rows
        else 0
    )
    columns[4].metric("Avg Confidence", f"{avg_confidence:.0f}")


def _render_detail(st: Any, detail: dict[str, Any], summary_row: dict[str, Any]) -> None:
    st.subheader(str(detail.get("symbol", "")))
    columns = st.columns(4)
    columns[0].metric("Label", _row_value(summary_row, "final_label"))
    columns[1].metric("Move", f"{_as_float(summary_row.get('premarket_move_pct')):.1f}%")
    columns[2].metric("Thesis", str(detail.get("label", {}).get("thesis_score", "-")))
    columns[3].metric("Danger", str(detail.get("label", {}).get("danger_score", "-")))

    st.caption(str(detail.get("label", {}).get("summary", "")))
    overview_tab, signals_tab, details_tab = st.tabs(
        ["Overview", "Signals", "Full Detail"]
    )

    with overview_tab:
        st.dataframe(
            [
                {
                    "layer": "fundamentals",
                    "level": _row_value(summary_row, "fundamental_level"),
                    "score": _row_value(summary_row, "fundamental_score"),
                },
                {
                    "layer": "dilution",
                    "level": _row_value(summary_row, "dilution_level"),
                    "score": _row_value(summary_row, "dilution_score"),
                },
                {
                    "layer": "catalyst",
                    "level": _row_value(summary_row, "catalyst_category"),
                    "score": _row_value(summary_row, "weak_catalyst_score"),
                },
                {
                    "layer": "hype",
                    "level": _row_value(summary_row, "hype_level"),
                    "score": _row_value(summary_row, "hype_score"),
                },
                {
                    "layer": "squeeze",
                    "level": _row_value(summary_row, "squeeze_level"),
                    "score": _row_value(summary_row, "squeeze_score"),
                },
            ],
            hide_index=True,
            use_container_width=True,
        )

    with signals_tab:
        signal_rows = []
        for layer in (
            "label",
            "premarket",
            "liquidity",
            "fundamentals",
            "dilution",
            "catalyst",
            "hype",
            "squeeze",
        ):
            layer_detail = detail.get(layer) or {}
            for reason in layer_detail.get("reasons", ()):
                signal_rows.append({"layer": layer, "type": "reason", "value": reason})
            for warning in layer_detail.get("warnings", ()):
                signal_rows.append({"layer": layer, "type": "warning", "value": warning})
            for risk_flag in layer_detail.get("risk_flags", ()):
                signal_rows.append(
                    {"layer": layer, "type": "risk_flag", "value": risk_flag}
                )
        st.dataframe(signal_rows, hide_index=True, use_container_width=True)

    with details_tab:
        st.json(detail)


def main() -> None:
    st = _load_streamlit()
    st.set_page_config(page_title="Stock Mover Screener", layout="wide")
    st.title("Stock Mover Screener")

    st.sidebar.header("Scan")
    use_liquidity = st.sidebar.toggle("Liquidity filter", value=True)
    result = _load_scan_result(st, use_liquidity=use_liquidity)

    st.sidebar.header("Filters")
    selected_labels = st.sidebar.multiselect(
        "Labels",
        LABEL_ORDER,
        default=list(LABEL_ORDER),
    )
    selected_squeeze_levels = st.sidebar.multiselect(
        "Squeeze",
        SQUEEZE_LEVEL_ORDER,
        default=list(SQUEEZE_LEVEL_ORDER),
    )
    min_confidence = st.sidebar.slider("Min confidence", 0, 95, 0, 5)
    min_move_pct = st.sidebar.slider("Min move %", 0.0, 100.0, 0.0, 1.0)

    rows = filter_summary_rows(
        result.summary_rows,
        labels=selected_labels,
        squeeze_levels=selected_squeeze_levels,
        min_confidence=min_confidence,
        min_move_pct=min_move_pct,
    )

    _render_metric_row(st, rows)
    st.dataframe(rows, hide_index=True, use_container_width=True)
    st.download_button(
        "Download CSV",
        data=summary_rows_to_csv(rows),
        file_name="screener_results.csv",
        mime="text/csv",
    )

    if not rows:
        return

    selected_symbol = st.selectbox("Ticker", [str(row.get("symbol")) for row in rows])
    selected_row = next(row for row in rows if row.get("symbol") == selected_symbol)
    detail = find_detail(result.full_details, selected_symbol)
    if detail:
        _render_detail(st, detail, selected_row)


if __name__ == "__main__":
    main()
