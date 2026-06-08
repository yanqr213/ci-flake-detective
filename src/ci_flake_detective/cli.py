"""Command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from .api import analyze_paths
from .config import load_config
from .models import DetectiveConfig
from .reporters import write_reports


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "show-default-config":
            print(json.dumps(DetectiveConfig.defaults().to_dict(), indent=2, ensure_ascii=False))
            return 0
        if args.command == "validate-config":
            load_config(args.config)
            print(f"Config OK: {args.config}")
            return 0
        if args.command == "analyze":
            return _run_analyze(args)
        parser.print_help()
        return 1
    except Exception as exc:  # pragma: no cover - validated by CLI integration tests.
        print(f"ci-flake-detective: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ci-flake-detective",
        description="Detect flaky tests, regressions, environment failures, duration drift, and retry effectiveness from CI test artifacts.",
    )
    sub = parser.add_subparsers(dest="command")

    analyze = sub.add_parser("analyze", help="Analyze JUnit XML and optional logs/durations.")
    analyze.add_argument("--junit", nargs="+", required=True, help="JUnit XML files or directories.")
    analyze.add_argument("--logs", nargs="*", default=[], help="Log files or directories.")
    analyze.add_argument("--durations", nargs="*", default=[], help="CSV/JSON duration history files or directories.")
    analyze.add_argument("--config", help="JSON config file.")
    analyze.add_argument("--output-dir", default="reports", help="Directory for report files.")
    analyze.add_argument(
        "--format",
        action="append",
        choices=["md", "markdown", "json", "csv"],
        default=[],
        help="Report format. Repeatable. Defaults to md/json/csv.",
    )
    analyze.add_argument("--strict", action="store_true", help="Fail on flaky, environment, and duration drift findings too.")
    analyze.add_argument("--quiet", action="store_true", help="Do not print summary.")

    validate = sub.add_parser("validate-config", help="Validate a JSON config file.")
    validate.add_argument("config")

    sub.add_parser("show-default-config", help="Print default JSON config.")
    return parser


def _run_analyze(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.strict:
        config.fail_on_flaky = True
        config.fail_on_environment = True
        config.fail_on_duration_drift = True
    formats = args.format or ["md", "json", "csv"]
    report = analyze_paths(
        junit_paths=args.junit,
        log_paths=args.logs,
        duration_paths=args.durations,
        config=config,
    )
    written = write_reports(report, args.output_dir, formats)
    code = report.exit_code()
    if not args.quiet:
        _print_summary(report.summary, written, code)
    return code


def _print_summary(summary: dict, written: List[Path], code: int) -> None:
    print("CI Flake Detective summary")
    print(f"  runs: {summary['run_count']}")
    print(f"  tests: {summary['test_count']}")
    print(f"  new regressions: {summary['new_regression_count']}")
    print(f"  flaky: {summary['flaky_count']}")
    print(f"  environment: {summary['environment_count']}")
    print(f"  timeout: {summary['timeout_count']}")
    print(f"  duration drift: {summary['duration_drift_count']}")
    for path in written:
        print(f"  wrote: {path}")
    print(f"  exit code: {code}")


if __name__ == "__main__":
    raise SystemExit(main())

