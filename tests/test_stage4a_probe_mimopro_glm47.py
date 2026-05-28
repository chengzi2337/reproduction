from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "stage4a_probe_mimopro_glm47.py"

SPEC = importlib.util.spec_from_file_location("stage4a_probe_script", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
probe_script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe_script
SPEC.loader.exec_module(probe_script)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_extract_relaxed_integer_answer_supports_required_formats() -> None:
    assert probe_script.extract_relaxed_integer_answer("### 70") == "70"
    assert probe_script.extract_relaxed_integer_answer("\\boxed{70}") == "70"
    assert probe_script.extract_relaxed_integer_answer("Final answer: 70") == "70"
    assert probe_script.extract_relaxed_integer_answer("70") == "70"


def test_classify_format_result_detects_format_loss() -> None:
    probe_case = probe_script.PROBE_CASES[2]

    classified = probe_script.classify_format_result(
        probe_case=probe_case,
        content="Final answer: 42",
    )

    assert classified["protocol_category"] == "format_loss"
    assert classified["format_loss"] is True
    assert classified["extracted_answer"] == "42"


def test_build_run_summary_includes_required_flags() -> None:
    record = {
        "provider": "mimo",
        "model": "mimo-model",
        "api_base_present": True,
        "backend_family": "openai_compatible",
        "provider_string": "openai/mimo-model",
        "probe_type": "litellm",
        "probe_prompt_id": "simple_ok",
        "status": "dry_run",
        "http_status": None,
        "content_nonempty": False,
        "content_preview": "",
        "reasoning_content_present": False,
        "finish_reason": None,
        "latency_seconds": 0.0,
        "error_type": None,
        "error_message_sanitized": None,
        "error_body_sanitized": None,
        "timeout": False,
        "extracted_answer": None,
        "protocol_category": "empty_or_invalid",
        "not_performance_claim": True,
        "no_gepa_optimize_called": True,
        "not_gepa_result": True,
    }

    summary = probe_script.build_run_summary(records=[record], execute=False)

    assert summary["stage4a_provider_probe"] is True
    assert summary["not_gepa_result"] is True
    assert summary["not_performance_claim"] is True


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

    provider_configs = probe_script.build_provider_configs(args)

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

    with pytest.raises(probe_script.Stage4AProbeError, match="缺少必需 artifact"):
        probe_script.load_required_artifacts(run_dir)


def test_execute_raw_sdk_timeout_is_classified(monkeypatch, tmp_path: Path) -> None:
    class _TimeoutClient:
        def __init__(self, *args, **kwargs) -> None:
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    with_raw_response=SimpleNamespace(create=self._raise_timeout)
                )
            )

        def _raise_timeout(self, **kwargs):
            raise TimeoutError("request timed out")

    monkeypatch.setattr(probe_script, "OpenAI", _TimeoutClient)
    provider = probe_script.ProviderConfig(
        provider="mimo",
        api_base="https://example.com",
        api_key_env="MIMO_API_KEY",
        api_key="secret-value",
        model="mimo-model",
        litellm_provider_string=None,
    )

    record = probe_script.execute_raw_sdk_probe(
        provider_config=provider,
        probe_case=probe_script.PROBE_CASES[0],
        timeout_seconds=1.0,
        run_dir=tmp_path,
    )

    assert record["status"] == "timeout"
    assert record["timeout"] is True
    assert record["error_type"] == "TimeoutError"
    assert "secret-value" not in json.dumps(record, ensure_ascii=False)


def test_execute_litellm_success_uses_default_openai_provider_string(monkeypatch, tmp_path: Path) -> None:
    class _FakeLiteLLM:
        def __init__(self) -> None:
            self.last_kwargs: dict[str, object] = {}

        def completion(self, **kwargs):
            self.last_kwargs = kwargs
            return {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "### 42"},
                    }
                ]
            }

    fake_litellm = _FakeLiteLLM()
    monkeypatch.setattr(probe_script, "litellm", fake_litellm)
    provider = probe_script.ProviderConfig(
        provider="glm",
        api_base="https://example.com",
        api_key_env="GLM_API_KEY",
        api_key="glm-secret",
        model="glm-4.7",
        litellm_provider_string=None,
    )

    record = probe_script.execute_litellm_probe(
        provider_config=provider,
        probe_case=probe_script.PROBE_CASES[2],
        timeout_seconds=1.0,
        run_dir=tmp_path,
    )

    assert fake_litellm.last_kwargs["model"] == "openai/glm-4.7"
    assert record["status"] == "ok"
    assert record["protocol_exact_match"] is True


def test_dry_run_main_does_not_call_execute_branch_and_does_not_leak_api_key(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(probe_script, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("MIMO_API_KEY", "top-secret-key")
    report_path = tmp_path / "reports" / "stage4a_provider_probe_result.md"

    def fail_if_execute_called(*args, **kwargs):
        raise AssertionError("未传 --execute 时不应发起真实请求")

    monkeypatch.setattr(probe_script, "execute_probe_plan", fail_if_execute_called)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stage4a_probe_mimopro_glm47.py",
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

    probe_script.main()

    output_root = tmp_path / "outputs" / "stage4a_provider_probe"
    run_dirs = list(output_root.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    input_snapshot = json.loads(_read_text(run_dir / "input_snapshot.json"))
    probe_results = json.loads(_read_text(run_dir / "probe_results.json"))
    run_summary = json.loads(_read_text(run_dir / "run_summary.json"))
    report_text = _read_text(report_path)
    artifact_text = "\n".join(
        [
            _read_text(run_dir / "input_snapshot.json"),
            _read_text(run_dir / "probe_results.json"),
            _read_text(run_dir / "run_summary.json"),
            _read_text(run_dir / "failure_cases.json"),
            report_text,
        ]
    )

    assert input_snapshot["metadata"]["mode"] == "dry_run"
    assert input_snapshot["metadata"]["model_called"] is False
    assert input_snapshot["metadata"]["api_called"] is False
    assert input_snapshot["metadata"]["new_experiment_executed"] is False
    assert probe_results["not_gepa_result"] is True
    assert run_summary["not_performance_claim"] is True
    assert "本次未调用模型" in report_text
    assert "top-secret-key" not in artifact_text


def test_report_does_not_embed_raw_response_path() -> None:
    input_snapshot = {
        "metadata": {
            "mode": "execute",
            "model_called": True,
            "api_called": True,
            "new_experiment_executed": True,
            **probe_script.DIAGNOSTIC_FLAGS,
        }
    }
    records = [
        {
            "provider": "mimo",
            "probe_type": "raw_sdk",
            "probe_prompt_id": "simple_ok",
            "status": "ok",
            "finish_reason": "stop",
            "content_preview": "OK",
            "raw_response_path": "outputs/stage4a_provider_probe/ts/raw_responses/sample.json",
        }
    ]
    run_summary = {
        "provider_path_summaries": [
            {
                "provider": "mimo",
                "probe_type": "raw_sdk",
                "provider_reachable": True,
                "key_status": "valid",
                "model_status": "supported",
                "content_returned": True,
                "timeout_observed": False,
            }
        ],
        "raw_sdk_vs_litellm": [{"provider": "mimo", "consistent": True, "reason": "all_checked"}],
        "failure_cases": [],
    }

    report = probe_script.render_report(
        input_snapshot=input_snapshot,
        records=records,
        run_summary=run_summary,
    )

    assert "raw_responses" not in report
    assert "sample.json" not in report


def test_script_source_does_not_call_gepa_or_stage4b() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "gepa.optimize" not in source
    assert "stage4b" not in source.lower()
