"""Report writers for Markdown, JSON, and CSV outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, List

from .models import AnalysisReport, TestInsight


CSV_FIELDS = [
    "test_id",
    "category",
    "severity",
    "latest_status",
    "failure_count",
    "pass_count",
    "run_count",
    "log_category",
    "retry_attempts",
    "retry_effective",
    "duration_latest",
    "duration_p50",
    "duration_drift_ratio",
    "duration_drift_seconds",
    "affected_area",
    "reasons",
]


def write_reports(report: AnalysisReport, output_dir: str, formats: Iterable[str]) -> List[Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    wanted = {fmt.lower() for fmt in formats}
    if "json" in wanted:
        path = out / "ci-flake-report.json"
        write_json(report, path)
        written.append(path)
    if "csv" in wanted:
        path = out / "ci-flake-report.csv"
        write_csv(report, path)
        written.append(path)
    if "md" in wanted or "markdown" in wanted:
        path = out / "ci-flake-report.md"
        write_markdown(report, path)
        written.append(path)
    return written


def write_json(report: AnalysisReport, path: Path) -> None:
    path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def write_csv(report: AnalysisReport, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for insight in report.insights:
            row = insight.to_dict()
            row["reasons"] = "; ".join(row["reasons"])
            writer.writerow({key: row.get(key, "") for key in CSV_FIELDS})


def write_markdown(report: AnalysisReport, path: Path) -> None:
    path.write_text(render_markdown(report), encoding="utf-8")


def render_markdown(report: AnalysisReport) -> str:
    summary = report.summary
    lines = [
        "# CI Flake Detective Report",
        "",
        "## Summary",
        "",
        f"- Runs: {summary['run_count']}",
        f"- Tests: {summary['test_count']}",
        f"- Observations: {summary['case_observation_count']}",
        f"- Failed observations: {summary['failed_observation_count']}",
        f"- New regressions: {summary['new_regression_count']}",
        f"- Flaky tests: {summary['flaky_count']}",
        f"- Environment failures: {summary['environment_count']}",
        f"- Timeout failures: {summary['timeout_count']}",
        f"- Duration drift: {summary['duration_drift_count']}",
        "",
        "## Top Insights",
        "",
        "| Test | Category | Severity | Latest | Runs | Failure/Pass | Log | Duration | Area | Reasons |",
        "| --- | --- | --- | --- | ---: | --- | --- | ---: | --- | --- |",
    ]
    for insight in report.insights:
        lines.append(_insight_row(insight))
    lines.extend(
        [
            "",
            "## Exit Policy",
            "",
            f"- Exit code: `{report.exit_code()}`",
            f"- fail_on_new_regression: `{report.config.fail_on_new_regression}`",
            f"- fail_on_flaky: `{report.config.fail_on_flaky}`",
            f"- fail_on_environment: `{report.config.fail_on_environment}`",
            f"- fail_on_duration_drift: `{report.config.fail_on_duration_drift}`",
            "",
            "## Field Notes",
            "",
            "- `new_regression`: latest observation failed after enough prior passes.",
            "- `flaky`: historical pass/fail mix across enough runs.",
            "- `environment_failure`: failure log matched infrastructure, network, runner, or service patterns.",
            "- `duration_drift`: latest duration exceeded both absolute and ratio thresholds.",
            "- `retry_effective`: at least one failed attempt later passed in the same run.",
            "",
        ]
    )
    return "\n".join(lines)


def _insight_row(insight: TestInsight) -> str:
    reasons = "; ".join(insight.reasons)
    duration = f"{insight.duration_latest:.3f}s / p50 {insight.duration_p50:.3f}s"
    return (
        f"| {_md(insight.test_id)} | {insight.category} | {insight.severity} | "
        f"{insight.latest_status} | {len(set(insight.run_ids))} | "
        f"{insight.failure_count}/{insight.pass_count} | {insight.log_category} | "
        f"{duration} | {_md(insight.affected_area)} | {_md(reasons)} |"
    )


def _md(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")

