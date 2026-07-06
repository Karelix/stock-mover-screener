"""Command line runner for CSV-backed pre-market scans."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence, TextIO

from stock_mover_screener.runner import (
    DEFAULT_CONFIG_DIR,
    scan_csv as run_scan_csv,
    write_summary_csv,
    write_summary_csv_file,
)


def scan_csv(
    input_path: str | Path,
    *,
    config_dir: str | Path = DEFAULT_CONFIG_DIR,
    use_liquidity: bool = True,
) -> list[dict[str, object]]:
    """Run the full labeled scanner against CSV records and return summary rows."""

    return run_scan_csv(
        input_path,
        config_dir=config_dir,
        use_liquidity=use_liquidity,
    ).summary_rows


def _run_scan(args: argparse.Namespace, stdout: TextIO, stderr: TextIO) -> int:
    rows = scan_csv(
        args.input,
        config_dir=args.config_dir,
        use_liquidity=not args.no_liquidity,
    )

    if args.output:
        write_summary_csv_file(rows, args.output)
        print(f"Wrote {len(rows)} candidate(s) to {args.output}", file=stderr)
        return 0

    write_summary_csv(rows, stdout)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stock-mover-screener",
        description="Run the stock mover screener against normalized CSV records.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser(
        "scan",
        help="scan normalized pre-market records from CSV",
    )
    scan_parser.add_argument("input", type=Path, help="input CSV path")
    scan_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="write summary CSV results to this path instead of stdout",
    )
    scan_parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="directory containing screener JSON config files",
    )
    scan_parser.add_argument(
        "--no-liquidity",
        action="store_true",
        help="score records without applying the liquidity filter",
    )
    scan_parser.set_defaults(func=_run_scan)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    active_stdout = stdout or sys.stdout
    active_stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.func(args, active_stdout, active_stderr)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=active_stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
