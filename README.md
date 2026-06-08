# ci-flake-detective

`ci-flake-detective` 是一个面向 CI 与测试治理的开源 DevTools 工具。它读取多次 CI run 导出的 JUnit XML、日志片段、测试时长 CSV/JSON，识别 flaky test、真实回归、环境型失败、超时漂移、重试有效性与影响范围，并输出 Markdown、JSON、CSV、SARIF 报告和可用于 CI gate 的退出码。

项目优先使用 Python 标准库，兼容 Python 3.9+，提供 CLI 与可导入 API。适用于 GitHub Actions、pytest/unittest/JUnit、Playwright、Node 测试等团队。

## 典型场景

- Pull Request 中区分“新代码回归”和“历史 flaky”。
- 每天聚合多次 CI run，找出最不稳定的测试和模块。
- 检测 Playwright 或端到端测试的超时漂移。
- 识别 runner、网络、依赖服务、磁盘空间等环境型失败。
- 判断 retry 是否真的把失败修复为通过。
- 输出结构化 JSON/CSV 给数据平台，输出 Markdown 给 PR 或构建摘要，输出 SARIF 给 GitHub Code Scanning。

## 安装

从源码安装：

```bash
python -m pip install -e .
```

检查 CLI：

```bash
ci-flake-detective --help
python -m ci_flake_detective --help
```

## 快速开始

```bash
ci-flake-detective analyze \
  --junit examples/junit \
  --logs examples/logs \
  --durations examples/durations \
  --output-dir reports
```

默认输出：

- `reports/ci-flake-report.md`
- `reports/ci-flake-report.json`
- `reports/ci-flake-report.csv`
- `reports/ci-flake-report.sarif`（显式传入 `--format sarif` 时生成）

默认退出码策略：

- `0`: 未触发失败门禁。
- `2`: 存在 `new_regression`，且 `fail_on_new_regression=true`。
- `3`: 存在 `flaky`，且 `fail_on_flaky=true`。
- `4`: 存在 `environment_failure`，且 `fail_on_environment=true`。
- `5`: 存在 `duration_drift`，且 `fail_on_duration_drift=true`。
- `1`: CLI 参数、配置或输入解析错误。

## CLI

### analyze

```bash
ci-flake-detective analyze \
  --junit path/to/junit.xml path/to/junit-dir \
  --logs path/to/logs \
  --durations path/to/durations.csv \
  --config config.json \
  --output-dir reports \
  --format md --format json --format csv --format sarif
```

参数说明：

- `--junit`: 必填。JUnit XML 文件或目录，目录会递归读取 `*.xml`。
- `--logs`: 可选。日志文件或目录，目录会读取 `*.log` 与 `*.txt`。
- `--durations`: 可选。测试时长历史 CSV/JSON 文件或目录。
- `--config`: 可选。JSON 配置文件。
- `--output-dir`: 可选。报告输出目录，默认 `reports`。
- `--format`: 可选。可重复传入 `md`、`json`、`csv`、`sarif`；默认输出 `md/json/csv`。
- `--strict`: 可选。临时开启 flaky、环境失败、时长漂移门禁。
- `--quiet`: 可选。减少 stdout 输出。

### validate-config

```bash
ci-flake-detective validate-config examples/config.strict.json
```

### show-default-config

```bash
ci-flake-detective show-default-config
```

## Python API

```python
from ci_flake_detective import analyze_paths, load_config

config = load_config("examples/config.strict.json")
report = analyze_paths(
    junit_paths=["examples/junit"],
    log_paths=["examples/logs"],
    duration_paths=["examples/durations"],
    config=config,
)

print(report.summary)
print(report.exit_code())
for insight in report.insights:
    print(insight.test_id, insight.category, insight.reasons)
```

也可以直接传入 `RunRecord`：

```python
from ci_flake_detective import analyze
from ci_flake_detective.models import RunRecord, TestCaseRecord

runs = [
    RunRecord("run-1", "memory", [TestCaseRecord("run-1", "test_a", "pkg", status="passed")]),
    RunRecord("run-2", "memory", [TestCaseRecord("run-2", "test_a", "pkg", status="failed")]),
]
report = analyze(runs)
```

