from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import litellm
import pytest

from src.mimo_streaming_gepa_bridge import (
    FirstTokenTimeout,
    MiMoStreamingBridgeConfig,
    patch_litellm_for_mimo_streaming,
    run_streaming_completion,
    build_streaming_completion_kwargs,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "stage4c_run_mimo_streaming_gepa_sanity.py"

SPEC = importlib.util.spec_from_file_location("stage4c_mimo_streaming_gepa_sanity_script", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
stage4c_script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = stage4c_script
SPEC.loader.exec_module(stage4c_script)


def _bridge_config(
    api_key: str = "secret-key",
    *,
    first_token_timeout_seconds: float = 1.0,
) -> MiMoStreamingBridgeConfig:
    return MiMoStreamingBridgeConfig(
        model="mimo-v2.5-pro",
        api_base="https://example.com/v1",
        api_key=api_key,
        provider="mimo",
        thinking_type="enabled",
        first_token_timeout_seconds=first_token_timeout_seconds,
        sdk_timeout_seconds=600.0,
        emergency_after_first_token_seconds=None,
    )


def _stub_dataset_metadata(diagnostic_val_limit: int):
    trainset = [{"question": "q1", "answer": "1"}]
    valset = [{"question": "q2", "answer": "2"}]
    testset = [{"question": "q3", "answer": "3"}]
    return (
        trainset,
        valset[:diagnostic_val_limit],
        testset,
        "stub_dataset_source",
        ["stub adaptation note"],
        {
            "trainset_size_full": len(trainset),
            "valset_size_full": len(valset),
            "valset_size_used": len(valset[:diagnostic_val_limit]),
            "diagnostic_val_limit": diagnostic_val_limit,
            "testset_size": len(testset),
        },
    )


def test_dry_run_main_does_not_call_model_or_gepa_and_writes_stub(monkeypatch, tmp_path: Path) -> None:
    def _forbidden_optimize(**kwargs):
        raise AssertionError("dry-run 不应进入 gepa.optimize")

    def _forbidden_completion(*args, **kwargs):
        raise AssertionError("dry-run 不应调用 litellm.completion")

    monkeypatch.setattr(stage4c_script.gepa, "optimize", _forbidden_optimize)
    monkeypatch.setattr(stage4c_script.litellm, "completion", _forbidden_completion)
    monkeypatch.setattr(stage4c_script.litellm, "batch_completion", _forbidden_completion)
    monkeypatch.setattr(stage4c_script, "load_dataset_metadata", _stub_dataset_metadata)
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.setenv("MIMO_API_BASE", "https://example.com/v1")
    monkeypatch.setenv("MIMO_MODEL", "mimo-v2.5-pro")

    output_dir = tmp_path / "outputs"
    report_path = tmp_path / "report.md"
    run_dir = tmp_path / "run"
    monkeypatch.setattr(
        sys,
        "argv",
        [
                "stage4c.py",
                "--output-dir",
                str(output_dir),
                "--report-path",
                str(report_path),
                "--run-dir",
                str(run_dir),
            ],
        )

    stage4c_script.main()

    report_text = report_path.read_text(encoding="utf-8")
    input_snapshot = json.loads((run_dir / "input_snapshot.json").read_text(encoding="utf-8"))
    run_summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))

    assert input_snapshot["metadata"]["model_called"] is False
    assert input_snapshot["requested_execution"]["execute_optimize"] is False
    assert input_snapshot["requested_execution"]["thinking"] == {"type": "enabled"}
    assert input_snapshot["requested_execution"]["streaming"] is True
    assert input_snapshot["requested_execution"]["max_metric_calls"] == 1
    assert run_summary["optimize_attempted"] is False
    assert "secret-key" not in report_text
    assert "secret-key" not in json.dumps(input_snapshot, ensure_ascii=False)
    assert str(PROJECT_ROOT) not in report_text


