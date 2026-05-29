from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "stage4b_mimo_timeout_decomposition_diagnostic.py"

SPEC = importlib.util.spec_from_file_location("stage4b_mimo_timeout_script", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
mimo_timeout_script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mimo_timeout_script
SPEC.loader.exec_module(mimo_timeout_script)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_load_timeout_values_defaults_and_rejects_invalid() -> None:
    assert mimo_timeout_script.load_timeout_values([60, 120, 240]) == [60, 120, 240]
    with pytest.raises(
        mimo_timeout_script.Stage4BMiMoTimeoutDiagnosticError, match="每个值都必须大于 0"
    ):
        mimo_timeout_script.load_timeout_values([60, 0])


def test_build_provider_config_missing_reason_is_clear(monkeypatch) -> None:
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.delenv("MIMO_API_BASE", raising=False)
    monkeypatch.delenv("MIMO_MODEL", raising=False)
    args = SimpleNamespace(
        api_key_env="MIMO_API_KEY",
        api_base_env="MIMO_API_BASE",
        model_env="MIMO_MODEL",
    )

    provider = mimo_timeout_script.build_provider_config(args)

    assert provider.provider == "mimo"
    assert provider.missing_config_reasons() == [
        "missing api_base",
        "missing credential env: MIMO_API_KEY",
        "missing model",
    ]


def test_build_dry_run_records_sets_schema_flags_and_does_not_call_model() -> None:
    provider = mimo_timeout_script.BASE.ProviderConfig(
        provider="mimo",
        api_base="",
        api_key_env="MIMO_API_KEY",
        api_key="",
        model="",
        litellm_provider_string=None,
    )
    layer_spec = mimo_timeout_script.PROMPT_LAYERS["l3_original_seed"]
    records = mimo_timeout_script.build_dry_run_records(
        provider_config=provider,
        backend_path="raw_sdk",
        modes=["non_streaming"],
        layer_specs=[layer_spec],
        sample_entries=[{"sample_id": "test-1", "gold": "### 42", "question": "Q"}],
        timeout_values=[60],
        sleep_between_requests=60.0,
        max_retries=0,
    )

    assert len(records) == 1
    record = records[0]
    assert record["status"] == "dry_run"
    assert record["diagnostic_only"] is True
    assert record["not_gepa_result"] is True
    assert record["not_performance_claim"] is True
    assert record["error_type"] == "ConfigPreview"


def test_summarize_health_checks_counts_ok_and_error() -> None:
    summaries = mimo_timeout_script.summarize_health_checks(
        [
            {
                "mode": "non_streaming",
                "timeout_setting": 60,
                "phase": "pre",
                "content_exact_ok": True,
                "latency_seconds": 1.0,
                "error_type": None,
            },
            {
                "mode": "non_streaming",
                "timeout_setting": 60,
                "phase": "post",
                "content_exact_ok": False,
                "latency_seconds": 2.0,
                "error_type": "TimeoutError",
            },
        ]
    )

    assert summaries == [
        {
            "mode": "non_streaming",
            "timeout_setting": 60,
            "check_count": 2,
            "ok_count": 1,
            "error_count": 1,
            "avg_latency_seconds": 1.5,
            "phases_seen": ["post", "pre"],
            **mimo_timeout_script.DIAGNOSTIC_FLAGS,
        }
    ]


def test_execute_single_case_timeout_is_classified_and_sanitized(monkeypatch, tmp_path: Path) -> None:
    class _RawResponseAPI:
        def create(self, **kwargs):
            raise TimeoutError("request timed out for secret-key")

    class _ChatCompletions:
        def __init__(self) -> None:
            self.with_raw_response = _RawResponseAPI()

    class _Chat:
        def __init__(self) -> None:
            self.completions = _ChatCompletions()

    class _FakeClient:
        def __init__(self, **kwargs) -> None:
            self.chat = _Chat()

    monkeypatch.setattr(mimo_timeout_script, "OpenAI", _FakeClient)
    provider = mimo_timeout_script.BASE.ProviderConfig(
        provider="mimo",
        api_base="https://example.com",
        api_key_env="MIMO_API_KEY",
        api_key="secret-key",
        model="mimo-model",
        litellm_provider_string=None,
    )

    record = mimo_timeout_script.execute_single_case(
        provider_config=provider,
        backend_path="raw_sdk",
        mode="non_streaming",
        layer_spec=mimo_timeout_script.PROMPT_LAYERS["l3_original_seed"],
        sample_entry={"sample_id": "test-1", "question": "Q", "gold": "### 42"},
        timeout_setting=60,
        sleep_between_requests=60.0,
        max_retries=0,
        run_dir=tmp_path,
    )

    assert record["status"] == "timeout"
    assert record["timeout"] is True
    assert record["diagnosis"] == "timeout"
    assert "secret-key" not in json.dumps(record, ensure_ascii=False)


def test_streaming_first_token_latency_statistics_are_recorded() -> None:
    summaries = mimo_timeout_script.summarize_records(
        [
            {
                "provider": "mimo",
                "backend_path": "raw_sdk",
                "mode": "streaming",
                "prompt_layer": "l3_original_seed",
                "timeout_setting": 60,
                "completed": True,
                "timeout": False,
                "rate_limit_observed": False,
                "provider_error": False,
                "official_score": 1.0,
                "relaxed_extractable_correct": True,
                "format_loss": False,
                "reasoning_error": False,
                "empty_or_invalid": False,
                "latency_seconds": 10.0,
                "time_to_first_token_seconds": 1.0,
                "finish_reason": "stop",
            },
            {
                "provider": "mimo",
                "backend_path": "raw_sdk",
                "mode": "streaming",
                "prompt_layer": "l3_original_seed",
                "timeout_setting": 60,
                "completed": True,
                "timeout": False,
                "rate_limit_observed": False,
                "provider_error": False,
                "official_score": 0.0,
                "relaxed_extractable_correct": False,
                "format_loss": False,
                "reasoning_error": True,
                "empty_or_invalid": False,
                "latency_seconds": 14.0,
                "time_to_first_token_seconds": 3.0,
                "finish_reason": "stop",
            },
        ]
    )

    assert summaries[0]["avg_time_to_first_token_seconds"] == pytest.approx(2.0)
    assert summaries[0]["max_time_to_first_token_seconds"] == pytest.approx(3.0)
    assert summaries[0]["avg_latency_seconds"] == pytest.approx(12.0)


def test_streaming_reasoning_only_output_does_not_mark_content_nonempty(monkeypatch, tmp_path: Path) -> None:
    class _Chunk:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

    class _Stream:
        def __init__(self) -> None:
            self.response = SimpleNamespace(status_code=200)
            self._items = [
                _Chunk({"choices": [{"delta": {"reasoning_content": "思考"}, "finish_reason": None}]}),
                _Chunk({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
            ]

        def __iter__(self):
            return iter(self._items)

        def close(self) -> None:
            return None

    class _ChatCompletions:
        def create(self, **kwargs):
            return _Stream()

    class _Chat:
        def __init__(self) -> None:
            self.completions = _ChatCompletions()

    class _FakeClient:
        def __init__(self, **kwargs) -> None:
            self.chat = _Chat()

    monkeypatch.setattr(mimo_timeout_script, "OpenAI", _FakeClient)
    provider = mimo_timeout_script.BASE.ProviderConfig(
        provider="mimo",
        api_base="https://example.com",
        api_key_env="MIMO_API_KEY",
        api_key="secret-key",
        model="mimo-model",
        litellm_provider_string=None,
    )

    record = mimo_timeout_script.execute_single_case(
        provider_config=provider,
        backend_path="raw_sdk",
        mode="streaming",
        layer_spec=mimo_timeout_script.PROMPT_LAYERS["l3_original_seed"],
        sample_entry={"sample_id": "test-1", "question": "Q", "gold": "### 42"},
        timeout_setting=60,
        sleep_between_requests=60.0,
        max_retries=0,
        run_dir=tmp_path,
    )

    assert record["reasoning_content_present"] is True
    assert record["content_nonempty"] is False
    assert record["reasoning_only_output"] is True
    assert record["empty_or_invalid"] is True


def test_relaxed_extractor_supports_required_formats() -> None:
    extractor = mimo_timeout_script.BASE.extract_relaxed_integer_answer
    assert extractor("### 70") == "70"
    assert extractor("\\boxed{70}") == "70"
    assert extractor("Final answer: 70") == "70"
    assert extractor("70") == "70"


def test_format_loss_classification_is_correct() -> None:
    result = mimo_timeout_script.classify_prediction(content="\\boxed{70}", gold="### 70")

    assert result["official_score"] == pytest.approx(0.0)
    assert result["relaxed_extractable_correct"] is True
    assert result["format_loss"] is True
    assert result["reasoning_error"] is False
    assert result["empty_or_invalid"] is False


def test_dry_run_main_does_not_call_execute_and_does_not_leak_api_key(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(mimo_timeout_script, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("MIMO_API_KEY", "top-secret-mimo-key")
    monkeypatch.setenv("MIMO_API_BASE", "https://mimo.example.com")
    monkeypatch.setenv("MIMO_MODEL", "mimo-pro")

    def fake_build_selected_samples(sample_ids: list[str]):
        return (
            [{"sample_id": "test-1", "question": "Q", "gold": "### 42", "sample": {}, "sample_index": 1}],
            {"split": "test", "split_label": "official test split", "selected_sample_ids": ["test-1"], "selected_count": 1},
        )

    def fail_if_execute_called(*args, **kwargs):
        raise AssertionError("未传 --execute 时不应发起真实请求")

    monkeypatch.setattr(mimo_timeout_script, "build_selected_samples", fake_build_selected_samples)
    monkeypatch.setattr(mimo_timeout_script, "execute_timeout_plan", fail_if_execute_called)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stage4b_mimo_timeout_decomposition_diagnostic.py",
            "--report-path",
            "reports/stage4b_mimo_timeout_decomposition_diagnostic_result.md",
        ],
    )

    mimo_timeout_script.main()

    output_root = tmp_path / "outputs" / "stage4b_mimo_timeout_decomposition_diagnostic"
    run_dirs = list(output_root.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    input_snapshot = json.loads(_read_text(run_dir / "input_snapshot.json"))
    result_payload = json.loads(_read_text(run_dir / "timeout_decomposition_results.json"))
    run_summary = json.loads(_read_text(run_dir / "run_summary.json"))
    report_text = _read_text(tmp_path / "reports" / "stage4b_mimo_timeout_decomposition_diagnostic_result.md")
    artifact_text = "\n".join(
        [
            _read_text(run_dir / "input_snapshot.json"),
            _read_text(run_dir / "timeout_decomposition_results.json"),
            _read_text(run_dir / "run_summary.json"),
            _read_text(run_dir / "failure_cases.json"),
            report_text,
        ]
    )

    assert input_snapshot["metadata"]["mode"] == "dry_run"
    assert input_snapshot["metadata"]["model_called"] is False
    assert input_snapshot["metadata"]["api_called"] is False
    assert result_payload["diagnostic_only"] is True
    assert result_payload["not_gepa_result"] is True
    assert run_summary["not_performance_claim"] is True
    assert "未调用模型" in report_text
    assert "top-secret-mimo-key" not in artifact_text


def test_script_source_does_not_call_gepa_or_glm() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "gepa.optimize" not in source
    assert "run_gepa_aime_experiment" not in source
    assert '"glm"' not in source
