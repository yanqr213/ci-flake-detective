import json
import tempfile
import unittest
from pathlib import Path

from ci_flake_detective.cli import main
from ci_flake_detective.reporters import render_markdown, write_reports
from ci_flake_detective.analyzer import analyze_runs
from ci_flake_detective.models import DetectiveConfig, RunRecord, TestCaseRecord


EXAMPLE = Path(__file__).resolve().parents[1] / "examples"


def sample_report():
    return analyze_runs(
        [
            RunRecord("r1", "r1", [TestCaseRecord("r1", "a", "pkg", status="passed")]),
            RunRecord("r2", "r2", [TestCaseRecord("r2", "a", "pkg", status="failed", message="AssertionError")]),
            RunRecord("r3", "r3", [TestCaseRecord("r3", "a", "pkg", status="passed")]),
        ],
        DetectiveConfig(fail_on_new_regression=False),
    )


class ReporterCliTests(unittest.TestCase):
    def test_render_markdown_contains_summary(self):
        md = render_markdown(sample_report())
        self.assertIn("## Summary", md)
        self.assertIn("Flaky tests", md)

    def test_write_reports_all_formats(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = write_reports(sample_report(), temp, ["md", "json", "csv"])
            names = {path.name for path in paths}
            self.assertEqual({"ci-flake-report.md", "ci-flake-report.json", "ci-flake-report.csv"}, names)

    def test_json_report_is_valid(self):
        with tempfile.TemporaryDirectory() as temp:
            write_reports(sample_report(), temp, ["json"])
            data = json.loads((Path(temp) / "ci-flake-report.json").read_text(encoding="utf-8"))
        self.assertIn("summary", data)

    def test_csv_report_has_header(self):
        with tempfile.TemporaryDirectory() as temp:
            write_reports(sample_report(), temp, ["csv"])
            text = (Path(temp) / "ci-flake-report.csv").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("test_id,category"))

    def test_cli_show_default_config(self):
        self.assertEqual(0, main(["show-default-config"]))

    def test_cli_validate_config(self):
        self.assertEqual(0, main(["validate-config", str(EXAMPLE / "config.strict.json")]))

    def test_cli_analyze_writes_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            code = main([
                "analyze",
                "--junit",
                str(EXAMPLE / "junit"),
                "--logs",
                str(EXAMPLE / "logs"),
                "--durations",
                str(EXAMPLE / "durations"),
                "--output-dir",
                temp,
                "--quiet",
            ])
            self.assertEqual(2, code)
            self.assertTrue((Path(temp) / "ci-flake-report.md").exists())

    def test_cli_analyze_single_format(self):
        with tempfile.TemporaryDirectory() as temp:
            main(["analyze", "--junit", str(EXAMPLE / "junit" / "run-001.xml"), "--output-dir", temp, "--format", "json", "--quiet"])
            self.assertTrue((Path(temp) / "ci-flake-report.json").exists())
            self.assertFalse((Path(temp) / "ci-flake-report.md").exists())

    def test_cli_strict_uses_flaky_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            code = main([
                "analyze",
                "--junit",
                str(EXAMPLE / "junit" / "run-001.xml"),
                str(EXAMPLE / "junit" / "run-002.xml"),
                "--output-dir",
                temp,
                "--strict",
                "--quiet",
            ])
        self.assertIn(code, {0, 3})

    def test_cli_bad_config_returns_one(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.json"
            path.write_text('{"nope": true}', encoding="utf-8")
            self.assertEqual(1, main(["validate-config", str(path)]))


if __name__ == "__main__":
    unittest.main()

