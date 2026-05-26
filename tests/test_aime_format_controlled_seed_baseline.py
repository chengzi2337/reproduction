from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "eval_aime_format_controlled_seed_baseline.py"

SPEC = importlib.util.spec_from_file_location("format_controlled_seed_baseline", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
baseline_script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = baseline_script
SPEC.loader.exec_module(baseline_script)


def _write_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "experiment_name: aime_format_controlled_seed_baseline_smoke",
                "reproduction_type: method_level_reproduction",
                "provider: deepseek",
                "api_base: https://api.deepseek.com",
                "benchmark: aime",
                "task_model: dummy-model",
                "reflection_model: dummy-reflection-model",
                "max_metric_calls: 90",
                "temperature_task: 0.0",
                "temperature_reflection: 0.7",
                "seed: 42",
                "output_dir: outputs/aime_format_controlled_seed_baseline_smoke",
                "allow_model_substitution: false",
                "save_raw_pickle: false",
                "diagnostic_type: format_controlled_seed_baseline",
                "default_dry_run: true",
                "smoke_sample_count: 3",
                "batch_size: 2",
                "prompts:",
                "  original_seed_prompt: \"You are a helpful assistant. Answer the question. Put your final answer in the format '### <answer>'\"",
                "  strong_format_seed_prompt: |",
                "    Solve the problem. Your final answer must be a single line in the exact format:",
                "    ### N",
                "    Do not use \\boxed{}.",
                "    Do not use XML tags.",
                "    Do not write the final answer in any other format.",
                "  answer_first_format_prompt: |",
                "    First output the final answer in the exact format:",
                "    ### N",
                "    Then optionally provide a short explanation.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _record(sample_id: str, prompt_version: str, prediction: str, gold: str, score: float) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "prompt_version": prompt_version,
        "question": f"question {sample_id}",
        "prediction": prediction,
        "gold": gold,
        "score": score,
        "error": None,
        "attempt_count": 1,
    }


def test_summarize_records_decomposes_official_and_relaxed_scores() -> None:
    records = [
        _record("a", "strong_format_seed_prompt", "### 70", "### 70", 1.0),
        _record("b", "strong_format_seed_prompt", "\\boxed{588}", "### 588", 0.0),
        _record("c", "strong_format_seed_prompt", "### 10", "### 11", 0.0),
        _record("d", "strong_format_seed_prompt", "", "### 12", 0.0),
    ]

    summary = baseline_script.summarize_records(records)

    assert summary["official_score"] == pytest.approx(0.25)
    assert summary["relaxed_extractable_score"] == pytest.approx(0.5)
    assert summary["format_loss_count"] == 1
    assert summary["reasoning_error_count"] == 1
    assert summary["empty_or_invalid_count"] == 1