## 输入格式

### JUnit XML

支持常见的 `testsuite` 和 `testsuites` 根节点：

```xml
<testsuite name="pytest" tests="1" failures="1">
  <testcase classname="tests.api" name="test_user_profile" file="api/test_user.py" time="0.8">
    <failure message="AssertionError: expected 200 actual 500" />
  </testcase>
</testsuite>
```

字段映射：

- `classname + name` 组成 `test_id`，格式为 `classname::name`。
- `time` 解析为秒。
- `failure` 归类为 `failed`。
- `error` 归类为 `error`。
- `skipped` 归类为 `skipped`。
- `system-out` 与 `system-err` 会作为日志上下文。
- `attempt`、`retry`、`rerun`、`flake_attempt` 会作为重试序号。

### 日志片段

日志文件支持 `.log` 和 `.txt`。文件名与 run id 或安全化后的 test id 匹配时会合并到对应测试上下文。即使没有精确匹配，也可以依靠 JUnit 内部的 failure message 和 system output 分类。

默认日志分类：

- `environment`: 网络、DNS、502/503、rate limit、磁盘空间、runner 通信失败等。
- `timeout`: timeout、timed out、TimeoutError、deadline exceeded 等。
- `assertion`: AssertionError、expected、actual、Diff 等。
- `dependency`: ModuleNotFoundError、ImportError、npm ERR、包缺失等。

### 测试时长 CSV

```csv
test_id,duration
tests.search::test_index_rebuild,8.1
tests.search::test_index_rebuild,22.0
```

支持列名：

- 测试 ID: `test_id`、`name`、`test`
- 秒数: `duration`、`seconds`、`time`

### 测试时长 JSON

列表格式：

```json
[
  {"test_id": "tests.search::test_index_rebuild", "duration": 8.1}
]
```

对象格式：

```json
{
  "tests": [
    {"test_id": "tests.search::test_index_rebuild", "seconds": 8.1}
  ]
}
```

## 判定规则

默认规则偏保守，避免把真实回归误判为 flaky。

- `new_regression`: 最新观测失败，且此前至少 `regression_min_prior_passes` 次通过，并且没有有效 retry。
- `flaky`: 观测 run 数不少于 `flaky_min_runs`，失败次数不少于 `flaky_min_failures`，且历史中同时出现通过和失败。
- `environment_failure`: 最新失败，日志命中环境类模式。
- `timeout_failure`: 最新失败，日志命中超时模式。
- `failure`: 最新失败，但不满足更具体分类。
- `duration_drift`: 最新时长同时超过 `duration_drift_factor` 倍历史 p50，且绝对增长不少于 `duration_drift_seconds` 秒。
- `slow`: 最新时长超过 `slow_test_seconds`。
- `stable`: 未发现不稳定信号。
- `retry_effective`: 同一 run 中较早 attempt 失败，较晚 attempt 通过。

规则优先级：

1. 新回归
2. Flaky
3. 环境失败
4. 超时失败
5. 普通失败
6. 时长漂移
7. 慢测试
8. 稳定

## 配置

查看默认配置：

```bash
ci-flake-detective show-default-config
```

配置文件必须是 JSON 对象。示例见 `examples/config.strict.json`。

常用字段：

- `flaky_min_runs`
- `flaky_min_failures`
- `flaky_requires_pass_and_fail`
- `regression_min_prior_passes`
- `duration_drift_factor`
- `duration_drift_seconds`
- `slow_test_seconds`
- `retry_effective_min_attempts`
- `fail_on_new_regression`
- `fail_on_flaky`
- `fail_on_environment`
- `fail_on_duration_drift`
- `log_patterns`

## 报告字段

JSON 与 CSV 中每条 insight 包含：