def test_enforce_bounds_allows_only_one_or_two_metric_calls(monkeypatch) -> None:
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.setenv("MIMO_API_BASE", "https://example.com/v1")
    monkeypatch.setenv("MIMO_MODEL", "mimo-v2.5-pro")

    args_two = argparse.Namespace(
        provider="mimo",
        api_key_env="MIMO_API_KEY",
        api_base_env="MIMO_API_BASE",
        model_env="MIMO_MODEL",
        output_dir="outputs",
        report_path="reports/report.md",
        run_dir=None,
        first_token_timeout=1800.0,
        sdk_timeout=1800.0,
        emergency_after_first_token=None,
        max_metric_calls=2,
        diagnostic_val_limit=1,
        execute=False,
    )
    runtime_two = stage4c_script.build_runtime_config(args_two)
    stage4c_script.enforce_bounds(args_two, runtime_two)

    args_three = argparse.Namespace(
        **{**args_two.__dict__, "max_metric_calls": 3}
    )
    runtime_three = stage4c_script.build_runtime_config(args_three)
    with pytest.raises(stage4c_script.Stage4CMiMoStreamingGEPASanityError, match="max_metric_calls=1 或 2"):
        stage4c_script.enforce_bounds(args_three, runtime_three)


def test_build_streaming_completion_kwargs_injects_enabled_without_default_caps() -> None:
    kwargs = build_streaming_completion_kwargs(
        bridge_config=_bridge_config(),
        messages=[{"role": "user", "content": "Q"}],
        inherited_kwargs={"temperature": 0.7, "max_workers": 8},
    )

    assert kwargs["stream"] is True
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}
    assert "thinking" not in kwargs
    assert "max_completion_tokens" not in kwargs
    assert "max_workers" not in kwargs
    assert kwargs["temperature"] == 0.7


def test_patch_restores_litellm_and_batch_responses_are_gepa_readable() -> None:
    class _Chunk:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def model_dump(self) -> dict[str, object]:
            return self.payload

    class _Stream:
        def __init__(self, content: str) -> None:
            self.response = SimpleNamespace(status_code=200)
            self.content = content

        def __iter__(self):
            yield _Chunk({"choices": [{"delta": {"content": self.content}, "finish_reason": "stop"}]})

        def close(self) -> None:
            return None

    calls: list[dict[str, object]] = []
    def _fake_completion(*args, **kwargs):
        calls.append(kwargs)
        messages = kwargs["messages"]
        content = messages[-1]["content"]
        return _Stream(str(content).upper())

    litellm.completion = _fake_completion
    litellm.batch_completion = lambda *args, **kwargs: []
    previous_completion = litellm.completion
    previous_batch = litellm.batch_completion
    records: list[dict[str, object]] = []

    try:
        with patch_litellm_for_mimo_streaming(bridge_config=_bridge_config(), call_records=records):
            responses = litellm.batch_completion(
                model="openai/mimo-v2.5-pro",
                messages=[
                    [{"role": "user", "content": "one"}],
                    [{"role": "user", "content": "two"}],
                ],
                max_workers=16,
            )
            assert [resp.choices[0].message.content for resp in responses] == ["ONE", "TWO"]
            assert [resp.choices[0].finish_reason for resp in responses] == ["stop", "stop"]
            assert len(records) == 2
            assert all(record["first_token_observed"] for record in records)
            assert all(call["extra_body"] == {"thinking": {"type": "enabled"}} for call in calls)
            assert all("thinking" not in call for call in calls)
    finally:
        assert litellm.completion is previous_completion
        assert litellm.batch_completion is previous_batch


def test_first_token_timeout_is_classified_and_stream_close_attempted() -> None:
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

    stream = _SlowStream()

    with pytest.raises(FirstTokenTimeout) as exc_info:
        run_streaming_completion(
            original_completion=lambda **kwargs: stream,
            bridge_config=_bridge_config(first_token_timeout_seconds=0.05),
            messages=[{"role": "user", "content": "Q"}],
            inherited_kwargs={},
            call_role="task_batch_completion",
            batch_index=0,
        )

    record = exc_info.value.bridge_record
    assert record["first_token_timeout_triggered"] is True
    assert record["first_token_observed"] is False
    assert record["stream_close_attempted"] is True
    assert stream.close_calls >= 1


