"""Historical aggregation and classification rules."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Dict, Iterable, List

from .log_classifier import classify_many
from .models import AnalysisReport, DetectiveConfig, RunRecord, TestCaseRecord, TestInsight


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def analyze_runs(
    runs: Iterable[RunRecord],
    config: DetectiveConfig | None = None,
    duration_history: Dict[str, List[float]] | None = None,
) -> AnalysisReport:
    cfg = config or DetectiveConfig.defaults()
    run_list = list(runs)
    by_test: Dict[str, List[TestCaseRecord]] = defaultdict(list)
    for run in run_list:
        for test in run.tests:
            by_test[test.test_id].append(test)

    insights = [
        _analyze_test(test_id, records, cfg, (duration_history or {}).get(test_id, []))
        for test_id, records in sorted(by_test.items())
    ]
    insights.sort(key=lambda item: (SEVERITY_ORDER.get(item.severity, 9), item.test_id))
    summary = _summary(run_list, insights)
    return AnalysisReport(runs=run_list, insights=insights, summary=summary, config=cfg)


def _analyze_test(
    test_id: str,
    records: List[TestCaseRecord],
    config: DetectiveConfig,
    external_durations: List[float],
) -> TestInsight:
    ordered = sorted(records, key=lambda item: (item.run_id, item.attempt))
    statuses = [record.status for record in ordered]
    run_ids = [record.run_id for record in ordered]
    durations = [record.duration for record in ordered if record.duration >= 0]
    all_durations = [value for value in external_durations + durations if value >= 0]
    failure_count = sum(1 for record in ordered if record.failed)
    pass_count = sum(1 for record in ordered if record.status == "passed")
    latest = ordered[-1] if ordered else None
    latest_status = latest.status if latest else "unknown"
    failed_messages = [record.message for record in ordered if record.failed and record.message]
    failed_outputs = [record.output for record in ordered if record.failed and record.output]
    log_category = classify_many(failed_messages, config.log_patterns)
    if log_category == "unknown":
        log_category = classify_many(failed_outputs, config.log_patterns)

    insight = TestInsight(
        test_id=test_id,
        statuses=statuses,
        run_ids=run_ids,
        durations=durations,
        failure_count=failure_count,
        pass_count=pass_count,
        latest_status=latest_status,
        log_category=log_category,
        retry_attempts=max((record.attempt for record in ordered), default=1),
        affected_area=_affected_area(ordered[0] if ordered else None, test_id),
        examples=_examples(ordered),
    )
    _fill_duration_fields(insight, all_durations, config)
    _fill_retry_fields(insight, ordered, config)
    _classify(insight, ordered, config)
    return insight


def _fill_duration_fields(insight: TestInsight, durations: List[float], config: DetectiveConfig) -> None:
    if not durations:
        return
    baseline_values = durations[:-1] or durations
    baseline = statistics.median(baseline_values)
    latest = durations[-1]
    insight.duration_p50 = baseline
    insight.duration_latest = latest
    insight.duration_drift_seconds = max(0.0, latest - baseline)
    if baseline > 0:
        insight.duration_drift_ratio = latest / baseline
    elif latest > 0:
        insight.duration_drift_ratio = float("inf")
    else:
        insight.duration_drift_ratio = 1.0
    if _has_duration_drift(insight, config):
        insight.reasons.append(
            f"duration drift: latest {latest:.3f}s vs p50 {baseline:.3f}s"
        )


def _fill_retry_fields(insight: TestInsight, records: List[TestCaseRecord], config: DetectiveConfig) -> None:
    by_run: Dict[str, List[TestCaseRecord]] = defaultdict(list)
    for record in records:
        by_run[record.run_id].append(record)
    for attempts in by_run.values():
        ordered = sorted(attempts, key=lambda item: item.attempt)
        if len(ordered) >= config.retry_effective_min_attempts:
            insight.retry_attempts = max(insight.retry_attempts, len(ordered))
            if ordered[0].failed and ordered[-1].status == "passed":
                insight.retry_effective = True
                insight.reasons.append("retry effective: failed attempt later passed")
                return


def _classify(insight: TestInsight, records: List[TestCaseRecord], config: DetectiveConfig) -> None:
    run_count = len(set(insight.run_ids))
    has_pass_and_fail = insight.failure_count > 0 and insight.pass_count > 0
    latest_failed = insight.latest_status in {"failed", "error"}
    prior = records[:-1]
    prior_passes = sum(1 for record in prior if record.status == "passed")

    if latest_failed and insight.log_category == "environment":
        insight.category = "environment_failure"
        insight.severity = "medium"
        insight.reasons.append("failure log matched environment pattern")
    elif latest_failed and insight.log_category == "timeout":
        insight.category = "timeout_failure"
        insight.severity = "high"
        insight.reasons.append("failure log matched timeout pattern")
    elif latest_failed and prior_passes >= config.regression_min_prior_passes and not insight.retry_effective:
        insight.category = "new_regression"
        insight.severity = "critical"
        insight.reasons.append(
            f"latest run failed after {prior_passes} prior pass(es)"
        )
    elif (
        run_count >= config.flaky_min_runs
        and insight.failure_count >= config.flaky_min_failures
        and (has_pass_and_fail or not config.flaky_requires_pass_and_fail)
    ):
        insight.category = "flaky"
        insight.severity = "high" if latest_failed else "medium"
        insight.reasons.append("mixed pass/fail history")
    elif latest_failed:
        insight.category = "failure"
        insight.severity = "high"
        insight.reasons.append("latest run failed")
    elif _has_duration_drift(insight, config):
        insight.category = "duration_drift"
        insight.severity = "medium"
    elif insight.duration_latest >= config.slow_test_seconds > 0:
        insight.category = "slow"
        insight.severity = "low"
        insight.reasons.append(f"latest duration >= {config.slow_test_seconds:.3f}s")
    else:
        insight.category = "stable"
        insight.severity = "info"
        insight.reasons.append("no instability signal detected")


def _has_duration_drift(insight: TestInsight, config: DetectiveConfig) -> bool:
    return (
        insight.duration_drift_seconds >= config.duration_drift_seconds
        and insight.duration_drift_ratio >= config.duration_drift_factor
    )


def _affected_area(record: TestCaseRecord | None, test_id: str) -> str:
    if record and record.file:
        return record.file.split("/")[0].split("\\")[0] or "unknown"
    if "::" in test_id:
        return test_id.split("::", 1)[0].split(".")[0] or "unknown"
    return "unknown"


def _examples(records: List[TestCaseRecord]) -> List[str]:
    out = []
    for record in records:
        if record.failed:
            snippet = (record.message or record.output).strip().replace("\n", " ")
            if snippet:
                out.append(snippet[:180])
        if len(out) >= 3:
            break
    return out


def _summary(runs: List[RunRecord], insights: List[TestInsight]) -> Dict[str, int]:
    categories = defaultdict(int)
    for insight in insights:
        categories[f"{insight.category}_count"] += 1
    environment_count = sum(
        1 for insight in insights if insight.category == "environment_failure" or insight.log_category == "environment"
    )
    timeout_count = sum(
        1 for insight in insights if insight.category == "timeout_failure" or insight.log_category == "timeout"
    )
    return {
        "run_count": len(runs),
        "test_count": len(insights),
        "case_observation_count": sum(len(run.tests) for run in runs),
        "failed_observation_count": sum(1 for run in runs for test in run.tests if test.failed),
        "flaky_count": categories["flaky_count"],
        "new_regression_count": categories["new_regression_count"],
        "environment_count": environment_count,
        "timeout_count": timeout_count,
        "duration_drift_count": categories["duration_drift_count"],
        "slow_count": categories["slow_count"],
        "failure_count": categories["failure_count"],
        "stable_count": categories["stable_count"],
    }
