"""Data models used by the analyzer and public API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


DEFAULT_LOG_PATTERNS = {
    "environment": [
        "ECONNRESET",
        "connection reset",
        "DNS",
        "ENOTFOUND",
        "502 Bad Gateway",
        "503 Service Unavailable",
        "rate limit",
        "temporarily unavailable",
        "No space left on device",
        "disk quota",
        "runner lost communication",
    ],
    "timeout": [
        "timeout",
        "timed out",
        "TimeoutError",
        "deadline exceeded",
        "exceeded timeout",
        "Test timeout",
    ],
    "assertion": [
        "AssertionError",
        "assert ",
        "expected",
        "actual",
        "Diff:",
        "Expected:",
    ],
    "dependency": [
        "ModuleNotFoundError",
        "ImportError",
        "Cannot find module",
        "npm ERR!",
        "pip install",
        "package not found",
    ],
}


@dataclass
class DetectiveConfig:
    """Tunable rules for test history classification."""

    flaky_min_runs: int = 3
    flaky_min_failures: int = 1
    flaky_requires_pass_and_fail: bool = True
    regression_min_prior_passes: int = 2
    duration_drift_factor: float = 1.8
    duration_drift_seconds: float = 5.0
    slow_test_seconds: float = 60.0
    retry_effective_min_attempts: int = 2
    fail_on_new_regression: bool = True
    fail_on_flaky: bool = False
    fail_on_environment: bool = False
    fail_on_duration_drift: bool = False
    log_patterns: Dict[str, List[str]] = field(default_factory=lambda: dict(DEFAULT_LOG_PATTERNS))

    @classmethod
    def defaults(cls) -> "DetectiveConfig":
        return cls()

    def validate(self) -> List[str]:
        errors = []
        if self.flaky_min_runs < 2:
            errors.append("flaky_min_runs must be >= 2")
        if self.flaky_min_failures < 1:
            errors.append("flaky_min_failures must be >= 1")
        if self.regression_min_prior_passes < 1:
            errors.append("regression_min_prior_passes must be >= 1")
        if self.duration_drift_factor <= 1:
            errors.append("duration_drift_factor must be > 1")
        if self.duration_drift_seconds < 0:
            errors.append("duration_drift_seconds must be >= 0")
        if self.slow_test_seconds < 0:
            errors.append("slow_test_seconds must be >= 0")
        if self.retry_effective_min_attempts < 2:
            errors.append("retry_effective_min_attempts must be >= 2")
        for key, value in self.log_patterns.items():
            if not isinstance(key, str) or not key:
                errors.append("log_patterns keys must be non-empty strings")
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                errors.append(f"log_patterns.{key} must be a list of strings")
        return errors

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DetectiveConfig":
        allowed = set(cls.__dataclass_fields__)
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ValueError(f"Unknown config keys: {', '.join(unknown)}")
        merged = cls.defaults()
        for key, value in data.items():
            setattr(merged, key, value)
        errors = merged.validate()
        if errors:
            raise ValueError("; ".join(errors))
        return merged

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flaky_min_runs": self.flaky_min_runs,
            "flaky_min_failures": self.flaky_min_failures,
            "flaky_requires_pass_and_fail": self.flaky_requires_pass_and_fail,
            "regression_min_prior_passes": self.regression_min_prior_passes,
            "duration_drift_factor": self.duration_drift_factor,
            "duration_drift_seconds": self.duration_drift_seconds,
            "slow_test_seconds": self.slow_test_seconds,
            "retry_effective_min_attempts": self.retry_effective_min_attempts,
            "fail_on_new_regression": self.fail_on_new_regression,
            "fail_on_flaky": self.fail_on_flaky,
            "fail_on_environment": self.fail_on_environment,
            "fail_on_duration_drift": self.fail_on_duration_drift,
            "log_patterns": self.log_patterns,
        }


@dataclass
class TestCaseRecord:
    run_id: str
    name: str
    classname: str = ""
    file: str = ""
    status: str = "passed"
    duration: float = 0.0
    message: str = ""
    output: str = ""
    failure_type: str = ""
    attempt: int = 1
    source: str = ""

    @property
    def test_id(self) -> str:
        parts = [self.classname.strip(), self.name.strip()]
        compact = "::".join(part for part in parts if part)
        return compact or self.name.strip()

    @property
    def failed(self) -> bool:
        return self.status in {"failed", "error"}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "test_id": self.test_id,
            "name": self.name,
            "classname": self.classname,
            "file": self.file,
            "status": self.status,
            "duration": self.duration,
            "message": self.message,
            "failure_type": self.failure_type,
            "attempt": self.attempt,
            "source": self.source,
        }


@dataclass
class RunRecord:
    run_id: str
    source: str
    tests: List[TestCaseRecord] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source": self.source,
            "metadata": self.metadata,
            "tests": [test.to_dict() for test in self.tests],
        }


@dataclass
class TestInsight:
    test_id: str
    statuses: List[str]
    run_ids: List[str]
    durations: List[float]
    failure_count: int = 0
    pass_count: int = 0
    latest_status: str = "unknown"
    category: str = "stable"
    log_category: str = "unknown"
    severity: str = "info"
    reasons: List[str] = field(default_factory=list)
    retry_attempts: int = 1
    retry_effective: bool = False
    duration_p50: float = 0.0
    duration_latest: float = 0.0
    duration_drift_ratio: float = 1.0
    duration_drift_seconds: float = 0.0
    affected_area: str = "unknown"
    examples: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "category": self.category,
            "severity": self.severity,
            "latest_status": self.latest_status,
            "failure_count": self.failure_count,
            "pass_count": self.pass_count,
            "run_count": len(self.run_ids),
            "run_ids": self.run_ids,
            "statuses": self.statuses,
            "log_category": self.log_category,
            "reasons": self.reasons,
            "retry_attempts": self.retry_attempts,
            "retry_effective": self.retry_effective,
            "duration_latest": round(self.duration_latest, 3),
            "duration_p50": round(self.duration_p50, 3),
            "duration_drift_ratio": round(self.duration_drift_ratio, 3),
            "duration_drift_seconds": round(self.duration_drift_seconds, 3),
            "affected_area": self.affected_area,
            "examples": self.examples,
        }


@dataclass
class AnalysisReport:
    runs: List[RunRecord]
    insights: List[TestInsight]
    summary: Dict[str, Any]
    config: DetectiveConfig
    generated_by: str = "ci-flake-detective"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_by": self.generated_by,
            "summary": self.summary,
            "config": self.config.to_dict(),
            "insights": [insight.to_dict() for insight in self.insights],
            "runs": [run.to_dict() for run in self.runs],
        }

    def exit_code(self) -> int:
        if self.summary.get("new_regression_count", 0) and self.config.fail_on_new_regression:
            return 2
        if self.summary.get("flaky_count", 0) and self.config.fail_on_flaky:
            return 3
        if self.summary.get("environment_count", 0) and self.config.fail_on_environment:
            return 4
        if self.summary.get("duration_drift_count", 0) and self.config.fail_on_duration_drift:
            return 5
        return 0

