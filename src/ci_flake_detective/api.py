"""Importable API for library users."""

from __future__ import annotations

from typing import Iterable, Optional

from .analyzer import analyze_runs
from .config import load_config
from .models import AnalysisReport, DetectiveConfig, RunRecord
from .parsers import apply_logs_to_runs, load_duration_records, load_log_fragments, parse_junit_paths


def analyze(
    runs: Iterable[RunRecord],
    config: Optional[DetectiveConfig] = None,
) -> AnalysisReport:
    return analyze_runs(runs, config=config)


def analyze_paths(
    junit_paths: Iterable[str],
    log_paths: Iterable[str] = (),
    duration_paths: Iterable[str] = (),
    config: Optional[DetectiveConfig] = None,
) -> AnalysisReport:
    runs = parse_junit_paths(junit_paths)
    apply_logs_to_runs(runs, load_log_fragments(log_paths))
    durations = load_duration_records(duration_paths)
    return analyze_runs(runs, config=config, duration_history=durations)