def test_load_smoke_config_requires_all_prompt_versions(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    raw_config = baseline_script.load_smoke_config(config_path)
    specs = baseline_script.load_prompt_specs(raw_config)

    assert [spec.name for spec in specs] == [
        "original_seed_prompt",
        "strong_format_seed_prompt",
        "answer_first_format_prompt",
    ]


def test_load_prompt_specs_can_select_single_prompt_version(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    raw_config = baseline_script.load_smoke_config(config_path)

    specs = baseline_script.load_prompt_specs(raw_config, ["answer_first_format_prompt"])

    assert [spec.name for spec in specs] == ["answer_first_format_prompt"]


def test_dry_run_main_writes_manifest_without_execute_dependencies(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    report_path = tmp_path / "report.md"
    monkeypatch.setattr(baseline_script, "PROJECT_ROOT", tmp_path)

    def fail_if_execute_called(*args, **kwargs):
        raise AssertionError("dry-run 不应进入 execute 分支")

    monkeypatch.setattr(baseline_script, "run_execute", fail_if_execute_called)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "eval_aime_format_controlled_seed_baseline.py",
            "--config",
            str(config_path),
            "--report-path",
            str(report_path),
        ],
    )

    baseline_script.main()

    output_root = tmp_path / "outputs" / "aime_format_controlled_seed_baseline_smoke"
    run_dirs = list(output_root.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    payload_path = run_dir / "format_controlled_seed_baseline_smoke_dry_run.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")

    assert payload["metadata"]["mode"] == "dry_run"
    assert payload["metadata"]["model_called"] is False
    assert payload["metadata"]["api_called"] is False
    assert payload["metadata"]["gepa_optimize_called"] is False
    assert payload["metadata"]["not_official_budget_baseline"] is True
    assert "本次未调用模型、未调用 API、未运行新实验" in report


def test_smoke_limit_requires_explicit_override_for_large_runs() -> None:
    with pytest.raises(baseline_script.FormatBaselineError, match="只允许小范围 smoke"):
        baseline_script.enforce_smoke_limit(150, allow_larger_smoke=False)

    baseline_script.enforce_smoke_limit(150, allow_larger_smoke=True)


def test_execute_branch_can_be_mocked_and_writes_diagnostic_metrics(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    raw_config = baseline_script.load_smoke_config(config_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    class _FakeConfig:
        task_model = "dummy-model"
        api_key = "fake-key"
        api_base = "https://api.deepseek.com"

    monkeypatch.setattr(
        "src.config.load_experiment_config",
        lambda *args, **kwargs: _FakeConfig(),
    )
    monkeypatch.setattr(
        baseline_script,
        "load_official_dataset_for_execute",
        lambda: (
            [
                {"input": "q1", "answer": "### 70", "id": "1"},
                {"input": "q2", "answer": "### 588", "id": "2"},
            ],
            "test",
            "test split",
        ),
    )

    def fake_evaluate_candidate(**kwargs):
        prompt_version = kwargs["prompt_version"]
        records = [
            _record("1", prompt_version, "### 70", "### 70", 1.0),
            _record("2", prompt_version, "\\boxed{588}", "### 588", 0.0),
        ]
        return records, {"average_score": 0.5}

    monkeypatch.setattr("src.eval_utils.evaluate_candidate", fake_evaluate_candidate)

    payload = baseline_script.run_execute(
        raw_config=raw_config,
        config_path=config_path,
        limit=2,
        batch_size=1,
        run_dir=run_dir,
        max_retries=0,
        retry_sleep_seconds=0.0,
        resume=False,
    )

    assert payload["metadata"]["mode"] == "execute"
    assert payload["metadata"]["gepa_optimize_called"] is False
    assert payload["summaries"]["original_seed_prompt"]["official_score"] == pytest.approx(0.5)
    assert payload["summaries"]["original_seed_prompt"]["relaxed_extractable_score"] == pytest.approx(1.0)
    assert payload["summaries"]["original_seed_prompt"]["format_loss_count"] == 1
    assert (run_dir / "per_example_eval.jsonl").exists()


def test_execute_resume_reuses_existing_success_records(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    raw_config = baseline_script.load_smoke_config(config_path)
    run_dir = tmp_path / "resume-run"
    run_dir.mkdir()
    existing = _record("1", "original_seed_prompt", "### 70", "### 70", 1.0)
    (run_dir / "per_example_eval.jsonl").write_text(
        json.dumps(existing, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    class _FakeConfig:
        task_model = "dummy-model"
        api_key = "fake-key"
        api_base = "https://api.deepseek.com"

    monkeypatch.setattr("src.config.load_experiment_config", lambda *args, **kwargs: _FakeConfig())
    monkeypatch.setattr(
        baseline_script,
        "load_official_dataset_for_execute",
        lambda: (
            [
                {"input": "q1", "answer": "### 70", "id": "1"},
                {"input": "q2", "answer": "### 588", "id": "2"},
            ],
            "test",
            "test split",
        ),
    )

    captured_existing: dict[str, int] = {}

    def fake_evaluate_candidate(**kwargs):
        prompt_version = kwargs["prompt_version"]
        captured_existing[prompt_version] = len(kwargs["existing_prompt_records"])
        records = list(kwargs["existing_prompt_records"])
        records.append(_record("2", prompt_version, "### 588", "### 588", 1.0))
        return records, {"average_score": 1.0}

    monkeypatch.setattr("src.eval_utils.evaluate_candidate", fake_evaluate_candidate)

    payload = baseline_script.run_execute(
        raw_config=raw_config,
        config_path=config_path,
        limit=2,
        batch_size=1,
        run_dir=run_dir,
        max_retries=0,
        retry_sleep_seconds=0.0,
        resume=True,
    )

    assert payload["execution"]["resume"] is True
    assert captured_existing["original_seed_prompt"] == 1
    assert captured_existing["strong_format_seed_prompt"] == 0


def test_script_source_does_not_directly_call_api_or_gepa_optimize() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "gepa.optimize" not in source
    assert "import openai" not in source
    assert "import litellm" not in source
