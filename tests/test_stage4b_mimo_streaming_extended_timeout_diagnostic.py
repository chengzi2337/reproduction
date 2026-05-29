from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "stage4b_mimo_streaming_extended_timeout_diagnostic.py"

SPEC = importlib.util.spec_from_file_location("stage4b_mimo_streaming_extended_timeout_script", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
streaming_script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = streaming_script
SPEC.loader.exec_module(streaming_script)


def test_build_provider_config_missing_reason_is_clear(monkeypatch) -> None:
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.delenv("MIMO_API_BASE", raising=False)
    monkeypatch.delenv("MIMO_MODEL", raising=False)
    args = SimpleNamespace(
        api_key_env="MIMO_API_KEY",
        api_base_env="MIMO_API_BASE",
        model_env="MIMO_MODEL",
    )

    provider = streaming_script.build_provider_config(args)

    assert provider.provider == "mimo"
    assert provider.missing_config_reasons() == [
        "missing api_base",
        "missing credential env: MIMO_API_KEY",
        "missing model",
    ]


def test_build_dry_run_records_sets_schema_flags_and_does_not_call_model() -> None:
    provider = streaming_script.BASE.ProviderConfig(
        provider="mimo",
        api_base="",
        api_key_env="MIMO_API_KEY",
        api_key="",
        model="",
        litellm_provider_string=None,
    )
    prompt_variant = streaming_script.PROMPT_VARIANTS["l4_strong_format"]
    records = streaming_script.build_dry_run_records(
        provider_config=provider,
        backend_path="raw_sdk",
        prompt_variant=prompt_variant,
        sample_entries=[{"sample_id": "test-1", "gold": "### 42", "question": "Q"}],
        application_wall_clock_timeout_seconds=600.0,
        sdk_timeout_seconds=600.0,
        sleep_between_requests=60.0,
        max_retries=0,
    )

    assert len(records) == 1
    record = records[0]
    assert record["status"] == "dry_run"
    assert record["diagnostic_only"] is True
    assert record["not_gepa_result"] is True
    assert record["not_performance_claim"] is True
    assert record["streaming_path_only"] is True
    assert record["error_type"] == "ConfigPreview"


def test_summarize_health_checks_counts_ok_and_error() -> None:
    summary = streaming_script.summarize_health_checks(
        [
            {
                "phase": "pre",
                "content_exact_ok": True,
                "latency_seconds": 1.0,
                "error_type": None,
            },
            {
                "phase": "post",
                "content_exact_ok": False,
                "latency_seconds": 2.0,
                "error_type": "TimeoutError",
            },
        ]
    )

    assert summary["check_count"] == 2
    assert summary["ok_count"] == 1
    assert summary["error_count"] == 1
    assert summary["avg_latency_seconds"] == 1.5
    assert summary["phases_seen"] == ["post", "pre"]
    assert summary["diagnostic_only"] is True


def test_application_wall_clock_timeout_before_first_token_is_classified_and_closes_stream(
    monkeypatch, tmp_path: Path
) -> None:
    class _SlowStream:
        def __init__(self) -> None:
            self.response = SimpleNamespace(status_code=200)
            self.close_calls = 0

        def __iter__(self):
            time.sleep(0.1)
            if False:
                yield None

        def close(self) -> None:
            self.close_calls += 1

    stream_holder: dict[str, _SlowStream] = {}

    class _ChatCompletions:
        def create(self, **kwargs):
            stream_holder["stream"] = _SlowStream()
            return stream_holder["stream"]

    class _Chat:
        def __init__(self) -> None:
            self.completions = _ChatCompletions()

    class _FakeClient:
        def __init__(self, **kwargs) -> None:
            self.chat = _Chat()

    monkeypatch.setattr(streaming_script, "OpenAI", _FakeClient)
    provider = streaming_script.BASE.ProviderConfig(
        provider="mimo",
        api_base="https://example.com",
        api_key_env="MIMO_API_KEY",
        api_key="secret-key",
        model="mimo-model",
        litellm_provider_string=None,
    )

    record = streaming_script.execute_single_case(
        provider_config=provider,
        backend_path="raw_sdk",
        prompt_variant=streaming_script.PROMPT_VARIANTS["l4_strong_format"],
        sample_entry={"sample_id": "test-1", "question": "Q", "gold": "### 42"},
        application_wall_clock_timeout_seconds=0.01,
        sdk_timeout_seconds=600.0,
        sleep_between_requests=60.0,
        max_retries=0,
        run_dir=tmp_path,
    )

    assert record["status"] == "timeout"
    assert record["timeout"] is True
    assert record["error_type"] == "ApplicationWallClockTimeout"
    assert record["timeout_enforced_by"] == "application_wall_clock"
    assert record["first_token_observed"] is False
    assert record["partial_content_nonempty"] is False
    assert record["content_nonempty"] is False
    assert record["stream_close_attempted"] is True
    assert stream_holder["stream"].close_calls >= 1


def test_application_wall_clock_timeout_mid_generation_keeps_partial_content(monkeypatch, tmp_path: Path) -> None:
    class _Chunk:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

    class _SlowMidStream:
        def __init__(self) -> None:
            self.response = SimpleNamespace(status_code=200)
            self.close_calls = 0
            self._items = [
                _Chunk({"choices": [{"delta": {"content": "### "}, "finish_reason": None}]}),
                _Chunk({"choices": [{"delta": {"content": "70"}, "finish_reason": None}]}),
            ]

        def __iter__(self):
            yield self._items[0]
            time.sleep(0.1)
            yield self._items[1]

        def close(self) -> None:
            self.close_calls += 1

    stream_holder: dict[str, _SlowMidStream] = {}

    class _ChatCompletions:
        def create(self, **kwargs):
            stream_holder["stream"] = _SlowMidStream()
            return stream_holder["stream"]

    class _Chat:
        def __init__(self) -> None:
            self.completions = _ChatCompletions()

    class _FakeClient:
        def __init__(self, **kwargs) -> None:
            self.chat = _Chat()

    monkeypatch.setattr(streaming_script, "OpenAI", _FakeClient)
    provider = streaming_script.BASE.ProviderConfig(
        provider="mimo",
        api_base="https://example.com",
        api_key_env="MIMO_API_KEY",
        api_key="secret-key",
        model="mimo-model",
        litellm_provider_string=None,
    )

    record = streaming_script.execute_single_case(
        provider_config=provider,
        backend_path="raw_sdk",
        prompt_variant=streaming_script.PROMPT_VARIANTS["l4_strong_format"],
        sample_entry={"sample_id": "test-1", "question": "Q", "gold": "### 70"},
        application_wall_clock_timeout_seconds=0.05,
        sdk_timeout_seconds=600.0,
        sleep_between_requests=60.0,
        max_retries=0,
        run_dir=tmp_path,
    )

    assert record["status"] == "timeout"
    assert record["timeout"] is True
    assert record["first_token_observed"] is True
    assert record["partial_content_nonempty"] is True
    assert record["content_nonempty"] is True
    assert record["relaxed_extractable_correct"] is False
    assert record["stream_close_attempted"] is True
    assert stream_holder["stream"].close_calls >= 1


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

    monkeypatch.setattr(streaming_script, "OpenAI", _FakeClient)
    provider = streaming_script.BASE.ProviderConfig(
        provider="mimo",
        api_base="https://example.com",
        api_key_env="MIMO_API_KEY",
        api_key="secret-key",
        model="mimo-model",
        litellm_provider_string=None,
    )

    record = streaming_script.execute_single_case(
        provider_config=provider,
        backend_path="raw_sdk",
        prompt_variant=streaming_script.PROMPT_VARIANTS["l4_strong_format"],
        sample_entry={"sample_id": "test-1", "question": "Q", "gold": "### 42"},
        application_wall_clock_timeout_seconds=600.0,
        sdk_timeout_seconds=600.0,
        sleep_between_requests=60.0,
        max_retries=0,
        run_dir=tmp_path,
    )

    assert record["reasoning_content_present"] is True
    assert record["content_nonempty"] is False
    assert record["reasoning_only_output"] is True
    assert record["empty_or_invalid"] is True


def test_streaming_first_token_latency_statistics_are_recorded() -> None:
    summary = streaming_script.summarize_records(
        [
            {
                "provider": "mimo",
                "backend_path": "raw_sdk",
                "mode": "streaming",
                "prompt_variant": "strong_format_seed_prompt",
                "completed": True,
                "timeout": False,
                "provider_error": False,
                "rate_limit_observed": False,
                "official_score": 1.0,
                "relaxed_extractable_correct": True,
                "format_loss": False,
                "reasoning_error": False,
                "empty_or_invalid": False,
                "latency_seconds": 10.0,
                "time_to_first_token_seconds": 1.0,
                "time_to_complete_seconds": 10.0,
                "finish_reason": "stop",
                "first_token_observed": True,
                "content_nonempty": True,
                "error_type": None,
            },
            {
                "provider": "mimo",
                "backend_path": "raw_sdk",
                "mode": "streaming",
                "prompt_variant": "strong_format_seed_prompt",
                "completed": True,
                "timeout": False,
                "provider_error": False,
                "rate_limit_observed": False,
                "official_score": 0.0,
                "relaxed_extractable_correct": False,
                "format_loss": False,
                "reasoning_error": True,
                "empty_or_invalid": False,
                "latency_seconds": 14.0,
                "time_to_first_token_seconds": 3.0,
                "time_to_complete_seconds": 14.0,
                "finish_reason": "stop",
                "first_token_observed": True,
                "content_nonempty": True,
                "error_type": None,
            },
        ]
    )

    assert summary["avg_time_to_first_token_seconds"] == pytest.approx(2.0)
    assert summary["max_time_to_first_token_seconds"] == pytest.approx(3.0)
    assert summary["avg_time_to_complete_seconds"] == pytest.approx(12.0)
    assert summary["content_nonempty_count"] == 2


def test_relaxed_extractor_supports_required_formats() -> None:
    extractor = streaming_script.BASE.extract_relaxed_integer_answer
    assert extractor("### 70") == "70"
    assert extractor("\\boxed{70}") == "70"
    assert extractor("Final answer: 70") == "70"
    assert extractor("70") == "70"


def test_format_loss_classification_is_correct() -> None:
    result = streaming_script.classify_prediction(content="\\boxed{70}", gold="### 70")

    assert result["official_score"] == pytest.approx(0.0)
    assert result["relaxed_extractable_correct"] is True
    assert result["format_loss"] is True
    assert result["reasoning_error"] is False
    assert result["empty_or_invalid"] is False


def test_dry_run_main_does_not_call_execute_and_does_not_leak_api_key(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(streaming_script, "PROJECT_ROOT", tmp_path)
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

    monkeypatch.setattr(streaming_script, "build_selected_samples", fake_build_selected_samples)
    monkeypatch.setattr(streaming_script, "execute_plan", fail_if_execute_called)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stage4b_mimo_streaming_extended_timeout_diagnostic.py",
            "--report-path",
            "reports/stage4b_mimo_streaming_extended_timeout_diagnostic_result.md",
        ],
    )

    streaming_script.main()

    report_text = (
        tmp_path / "reports" / "stage4b_mimo_streaming_extended_timeout_diagnostic_result.md"
    ).read_text(encoding="utf-8")
    assert "top-secret-mimo-key" not in report_text


def test_missing_env_config_stays_explicit_in_dry_run_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(streaming_script, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.delenv("MIMO_API_BASE", raising=False)
    monkeypatch.delenv("MIMO_MODEL", raising=False)

    def fake_build_selected_samples(sample_ids: list[str]):
        return (
            [{"sample_id": "test-1", "question": "Q", "gold": "### 42", "sample": {}, "sample_index": 1}],
            {"split": "test", "split_label": "official test split", "selected_sample_ids": ["test-1"], "selected_count": 1},
        )

    monkeypatch.setattr(streaming_script, "build_selected_samples", fake_build_selected_samples)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stage4b_mimo_streaming_extended_timeout_diagnostic.py",
            "--report-path",
            "reports/stage4b_mimo_streaming_extended_timeout_diagnostic_result.md",
        ],
    )

    streaming_script.main()

    run_dir = next((tmp_path / streaming_script.DEFAULT_OUTPUT_DIR).glob("*"))
    payload = json.loads((run_dir / "input_snapshot.json").read_text(encoding="utf-8"))
    assert payload["provider_config"]["missing_config_reasons"] == [
        "missing api_base",
        "missing credential env: MIMO_API_KEY",
        "missing model",
    ]
