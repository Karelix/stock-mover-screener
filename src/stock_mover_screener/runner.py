"""Reusable CSV scan helpers for command line and dashboard runners."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from stock_mover_screener.catalyst import load_catalyst_rules
from stock_mover_screener.dilution import load_dilution_rules
from stock_mover_screener.fundamentals import load_fundamental_rules
from stock_mover_screener.hype import load_hype_rules
from stock_mover_screener.labels import (
    candidate_to_full_dict,
    candidate_to_summary_row,
    load_label_rules,
)
from stock_mover_screener.liquidity import load_liquidity_rules
from stock_mover_screener.pipeline import (
    LabeledPremarketCandidate,
    scan_labeled_premarket_candidates,
)
from stock_mover_screener.premarket import load_premarket_scan_rules
from stock_mover_screener.squeeze import load_squeeze_rules
from stock_mover_screener.universe import load_universe_rules


DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

SUMMARY_FIELDNAMES = [
    "symbol",
    "final_label",
    "confidence",
    "summary",
    "premarket_move_pct",
    "mover_score",
    "liquidity_score",
    "fundamental_level",
    "fundamental_score",
    "dilution_level",
    "dilution_score",
    "catalyst_category",
    "weak_catalyst_score",
    "hype_level",
    "hype_score",
    "squeeze_level",
    "squeeze_score",
]


@dataclass(frozen=True)
class ScanResult:
    candidates: list[LabeledPremarketCandidate]
    summary_rows: list[dict[str, Any]]
    full_details: list[dict[str, Any]]


def _clean_csv_row(row: dict[str | None, str | None]) -> dict[str, Any]:
    return {
        key.strip(): value.strip() if isinstance(value, str) else value
        for key, value in row.items()
        if key is not None and key.strip()
    }


def read_csv_records(path: str | Path) -> list[dict[str, Any]]:
    """Read provider-normalized records from a CSV file."""

    input_path = Path(path)
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return read_csv_records_from_handle(handle, source_name=str(input_path))


def read_csv_records_from_text(
    csv_text: str, *, source_name: str = "uploaded CSV"
) -> list[dict[str, Any]]:
    """Read provider-normalized records from CSV text."""

    return read_csv_records_from_handle(io.StringIO(csv_text), source_name=source_name)


def read_csv_records_from_handle(
    handle: TextIO, *, source_name: str = "CSV input"
) -> list[dict[str, Any]]:
    """Read provider-normalized records from a text stream."""

    reader = csv.DictReader(handle)
    if reader.fieldnames is None:
        raise ValueError(f"{source_name} does not contain a CSV header")
    return [_clean_csv_row(row) for row in reader]


def scan_records(
    records: list[dict[str, Any]],
    *,
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
    use_liquidity: bool = True,
) -> ScanResult:
    """Run the full labeled scanner against normalized records."""

    config_path = Path(config_dir)
    candidates = scan_labeled_premarket_candidates(
        records,
        universe_rules=load_universe_rules(config_path / "universe.json"),
        premarket_rules=load_premarket_scan_rules(config_path / "premarket_scan.json"),
        liquidity_rules=load_liquidity_rules(config_path / "liquidity.json"),
        fundamental_rules=load_fundamental_rules(config_path / "fundamentals.json"),
        dilution_rules=load_dilution_rules(config_path / "dilution.json"),
        catalyst_rules=load_catalyst_rules(config_path / "catalyst.json"),
        hype_rules=load_hype_rules(config_path / "hype.json"),
        squeeze_rules=load_squeeze_rules(config_path / "squeeze.json"),
        label_rules=load_label_rules(config_path / "labels.json"),
        use_liquidity=use_liquidity,
    )
    return ScanResult(
        candidates=candidates,
        summary_rows=[candidate_to_summary_row(candidate) for candidate in candidates],
        full_details=[candidate_to_full_dict(candidate) for candidate in candidates],
    )


def scan_csv(
    input_path: str | Path,
    *,
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
    use_liquidity: bool = True,
) -> ScanResult:
    """Run the full labeled scanner against CSV records."""

    return scan_records(
        read_csv_records(input_path),
        config_dir=config_dir,
        use_liquidity=use_liquidity,
    )


def scan_csv_text(
    csv_text: str,
    *,
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
    use_liquidity: bool = True,
    source_name: str = "uploaded CSV",
) -> ScanResult:
    """Run the full labeled scanner against CSV text."""

    return scan_records(
        read_csv_records_from_text(csv_text, source_name=source_name),
        config_dir=config_dir,
        use_liquidity=use_liquidity,
    )


def write_summary_csv(rows: list[dict[str, Any]], handle: TextIO) -> None:
    writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDNAMES, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)


def write_summary_csv_file(rows: list[dict[str, Any]], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        write_summary_csv(rows, handle)


def summary_rows_to_csv(rows: list[dict[str, Any]]) -> str:
    handle = io.StringIO()
    write_summary_csv(rows, handle)
    return handle.getvalue()