- `test_id`: 稳定测试标识。
- `category`: 分类结果。
- `severity`: `critical`、`high`、`medium`、`low`、`info`。
- `latest_status`: 最新状态。
- `failure_count` / `pass_count` / `run_count`: 历史统计。
- `run_ids` / `statuses`: 观测序列。
- `log_category`: 日志分类。
- `reasons`: 判定依据。
- `retry_attempts`: 最大重试次数。
- `retry_effective`: retry 是否把失败转为通过。
- `duration_latest`: 最新时长。
- `duration_p50`: 历史基线。
- `duration_drift_ratio`: 最新时长与基线比值。
- `duration_drift_seconds`: 最新时长与基线差值。
- `affected_area`: 从文件路径或 classname 推断的影响范围。
- `examples`: 失败消息摘录。

SARIF 输出会把非 `stable` insight 映射为 Code Scanning result：`new_regression` 是 `error`，`flaky`、`environment_failure`、`timeout_failure` 是 `warning`，`duration_drift`、`slow` 等是 `note`。这适合在 GitHub 的安全/质量视图里集中查看测试治理问题。

## GitHub Actions 集成

基础用法：

```yaml
name: test

on:
  pull_request:
  push:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install -e .
      - run: pytest --junitxml=artifacts/junit.xml
      - run: ci-flake-detective analyze --junit artifacts --output-dir reports --format md --format json --format sarif
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: ci-flake-report
          path: reports
```

上传 SARIF 到 GitHub Code Scanning：

```yaml
permissions:
  contents: read
  security-events: write

steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with:
      python-version: "3.12"
  - run: python -m pip install git+https://github.com/yanqr213/ci-flake-detective.git
  - run: ci-flake-detective analyze --junit artifacts --output-dir reports --format sarif
  - uses: github/codeql-action/upload-sarif@v3
    if: always()
    with:
      sarif_file: reports/ci-flake-report.sarif
```

如果只想在新回归时失败，使用默认配置即可。如果希望 flaky、环境失败、时长漂移也让 CI 失败：

```bash
ci-flake-detective analyze --junit artifacts --strict
```

## 限制

- 当前版本不调用 GitHub API，不直接拉取 Actions 历史；请先导出 JUnit XML、日志、时长文件。
- JUnit XML 的 retry 表达在不同框架中差异较大，本工具优先读取常见 attempt 属性。
- 日志分类是确定性关键词匹配，不使用机器学习。
- 时长漂移依赖历史数据质量；run 数过少时可能只适合作为提示。
- 影响范围通过 `file` 或 `classname` 粗略推断，不替代代码覆盖率分析。

## 开发指南

本项目无运行时第三方依赖。

```bash
python -m pip install -e .
python -m unittest discover -s tests
ci-flake-detective analyze --junit examples/junit --logs examples/logs --durations examples/durations --output-dir reports
```

项目结构：

- `src/ci_flake_detective/models.py`: 数据模型和默认配置。
- `src/ci_flake_detective/parsers.py`: JUnit、日志、时长输入解析。
- `src/ci_flake_detective/analyzer.py`: 历史聚合与判定规则。
- `src/ci_flake_detective/reporters.py`: Markdown、JSON、CSV、SARIF 输出。
- `src/ci_flake_detective/cli.py`: 命令行入口。
- `tests/`: unittest 测试套件。
- `examples/`: 可直接运行的样例数据。
- `.github/workflows/ci.yml`: GitHub Actions CI。

## English

`ci-flake-detective` is an open-source DevTools project for CI and test governance. It reads JUnit XML files, log fragments, and duration history exported from repeated CI runs, then detects flaky tests, new regressions, environment failures, timeout failures, duration drift, retry effectiveness, and affected areas. It writes Markdown, JSON, CSV, and SARIF reports and returns CI-friendly exit codes.

The project prefers the Python standard library, supports Python 3.9+, and provides both a CLI and an importable API.

### Use Cases

- Separate real pull-request regressions from known flaky tests.
- Aggregate repeated CI runs and rank unstable tests.
- Detect Playwright or end-to-end timeout drift.
- Classify network, runner, service, dependency, and disk-related failures.
- Measure whether retries actually turn failures into passes.
- Send JSON/CSV to data systems, Markdown to build summaries, and SARIF to GitHub Code Scanning.

