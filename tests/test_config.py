import json
import tempfile
import unittest
from pathlib import Path

from ci_flake_detective.config import load_config
from ci_flake_detective.models import DetectiveConfig


class ConfigTests(unittest.TestCase):
    def test_defaults_are_valid(self):
        self.assertEqual([], DetectiveConfig.defaults().validate())

    def test_to_dict_contains_exit_flags(self):
        data = DetectiveConfig.defaults().to_dict()
        self.assertIn("fail_on_new_regression", data)
        self.assertIn("log_patterns", data)

    def test_from_dict_overrides_value(self):
        cfg = DetectiveConfig.from_dict({"flaky_min_runs": 4})
        self.assertEqual(4, cfg.flaky_min_runs)

    def test_from_dict_rejects_unknown_key(self):
        with self.assertRaises(ValueError):
            DetectiveConfig.from_dict({"unknown": True})

    def test_invalid_flaky_min_runs(self):
        self.assertIn("flaky_min_runs", DetectiveConfig(flaky_min_runs=1).validate()[0])

    def test_invalid_flaky_min_failures(self):
        self.assertIn("flaky_min_failures", DetectiveConfig(flaky_min_failures=0).validate()[0])

    def test_invalid_regression_prior_passes(self):
        self.assertIn("regression_min_prior_passes", DetectiveConfig(regression_min_prior_passes=0).validate()[0])

    def test_invalid_drift_factor(self):
        self.assertIn("duration_drift_factor", DetectiveConfig(duration_drift_factor=1.0).validate()[0])

    def test_invalid_drift_seconds(self):
        self.assertIn("duration_drift_seconds", DetectiveConfig(duration_drift_seconds=-1).validate()[0])

    def test_invalid_slow_seconds(self):
        self.assertIn("slow_test_seconds", DetectiveConfig(slow_test_seconds=-1).validate()[0])

    def test_invalid_retry_attempts(self):
        self.assertIn("retry_effective_min_attempts", DetectiveConfig(retry_effective_min_attempts=1).validate()[0])

    def test_invalid_log_patterns_value(self):
        cfg = DetectiveConfig(log_patterns={"x": "bad"})  # type: ignore[arg-type]
        self.assertIn("log_patterns.x", cfg.validate()[0])

    def test_load_config_default(self):
        self.assertIsInstance(load_config(), DetectiveConfig)

    def test_load_config_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text(json.dumps({"fail_on_flaky": True}), encoding="utf-8")
            cfg = load_config(str(path))
        self.assertTrue(cfg.fail_on_flaky)

    def test_load_config_rejects_list_root(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(str(path))


if __name__ == "__main__":
    unittest.main()

