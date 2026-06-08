"""Input parsers for JUnit XML, logs, and duration files."""

from __future__ import annotations

import csv
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .models import RunRecord, TestCaseRecord


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _clean_float(value: Optional[str], default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _status_from_case(case: ET.Element) -> tuple[str, str, str]:
    message = ""
    failure_type = ""
    status = "passed"
    for child in list(case):
        tag = _strip_namespace(child.tag)
        if tag in {"failure", "error", "skipped"}:
            status = "failed" if tag == "failure" else tag
            if tag == "skipped":
                status = "skipped"
            message = child.attrib.get("message", "") or (child.text or "")
            failure_type = child.attrib.get("type", tag)
            break
    return status, message.strip(), failure_type


def _case_output(case: ET.Element, suite_output: str = "") -> str:
    parts = []
    for child in list(case):
        tag = _strip_namespace(child.tag)
        if tag in {"system-out", "system-err"} and child.text:
            parts.append(child.text)
    if suite_output:
        parts.append(suite_output)
    return "\n".join(parts).strip()


def _suite_outputs(suite: ET.Element) -> str:
    parts = []
    for child in list(suite):
        tag = _strip_namespace(child.tag)
        if tag in {"system-out", "system-err"} and child.text:
            parts.append(child.text)
    return "\n".join(parts)


def _iter_suites(root: ET.Element) -> Iterable[ET.Element]:
    if _strip_namespace(root.tag) == "testsuite":
        yield root
    for elem in root.iter():
        if elem is not root and _strip_namespace(elem.tag) == "testsuite":
            yield elem


def _run_id_from_path(path: Path) -> str:
    stem = path.stem
    match = re.search(r"(run[-_ ]?\d+|\d{6,}|attempt[-_ ]?\d+)", stem, re.I)
    return match.group(1).replace(" ", "-") if match else stem


def _attempt_from_case(case: ET.Element) -> int:
    for key in ("attempt", "retry", "rerun", "flake_attempt"):
        value = case.attrib.get(key)
        if value and value.isdigit():
            return max(1, int(value))
    return 1


def parse_junit_file(path: str, run_id: Optional[str] = None) -> RunRecord:
    junit_path = Path(path)
    root = ET.parse(junit_path).getroot()
    actual_run_id = run_id or root.attrib.get("id") or _run_id_from_path(junit_path)
    record = RunRecord(run_id=actual_run_id, source=str(junit_path))

    for suite in _iter_suites(root):
        suite_name = suite.attrib.get("name", "")
        suite_file = suite.attrib.get("file", "")
        suite_output = _suite_outputs(suite)
        for case in suite:
            if _strip_namespace(case.tag) != "testcase":
                continue
            status, message, failure_type = _status_from_case(case)
            classname = case.attrib.get("classname") or suite_name
            test = TestCaseRecord(
                run_id=actual_run_id,
                name=case.attrib.get("name", ""),
                classname=classname,
                file=case.attrib.get("file") or suite_file,
                status=status,
                duration=_clean_float(case.attrib.get("time")),
                message=message,
                failure_type=failure_type,
                output=_case_output(case, suite_output),
                attempt=_attempt_from_case(case),
                source=str(junit_path),
            )
            record.tests.append(test)
    record.metadata["format"] = "junit"
    record.metadata["test_count"] = len(record.tests)
    return record


def parse_junit_paths(paths: Iterable[str]) -> List[RunRecord]:
    records = []
    for item in paths:
        path = Path(item)
        if path.is_dir():
            for xml_path in sorted(path.rglob("*.xml")):
                records.append(parse_junit_file(str(xml_path)))
        else:
            records.append(parse_junit_file(str(path)))
    return records


def load_log_fragments(paths: Iterable[str]) -> Dict[str, str]:
    fragments: Dict[str, str] = {}
    for item in paths:
        path = Path(item)
        files = sorted(path.rglob("*.log")) + sorted(path.rglob("*.txt")) if path.is_dir() else [path]
        for log_path in files:
            if not log_path.exists():
                continue
            text = log_path.read_text(encoding="utf-8", errors="replace")
            fragments[log_path.stem] = text
    return fragments


def apply_logs_to_runs(runs: List[RunRecord], fragments: Dict[str, str]) -> None:
    if not fragments:
        return
    for run in runs:
        by_run = fragments.get(run.run_id) or fragments.get(Path(run.source).stem)
        for test in run.tests:
            by_test = fragments.get(_safe_fragment_key(test.test_id))
            additions = [part for part in (by_run, by_test) if part]
            if additions:
                test.output = "\n".join([test.output] + additions).strip()


def _safe_fragment_key(test_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", test_id).strip("_")


def load_duration_records(paths: Iterable[str]) -> Dict[str, List[float]]:
    durations: Dict[str, List[float]] = {}
    for item in paths:
        path = Path(item)
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        for file_path in files:
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() == ".csv":
                _read_duration_csv(file_path, durations)
            elif file_path.suffix.lower() == ".json":
                _read_duration_json(file_path, durations)
    return durations


def _read_duration_csv(path: Path, durations: Dict[str, List[float]]) -> None:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            test_id = row.get("test_id") or row.get("name") or row.get("test")
            seconds = row.get("duration") or row.get("seconds") or row.get("time")
            if test_id:
                durations.setdefault(test_id, []).append(_clean_float(seconds))


def _read_duration_json(path: Path, durations: Dict[str, List[float]]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("tests", []) if isinstance(data, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        test_id = row.get("test_id") or row.get("name") or row.get("test")
        seconds = row.get("duration") or row.get("seconds") or row.get("time")
        if test_id:
            durations.setdefault(str(test_id), []).append(_clean_float(str(seconds)))