### Installation

```bash
python -m pip install -e .
```

### Quick Start

```bash
ci-flake-detective analyze \
  --junit examples/junit \
  --logs examples/logs \
  --durations examples/durations \
  --output-dir reports
```

Outputs:

- `reports/ci-flake-report.md`
- `reports/ci-flake-report.json`
- `reports/ci-flake-report.csv`
- `reports/ci-flake-report.sarif` when `--format sarif` is requested

### CLI

```bash
ci-flake-detective analyze --junit path/to/junit.xml path/to/junit-dir
ci-flake-detective validate-config examples/config.strict.json
ci-flake-detective show-default-config
```

Analyze options:

- `--junit`: Required. JUnit XML files or directories.
- `--logs`: Optional log files or directories.
- `--durations`: Optional CSV/JSON duration history files or directories.
- `--config`: Optional JSON config file.
- `--output-dir`: Report output directory, default `reports`.
- `--format`: Repeatable output format: `md`, `json`, `csv`, `sarif`.
- `--strict`: Fail CI on flaky, environment, and duration-drift findings too.
- `--quiet`: Suppress summary output.

### API

```python
from ci_flake_detective import analyze_paths, load_config

config = load_config("examples/config.strict.json")
report = analyze_paths(
    junit_paths=["examples/junit"],
    log_paths=["examples/logs"],
    duration_paths=["examples/durations"],
    config=config,
)

print(report.summary)
print(report.exit_code())
```

### Input Formats

JUnit XML supports `testsuite` and `testsuites` roots. `classname` plus `name` becomes `test_id`. `failure`, `error`, and `skipped` map to test status. `system-out` and `system-err` are used as log context. Retry attempt attributes are read from `attempt`, `retry`, `rerun`, or `flake_attempt`.

Duration CSV accepts `test_id`, `name`, or `test` as the test key and `duration`, `seconds`, or `time` as seconds. Duration JSON may be a list of objects or an object containing a `tests` list.

### Rules

- `new_regression`: latest observation failed after enough prior passes and no effective retry.
- `flaky`: enough runs contain both passes and failures.
- `environment_failure`: latest failure matches environment log patterns.
- `timeout_failure`: latest failure matches timeout patterns.
- `failure`: latest failure without a more specific category.
- `duration_drift`: latest duration exceeds both ratio and absolute thresholds.
- `slow`: latest duration exceeds the slow-test threshold.
- `stable`: no instability signal detected.
- `retry_effective`: an earlier failed attempt later passed in the same run.

### Report Fields

Each insight includes `test_id`, `category`, `severity`, `latest_status`, failure/pass/run counts, `log_category`, `reasons`, retry data, duration baseline and drift values, `affected_area`, and example failure snippets.

SARIF maps non-stable insights into Code Scanning results, with new regressions as `error`, flaky/environment/timeout findings as `warning`, and duration/slow-test findings as `note`.

### CI Integration

```yaml
- run: pytest --junitxml=artifacts/junit.xml
- run: ci-flake-detective analyze --junit artifacts --output-dir reports --format md --format json --format sarif
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: ci-flake-report
    path: reports
```

Exit codes:

- `0`: no configured gate failed.
- `1`: CLI/config/input error.
- `2`: new regression gate failed.
- `3`: flaky gate failed.
- `4`: environment gate failed.
- `5`: duration drift gate failed.

### Limitations

- The tool does not call the GitHub API or fetch Actions history directly.
- Retry metadata differs across frameworks; this version reads common attempt attributes.
- Log classification is deterministic keyword matching, not machine learning.
- Duration drift quality depends on historical duration data.
- Affected area inference is path/classname-based and is not a replacement for coverage analysis.

### Development

```bash
python -m pip install -e .
python -m unittest discover -s tests
ci-flake-detective analyze --junit examples/junit --logs examples/logs --durations examples/durations --output-dir reports
```

The code lives under `src/ci_flake_detective`, tests under `tests`, examples under `examples`, and GitHub Actions CI under `.github/workflows/ci.yml`.
