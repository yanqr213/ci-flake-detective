"""Public API for ci-flake-detective."""

from .api import analyze, analyze_paths, load_config
from .models import AnalysisReport, DetectiveConfig, RunRecord, TestCaseRecord, TestInsight

__all__ = [
    "AnalysisReport",
    "DetectiveConfig",
    "RunRecord",
    "TestCaseRecord",
    "TestInsight",
    "analyze",
    "analyze_paths",
    "load_config",
]

__version__ = "0.2.0"
