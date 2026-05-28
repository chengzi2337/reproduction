from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "stage4b_eval_fixed_prompt_aime_mimopro_glm47.py"

SPEC = importlib.util.spec_from_file_location("stage4b_fixed_prompt_script", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
stage4b_script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = stage4b_script
SPEC.loader.exec_module(stage4b_script)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_extract_relaxed_integer_answer_supports_required_formats() -> None:
    assert stage4b_script.extract_relaxed_integer_answer("### 70") == "70"
    assert stage4b_script.extract_relaxed_integer_answer("\\boxed{70}") == "70"
    assert stage4b_script.extract_relaxed_integer_answer("Final answer: 70") == "70"
    assert stage4b_script.extract_relaxed_integer_answer("70") == "70"


def test_classify_prediction_supports_contains_answer_official_semantics_and_format_loss() -> None:
    official = stage4b_script.classify_prediction(content="推导如下\n### 70\n结束", gold="### 70")
    format_loss = stage4b_script.classify_prediction(content="\\boxed{70}", gold="### 70")

    assert official["official_score"] == pytest.approx(1.0)
    assert official["relaxed_extractable_correct"] is True
    assert official["diagnosis"] == "official_correct"
    assert format_loss["official_score"] == pytest.approx(0.0)
    assert format_loss["relaxed_extractable_correct"] is True
    assert format_loss["format_loss"] is True
    assert format_loss["diagnosis"] == "format_loss"


def test_build_run_summary_includes_required_flags() -> None:
    record = {
        "provider": "mimo",
        "model": "mimo-model",
        "backend_path": "raw_sdk",
        "prompt_variant": "original_seed_prompt",
        "sample_id": "test-1",
        "official_score": 1.0,
        "relaxed_extractable_correct": True,
        "format_loss": False,
        "reasoning_error": False,
        "empty_or_invalid": False,
        "timeout": False,
        "request_completed": True,
        "latency_seconds": 1.2,
        "finish_reason": "stop",
        "status": "ok",
        "content_nonempty": True,
        "error_type": None,
        "extracted_answer": "70",
        "diagnosis": "official_correct",
        "not_gepa_result": True,
        "not_performance_claim": True,
    }

    summary = stage4b_script.build_run_summary(records=[record], execute=True)

    assert summary["stage4b_fixed_prompt_baseline"] is True
    assert summary["not_gepa_result"] is True
    assert summary["not_performance_claim"] is True
    assert summary["group_summaries"][0]["official_score"] == pytest.approx(1.0)


def test_provider_config_missing_reason_is_clear(monkeypatch) -> None:
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    args = SimpleNamespace(
        providers=("mimo",),
        mimo_api_base="",
        mimo_api_key_env="MIMO_API_KEY",
        mimo_model="",
        mimo_provider_string=None,
        glm_api_base="",
        glm_api_key_env="GLM_API_KEY",
        glm_model="",
        glm_provider_string=None,
    )

    provider_configs = stage4b_script.build_provider_configs(args)

    assert len(provider_configs) == 1
    assert provider_configs[0].missing_config_reasons() == [
        "missing api_base",
        "missing credential env: MIMO_API_KEY",
        "missing model",
    ]


def test_load_required_artifacts_fails_explicitly(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "input_snapshot.json").write_text("{}", encoding="utf-8")

    with pytest.raises(stage4b_script.Stage4BError, match="缺少必需 artifact"):
        stage4b_script.load_required_artifacts(run_dir)


def test_execute_sample_timeout_is_classified(monkeypatch, tmp_path: Path) -> None:
    def raise_timeout(**kwargs):
        raise TimeoutError("request timed out")

    monkeypatch.setattr(stage4b_script, "_execute_raw_sdk_request", raise_timeout)
    provider = stage4b_script.ProviderConfig(
        provider="mimo",
        api_base="https://example.com",
        api_key_env="MIMO_API_KEY",
        api_key="secret-value",
        model="mimo-model",
        litellm_provider_string=None,
    )
    prompt = stage4b_script.PromptSpec(
        name="original_seed_prompt",
        system_prompt=stage4b_script.PROMPTS["original_seed_prompt"],
    )

    record = stage4b_script.execute_sample(
        provider_config=provider,
        backend_path="raw_sdk",
        prompt_spec=prompt,
        sample={"input": "Q", "answer": "### 42", "id": "1"},
        split_name="test",
        sample_index=1,
        timeout_seconds=1.0,
        run_dir=tmp_path,
        max_retries=0,
        retry_sleep_seconds=0.0,
    )

    assert record["status"] == "timeout"
    assert record["timeout"] is True
    assert record["error_type"] == "TimeoutError"
    assert "secret-value" not in json.dumps(record, ensure_ascii=False)


def test_dry_run_main_does_not_call_execute_branch_and_does_not_leak_api_key(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(stage4b_script, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("MIMO_API_KEY", "top-secret-key")
    report_path = tmp_path / "reports" / "stage4b_fixed_prompt_aime_baseline_result.md"

    def fail_if_execute_called(*args, **kwargs):
        raise AssertionError("未传 --execute 时不应发起真实请求")

    monkeypatch.setattr(stage4b_script, "run_execute", fail_if_execute_called)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stage4b_eval_fixed_prompt_aime_mimopro_glm47.py",
            "--providers",
            "mimo",
            "--mimo-api-base",
            "https://mimo.example.com",
            "--mimo-model",
            "mimo-pro",
            "--report-path",
            str(report_path),
        ],
    )

    stage4b_script.main()

    output_root = tmp_path / "outputs" / "stage4b_fixed_prompt_aime_baseline"
    run_dirs = list(output_root.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    input_snapshot = json.loads(_read_text(run_dir / "input_snapshot.json"))
    fixed_prompt_results = json.loads(_read_text(run_dir / "fixed_prompt_results.json"))
    run_summary = json.loads(_read_text(run_dir / "run_summary.json"))
    report_text = _read_text(report_path)
    artifact_text = "\n".join(
        [
            _read_text(run_dir / "input_snapshot.json"),
            _read_text(run_dir / "fixed_prompt_results.json"),
            _read_text(run_dir / "run_summary.json"),
            _read_text(run_dir / "failure_cases.json"),
            report_text,
        ]
    )

    assert input_snapshot["metadata"]["mode"] == "dry_run"
    assert input_snapshot["metadata"]["model_called"] is False
    assert input_snapshot["metadata"]["api_called"] is False
    assert input_snapshot["metadata"]["new_experiment_executed"] is False
    assert fixed_prompt_results["not_gepa_result"] is True
    assert run_summary["not_performance_claim"] is True
    assert "本次未调用模型、未调用 API、未运行新实验" in report_text
    assert "top-secret-key" not in artifact_text


def test_report_does_not_embed_full_response_path() -> None:
    payload = {
        "metadata": {
            "mode": "execute",
            "model_called": True,
            "api_called": True,
            "new_experiment_executed": True,
            **stage4b_script.DIAGNOSTIC_FLAGS,
        },
        "execution": {
            "split_label": "official test split",
            "subset_selector": "first_30_items",
            "backend_path": "raw_sdk",
        },
    }
    records = [
        {
            "provider": "mimo",
            "backend_path": "raw_sdk",
            "prompt_variant": "original_seed_prompt",
            "sample_id": "test-1",
            "status": "ok",
            "finish_reason": "stop",
            "raw_response_preview": "### 42",
            "full_response_path": "outputs/stage4b_fixed_prompt_aime_baseline/ts/raw_responses/sample.json",
        }
    ]
    run_summary = {
        "group_summaries": [
            {
                "provider": "mimo",
                "backend_path": "raw_sdk",
                "prompt_variant": "original_seed_prompt",
                "completed_count": 30,
                "official_score": 0.5,
                "relaxed_extractable_score": 0.6,
                "official_minus_relaxed_gap": -0.1,
                "format_loss_count": 3,
                "reasoning_error_count": 10,
                "empty_or_invalid_count": 2,
                "timeout_count": 0,
            }
        ],
        "failure_cases": [],
    }

    report = stage4b_script.render_report(payload, records, run_summary)

    assert "raw_responses" not in report
    assert "sample.json" not in report


def test_limit_guard_blocks_over_30() -> None:
    with pytest.raises(stage4b_script.Stage4BError, match="禁止直接扩大到 150"):
        stage4b_script.enforce_stage4b_limit(150)


def test_script_source_does_not_call_gepa_or_gepa_runner() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "gepa.optimize" not in source
    assert "run_gepa_aime_experiment" not in source
