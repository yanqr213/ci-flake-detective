import unittest

from ci_flake_detective.analyzer import analyze_runs
from ci_flake_detective.models import DetectiveConfig, RunRecord, TestCaseRecord
from ci_flake_detective.parsers import parse_junit_paths


def run(run_id, *tests):
    return RunRecord(run_id=run_id, source=run_id, tests=list(tests))


def case(run_id, name, status="passed", duration=1.0, message="", attempt=1, file="tests/test_x.py"):
    return TestCaseRecord(
        run_id=run_id,
        classname="pkg",
        name=name,
        status=status,
        duration=duration,
        message=message,
        attempt=attempt,
        file=file,
    )


class AnalyzerTests(unittest.TestCase):
    def test_stable_test(self):
        report = analyze_runs([run("r1", case("r1", "a")), run("r2", case("r2", "a"))])
        self.assertEqual("stable", report.insights[0].category)

    def test_flaky_test(self):
        report = analyze_runs([
            run("r1", case("r1", "a")),
            run("r2", case("r2", "a", "failed", message="AssertionError")),
            run("r3", case("r3", "a")),
        ])
        self.assertEqual("flaky", report.insights[0].category)

    def test_new_regression(self):
        report = analyze_runs([
            run("r1", case("r1", "a")),
            run("r2", case("r2", "a")),
            run("r3", case("r3", "a", "failed", message="AssertionError")),
        ])
        self.assertEqual("new_regression", report.insights[0].category)

    def test_environment_failure(self):
        cfg = DetectiveConfig(regression_min_prior_passes=5)
        report = analyze_runs([run("r1", case("r1", "a", "failed", message="ECONNRESET"))], cfg)
        self.assertEqual("environment_failure", report.insights[0].category)

    def test_timeout_failure(self):
        cfg = DetectiveConfig(regression_min_prior_passes=5)
        report = analyze_runs([run("r1", case("r1", "a", "failed", message="TimeoutError"))], cfg)
        self.assertEqual("timeout_failure", report.insights[0].category)

    def test_generic_failure(self):
        cfg = DetectiveConfig(regression_min_prior_passes=5)
        report = analyze_runs([run("r1", case("r1", "a", "failed", message="boom"))], cfg)
        self.assertEqual("failure", report.insights[0].category)

    def test_duration_drift(self):
        cfg = DetectiveConfig(duration_drift_factor=2.0, duration_drift_seconds=5)
        report = analyze_runs([
            run("r1", case("r1", "a", duration=5)),
            run("r2", case("r2", "a", duration=5)),
            run("r3", case("r3", "a", duration=12)),
        ], cfg)
        self.assertEqual("duration_drift", report.insights[0].category)

    def test_slow_test(self):
        cfg = DetectiveConfig(slow_test_seconds=2, duration_drift_seconds=100)
        report = analyze_runs([run("r1", case("r1", "a", duration=3))], cfg)
        self.assertEqual("slow", report.insights[0].category)

    def test_retry_effective(self):
        report = analyze_runs([run(
            "r1",
            case("r1", "a", "failed", message="AssertionError", attempt=1),
            case("r1", "a", "passed", attempt=2),
        )])
        self.assertTrue(report.insights[0].retry_effective)

    def test_retry_prevents_regression(self):
        report = analyze_runs([
            run("r1", case("r1", "a")),
            run("r2", case("r2", "a")),
            run("r3", case("r3", "a", "failed", attempt=1), case("r3", "a", "passed", attempt=2)),
        ])
        self.assertNotEqual("new_regression", report.insights[0].category)

    def test_summary_counts(self):
        report = analyze_runs([
            run("r1", case("r1", "a"), case("r1", "b", "failed")),
        ], DetectiveConfig(regression_min_prior_passes=5))
        self.assertEqual(1, report.summary["run_count"])
        self.assertEqual(2, report.summary["test_count"])
        self.assertEqual(1, report.summary["failed_observation_count"])

    def test_exit_code_regression(self):
        report = analyze_runs([
            run("r1", case("r1", "a")),
            run("r2", case("r2", "a")),
            run("r3", case("r3", "a", "failed")),
        ])
        self.assertEqual(2, report.exit_code())

    def test_exit_code_flaky_when_enabled(self):
        cfg = DetectiveConfig(fail_on_new_regression=False, fail_on_flaky=True)
        report = analyze_runs([
            run("r1", case("r1", "a")),
            run("r2", case("r2", "a", "failed")),
            run("r3", case("r3", "a")),
        ], cfg)
        self.assertEqual(3, report.exit_code())

    def test_exit_code_environment_when_enabled(self):
        cfg = DetectiveConfig(regression_min_prior_passes=5, fail_on_new_regression=False, fail_on_environment=True)
        report = analyze_runs([run("r1", case("r1", "a", "failed", message="ECONNRESET"))], cfg)
        self.assertEqual(4, report.exit_code())

    def test_exit_code_duration_when_enabled(self):
        cfg = DetectiveConfig(fail_on_new_regression=False, fail_on_duration_drift=True, duration_drift_seconds=1)
        report = analyze_runs([run("r1", case("r1", "a", duration=1)), run("r2", case("r2", "a", duration=5))], cfg)
        self.assertEqual(5, report.exit_code())

    def test_external_duration_history(self):
        cfg = DetectiveConfig(duration_drift_factor=2, duration_drift_seconds=5)
        report = analyze_runs([run("r1", case("r1", "a", duration=20))], cfg, {"pkg::a": [5, 5, 5]})
        self.assertEqual("duration_drift", report.insights[0].category)

    def test_affected_area_from_file(self):
        report = analyze_runs([run("r1", case("r1", "a", file="web/test_login.py"))])
        self.assertEqual("web", report.insights[0].affected_area)

    def test_examples_are_captured(self):
        report = analyze_runs([run("r1", case("r1", "a", "failed", message="AssertionError: x"))], DetectiveConfig(regression_min_prior_passes=5))
        self.assertIn("AssertionError", report.insights[0].examples[0])

    def test_report_to_dict(self):
        report = analyze_runs([run("r1", case("r1", "a"))])
        data = report.to_dict()
        self.assertIn("summary", data)
        self.assertIn("insights", data)

    def test_example_data_has_multiple_signals(self):
        example = __import__("pathlib").Path(__file__).resolve().parents[1] / "examples"
        report = analyze_runs(parse_junit_paths([str(example / "junit")]))
        categories = {insight.test_id: insight.category for insight in report.insights}
        self.assertEqual("new_regression", categories["tests.api::test_user_profile"])
        self.assertIn(categories["tests.checkout::test_coupon_edge"], {"flaky", "stable"})


if __name__ == "__main__":
    unittest.main()

