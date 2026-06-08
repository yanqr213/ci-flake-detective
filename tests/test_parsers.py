import tempfile
import unittest
from pathlib import Path

from ci_flake_detective.parsers import (
    apply_logs_to_runs,
    load_duration_records,
    load_log_fragments,
    parse_junit_file,
    parse_junit_paths,
)


EXAMPLE = Path(__file__).resolve().parents[1] / "examples"


class ParserTests(unittest.TestCase):
    def test_parse_single_junit_file(self):
        run = parse_junit_file(str(EXAMPLE / "junit" / "run-001.xml"))
        self.assertEqual("run-001", run.run_id)
        self.assertEqual(6, len(run.tests))

    def test_parse_failure_status(self):
        run = parse_junit_file(str(EXAMPLE / "junit" / "run-001.xml"))
        failed = [test for test in run.tests if test.failed]
        self.assertEqual(1, len(failed))
        self.assertEqual("failed", failed[0].status)

    def test_parse_error_status(self):
        run = parse_junit_file(str(EXAMPLE / "junit" / "run-003.xml"))
        statuses = {test.test_id: test.status for test in run.tests}
        self.assertEqual("error", statuses["tests.worker::test_background_sync"])

    def test_parse_attempt_attribute(self):
        run = parse_junit_file(str(EXAMPLE / "junit" / "run-003.xml"))
        attempts = [test.attempt for test in run.tests if test.name == "test_retryable_job"]
        self.assertEqual([1, 2], attempts)

    def test_parse_directory(self):
        runs = parse_junit_paths([str(EXAMPLE / "junit")])
        self.assertEqual(3, len(runs))

    def test_test_id_uses_classname(self):
        run = parse_junit_file(str(EXAMPLE / "junit" / "run-001.xml"))
        self.assertEqual("tests.checkout::test_pay_success", run.tests[0].test_id)

    def test_load_log_fragments(self):
        fragments = load_log_fragments([str(EXAMPLE / "logs")])
        self.assertIn("run-003", fragments)
        self.assertIn("ECONNRESET", fragments["run-003"])

    def test_apply_logs_to_runs(self):
        runs = parse_junit_paths([str(EXAMPLE / "junit" / "run-003.xml")])
        apply_logs_to_runs(runs, {"run-003": "No space left on device"})
        self.assertIn("No space left", runs[0].tests[0].output)

    def test_load_duration_csv(self):
        durations = load_duration_records([str(EXAMPLE / "durations")])
        self.assertIn("tests.search::test_index_rebuild", durations)
        self.assertEqual(4, len(durations["tests.search::test_index_rebuild"]))

    def test_load_duration_json_list(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "durations.json"
            path.write_text('[{"test_id":"a::b","duration":3.5}]', encoding="utf-8")
            durations = load_duration_records([str(path)])
        self.assertEqual([3.5], durations["a::b"])

    def test_load_duration_json_object(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "durations.json"
            path.write_text('{"tests":[{"name":"a","seconds":2}]}', encoding="utf-8")
            durations = load_duration_records([str(path)])
        self.assertEqual([2.0], durations["a"])

    def test_parse_testsuites_root(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "x.xml"
            path.write_text(
                '<testsuites><testsuite name="s"><testcase classname="c" name="n" time="0.1"/></testsuite></testsuites>',
                encoding="utf-8",
            )
            run = parse_junit_file(str(path))
        self.assertEqual("c::n", run.tests[0].test_id)

    def test_parse_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "x.xml"
            path.write_text(
                '<testsuite><testcase classname="c" name="n"><skipped message="skip"/></testcase></testsuite>',
                encoding="utf-8",
            )
            run = parse_junit_file(str(path))
        self.assertEqual("skipped", run.tests[0].status)

    def test_bad_float_defaults_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "x.xml"
            path.write_text('<testsuite><testcase classname="c" name="n" time="bad"/></testsuite>', encoding="utf-8")
            run = parse_junit_file(str(path))
        self.assertEqual(0.0, run.tests[0].duration)

    def test_suite_output_is_attached(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "x.xml"
            path.write_text(
                '<testsuite><system-out>hello</system-out><testcase classname="c" name="n"/></testsuite>',
                encoding="utf-8",
            )
            run = parse_junit_file(str(path))
        self.assertIn("hello", run.tests[0].output)


if __name__ == "__main__":
    unittest.main()