def test_after_first_token_natural_completion_records_latencies() -> None:
    class _Chunk:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def model_dump(self) -> dict[str, object]:
            return self.payload

    class _Stream:
        def __init__(self) -> None:
            self.response = SimpleNamespace(status_code=200)

        def __iter__(self):
            yield _Chunk({"choices": [{"delta": {"content": "### "}, "finish_reason": None}]})
            time.sleep(0.06)
            yield _Chunk({"choices": [{"delta": {"content": "70"}, "finish_reason": "stop"}]})

        def close(self) -> None:
            return None

    response, record, raw_payload = run_streaming_completion(
        original_completion=lambda **kwargs: _Stream(),
        bridge_config=_bridge_config(),
        messages=[{"role": "user", "content": "Q"}],
        inherited_kwargs={},
        call_role="reflection_completion",
        batch_index=None,
    )

    assert response.choices[0].message.content == "### 70"
    assert record["first_token_observed"] is True
    assert record["stream_completed"] is True
    assert record["time_to_first_token_seconds"] is not None
    assert record["time_after_first_token_seconds"] is not None
    assert record["time_after_first_token_seconds"] >= 0.05
    assert record["finish_reason"] == "stop"
    assert raw_payload["content"] == "### 70"


def test_stream_error_preserves_partial_content_and_sanitizes_secret() -> None:
    class _Chunk:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def model_dump(self) -> dict[str, object]:
            return self.payload

    class _BrokenStream:
        def __init__(self) -> None:
            self.response = SimpleNamespace(status_code=200)
            self.close_calls = 0

        def __iter__(self):
            yield _Chunk({"choices": [{"delta": {"content": "### "}, "finish_reason": None}]})
            raise TimeoutError("sdk timed out for secret-key")

        def close(self) -> None:
            self.close_calls += 1

    stream = _BrokenStream()

    with pytest.raises(TimeoutError) as exc_info:
        run_streaming_completion(
            original_completion=lambda **kwargs: stream,
            bridge_config=_bridge_config(),
            messages=[{"role": "user", "content": "Q"}],
            inherited_kwargs={},
            call_role="task_batch_completion",
            batch_index=0,
        )

    record = exc_info.value.bridge_record
    raw_payload = exc_info.value.bridge_raw_payload
    assert record["partial_content_nonempty"] is True
    assert record["content_nonempty"] is True
    assert record["sdk_timeout_triggered"] is True
    assert "secret-key" not in record["error_message_sanitized"]
    assert raw_payload["content"] == "### "
    assert stream.close_calls >= 1


