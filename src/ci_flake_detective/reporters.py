"""Report writers for Markdown, JSON, and CSV outputs."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from . import __version__
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
    if "sarif" in wanted:
        path = out / "ci-flake-report.sarif"
        write_sarif(report, path)
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


def write_sarif(report: AnalysisReport, path: Path) -> None:
    path.write_text(render_sarif(report), encoding="utf-8")


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


def render_sarif(report: AnalysisReport) -> str:
    findings = [insight for insight in report.insights if insight.category != "stable"]
    sarif = {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "ci-flake-detective",
                        "semanticVersion": __version__,
                        "informationUri": "https://github.com/yanqr213/ci-flake-detective",
                        "rules": _sarif_rules(findings),
                    }
                },
                "automationDetails": {"id": "ci-flake-detective"},
                "results": [_insight_to_sarif(insight) for insight in findings],
                "properties": {
                    "summary": report.summary,
                    "exitCode": report.exit_code(),
                    "generatedBy": report.generated_by,
                },
            }
        ],
    }
    return json.dumps(sarif, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sarif_rules(insights: List[TestInsight]) -> List[Dict[str, Any]]:
    categories = sorted({insight.category for insight in insights})
    return [
        {
            "id": _rule_id(category),
            "name": category.replace("_", " ").title(),
            "shortDescription": {"text": f"CI test insight: {category}."},
            "fullDescription": {"text": _rule_help(category)},
            "defaultConfiguration": {"level": _level_for_category(category)},
            "help": {"text": _rule_help(category), "markdown": _rule_help(category)},
            "properties": {
                "precision": "medium",
                "tags": ["ci", "flaky-tests", "junit", "test-governance", category],
            },
        }
        for category in categories
    ]


def _insight_to_sarif(insight: TestInsight) -> Dict[str, Any]:
    message = (
        f"{insight.test_id}: {insight.category} ({insight.severity}). "
        f"Latest status {insight.latest_status}; failures/passes {insight.failure_count}/{insight.pass_count}. "
        f"{'; '.join(insight.reasons)}"
    )
    return {
        "ruleId": _rule_id(insight.category),
        "level": _level_for_category(insight.category),
        "message": {"text": _trim(message, 800)},
        "locations": [_location_for_insight(insight)],
        "partialFingerprints": {
            "ciFlakeDetective/v1": hashlib.sha256(f"{insight.test_id}|{insight.category}|{insight.affected_area}".encode("utf-8")).hexdigest()[:32]
        },
        "properties": insight.to_dict(),
    }


def _location_for_insight(insight: TestInsight) -> Dict[str, Any]:
    uri = _artifact_uri(insight.affected_area)
    return {
        "physicalLocation": {
            "artifactLocation": {"uri": uri},
            "region": {"startLine": 1},
        },
        "logicalLocations": [
            {
                "name": insight.test_id,
                "fullyQualifiedName": insight.test_id,
                "kind": "function",
            }
        ],
    }


def _artifact_uri(value: str) -> str:
    if value and value != "unknown":
        return value.replace("\\", "/")
    return "ci-test-history"


def _rule_id(category: str) -> str:
    return f"ci-flake.{category or 'unknown'}"


def _level_for_category(category: str) -> str:
    if category == "new_regression":
        return "error"
    if category in {"flaky", "environment_failure", "timeout_failure"}:
        return "warning"
    return "note"


def _rule_help(category: str) -> str:
    help_text = {
        "new_regression": "The latest CI observation failed after enough prior passes. Treat this as a likely pull-request regression.",
        "flaky": "The test has both passing and failing observations across history. Stabilize or quarantine before relying on it as a gate.",
        "environment_failure": "The latest failure matched infrastructure, network, runner, disk, or service patterns.",
        "timeout_failure": "The latest failure matched timeout patterns. Investigate deadlocks, slow dependencies, or test time budgets.",
        "duration_drift": "The latest duration exceeded both ratio and absolute drift thresholds compared with history.",
        "slow": "The test exceeded the configured slow-test threshold.",
        "retry_effective": "A failed attempt later passed in the same run, indicating retry sensitivity.",
        "failure": "The latest observation failed but did not match a more specific category.",
    }
    return help_text.get(category, "Review this CI test insight and decide whether to fix, quarantine, or update thresholds.")


def _trim(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."