def test_execute_only_branch_calls_gepa_optimize(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MIMO_API_KEY", "secret-key")
    monkeypatch.setenv("MIMO_API_BASE", "https://example.com/v1")
    monkeypatch.setenv("MIMO_MODEL", "mimo-v2.5-pro")

    calls = {"optimize": 0}

    def _ok_health(*, bridge_config, original_completion):
        return (
            {
                "provider": "mimo",
                "model": "mimo-v2.5-pro",
                "content_exact_ok": True,
                "content_preview": "OK",
                "latency_seconds": 0.1,
                "error_type": None,
                "error_message_sanitized": None,
                "http_status": 200,
            },
            {"content": "OK"},
        )

    @contextmanager
    def _noop_patch(**kwargs):
        yield

    class _Result:
        best_idx = 0
        val_aggregate_scores = [1.0]
        total_metric_calls = 2
        num_candidates = 2
        num_val_instances = 1
        num_full_val_evals = 1

    def _fake_optimize(**kwargs):
        calls["optimize"] += 1
        return _Result()

    monkeypatch.setattr(stage4c_script, "execute_health_check", _ok_health)
    monkeypatch.setattr(stage4c_script, "patch_litellm_for_mimo_streaming", _noop_patch)
    monkeypatch.setattr(stage4c_script.gepa, "optimize", _fake_optimize)
    monkeypatch.setattr(stage4c_script, "load_dataset_metadata", _stub_dataset_metadata)

    output_dir = tmp_path / "outputs"
    report_path = tmp_path / "report.md"
    run_dir = tmp_path / "run"
    monkeypatch.setattr(
        sys,
        "argv",
        [
                "stage4c.py",
                "--execute",
                "--output-dir",
                str(output_dir),
                "--report-path",
                str(report_path),
                "--run-dir",
                str(run_dir),
                "--max-metric-calls",
                "2",
            ],
        )

    stage4c_script.main()

    report_text = report_path.read_text(encoding="utf-8")
    run_summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    input_snapshot = json.loads((run_dir / "input_snapshot.json").read_text(encoding="utf-8"))
    assert calls["optimize"] == 1
    assert run_summary["optimize_attempted"] is True
    assert run_summary["optimize_succeeded"] is True
    assert run_summary["result_summary"]["total_metric_calls"] == 2
    assert run_summary["result_summary"]["num_candidates"] == 2
    assert input_snapshot["requested_execution"]["max_metric_calls"] == 2
    assert input_snapshot["requested_execution"]["requested_budget_reaches_loop_entry"] is True
    assert input_snapshot["requested_execution"]["stage4c_scope"] == "optimization_loop_entry_followup"
    assert "optimization-loop entry passed" in report_text


def test_health_check_failure_blocks_execute(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MIMO_API_KEY", "secret-key")
    monkeypatch.setenv("MIMO_API_BASE", "https://example.com/v1")
    monkeypatch.setenv("MIMO_MODEL", "mimo-v2.5-pro")

    calls = {"optimize": 0}

    def _fail_pre_health(*, bridge_config, original_completion):
        return (
            {
                "provider": "mimo",
                "model": "mimo-v2.5-pro",
                "content_exact_ok": False,
                "content_preview": "",
                "latency_seconds": None,
                "error_type": "APIConnectionError",
                "error_message_sanitized": "network down",
                "http_status": None,
            },
            None,
        )

    def _forbidden_optimize(**kwargs):
        calls["optimize"] += 1
        raise AssertionError("health check 失败后不应进入 optimize")

    monkeypatch.setattr(stage4c_script, "execute_health_check", _fail_pre_health)
    monkeypatch.setattr(stage4c_script.gepa, "optimize", _forbidden_optimize)
    monkeypatch.setattr(stage4c_script, "load_dataset_metadata", _stub_dataset_metadata)

    output_dir = tmp_path / "outputs"
    report_path = tmp_path / "report.md"
    run_dir = tmp_path / "run"
    monkeypatch.setattr(
        sys,
        "argv",
        [
                "stage4c.py",
                "--execute",
                "--output-dir",
                str(output_dir),
                "--report-path",
                str(report_path),
                "--run-dir",
                str(run_dir),
            ],
        )

    stage4c_script.main()

    run_summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert calls["optimize"] == 0
    assert run_summary["optimize_attempted"] is False
    assert run_summary["error_type"] == "APIConnectionError"


def test_missing_config_returns_clear_error_without_optimize(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.setenv("MIMO_API_BASE", "https://example.com/v1")
    monkeypatch.setenv("MIMO_MODEL", "mimo-v2.5-pro")

    calls = {"optimize": 0}

    def _forbidden_optimize(**kwargs):
        calls["optimize"] += 1
        raise AssertionError("missing config 后不应进入 optimize")

    monkeypatch.setattr(stage4c_script.gepa, "optimize", _forbidden_optimize)
    monkeypatch.setattr(stage4c_script, "load_dataset_metadata", _stub_dataset_metadata)

    output_dir = tmp_path / "outputs"
    report_path = tmp_path / "report.md"
    run_dir = tmp_path / "run"
    monkeypatch.setattr(
        sys,
        "argv",
        [
                "stage4c.py",
                "--execute",
                "--output-dir",
                str(output_dir),
                "--report-path",
                str(report_path),
                "--run-dir",
                str(run_dir),
            ],
        )

    stage4c_script.main()

    run_summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert calls["optimize"] == 0
    assert run_summary["error_type"] == "ConfigMissing"
    assert "missing credential env: MIMO_API_KEY" in run_summary["error_message_sanitized"]
