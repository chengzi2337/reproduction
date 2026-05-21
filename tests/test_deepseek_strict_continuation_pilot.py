from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SPEC = importlib.util.spec_from_file_location(
    "deepseek_strict_continuation_pilot_script",
    PROJECT_ROOT / "scripts" / "deepseek_run_strict_continuation_pilot.py",
)
assert SPEC is not None and SPEC.loader is not None
deepseek_pilot_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deepseek_pilot_script)


class _FakeResult:
    best_idx = 0
    val_aggregate_scores = [0.84]
    total_metric_calls = 96
    num_candidates = 3
    num_val_instances = 45
    num_full_val_evals = 2


def test_dry_run_does_not_call_gepa_optimize(tmp_path, monkeypatch) -> None:
    called = {"optimize": False}
    monkeypatch.setattr(
        deepseek_pilot_script,
        "load_dataset_via_strict_readme_path",
        lambda: ([{"input": "q"}], [{"input": "q"}], [{"input": "q"}], "dataset-source"),
    )
    monkeypatch.setattr(
        deepseek_pilot_script.gepa,
        "optimize",
        lambda **kwargs: called.__setitem__("optimize", True),
    )

    run_dir = deepseek_pilot_script.run_deepseek_strict_continuation_pilot(
        provider="deepseek",
        api_base="https://api.deepseek.com",
        api_key="",
        api_key_env_name="DEEPSEEK_API_KEY",
        task_model="deepseek-v4-flash",
        reflection_model="deepseek-v4-pro",
        max_metric_calls=50,
        seed=42,
        execute=False,
        output_root=tmp_path,
    )
    snapshot = json.loads(
        (run_dir / "deepseek_strict_continuation_pilot_input_snapshot.json").read_text(encoding="utf-8")
    )
    assert called["optimize"] is False
    assert snapshot["path_type"] == "deepseek_strict_continuation_pilot"
    assert snapshot["provider"] == "deepseek"
    assert snapshot["task_lm"] == "openai/deepseek-v4-flash"
    assert snapshot["reflection_lm"] == "openai/deepseek-v4-pro"
    assert "deepseek_strict_continuation_pilot_result_summary.json" not in {path.name for path in run_dir.iterdir()}


def test_execute_calls_gepa_optimize_with_mock(tmp_path, monkeypatch) -> None:
    called = {"optimize": False}
    monkeypatch.setattr(
        deepseek_pilot_script,
        "load_dataset_via_strict_readme_path",
        lambda: ([{"input": "q"}], [{"input": "q"}], [{"input": "q"}], "dataset-source"),
    )

    def _fake_optimize(**kwargs):
        called["optimize"] = True
        return _FakeResult()

    monkeypatch.setattr(deepseek_pilot_script.gepa, "optimize", _fake_optimize)
    monkeypatch.setattr(deepseek_pilot_script, "temporary_openai_compatible_env", _null_context)

    run_dir = deepseek_pilot_script.run_deepseek_strict_continuation_pilot(
        provider="deepseek",
        api_base="https://api.deepseek.com",
        api_key="ds-secret-do-not-leak",
        api_key_env_name="DEEPSEEK_API_KEY",
        task_model="deepseek-v4-flash",
        reflection_model="deepseek-v4-pro",
        max_metric_calls=50,
        seed=42,
        execute=True,
        output_root=tmp_path,
    )
    summary_text = (run_dir / "deepseek_strict_continuation_pilot_result_summary.json").read_text(
        encoding="utf-8"
    )
    summary = json.loads(summary_text)
    assert called["optimize"] is True
    assert summary["path_type"] == "deepseek_strict_continuation_pilot"
    assert summary["execution_completed"] is True
    assert summary["best_score"] == 0.84
    assert summary["num_candidates"] == 3
    assert "ds-secret-do-not-leak" not in summary_text


def test_missing_api_base_raises(tmp_path) -> None:
    with pytest.raises(ValueError, match="DEEPSEEK_API_BASE"):
        deepseek_pilot_script.run_deepseek_strict_continuation_pilot(
            provider="deepseek",
            api_base="",
            api_key="",
            api_key_env_name="DEEPSEEK_API_KEY",
            task_model="deepseek-v4-flash",
            reflection_model="deepseek-v4-pro",
            max_metric_calls=50,
            seed=42,
            execute=False,
            output_root=tmp_path,
        )


def test_execute_requires_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        deepseek_pilot_script,
        "load_dataset_via_strict_readme_path",
        lambda: ([{"input": "q"}], [{"input": "q"}], [{"input": "q"}], "dataset-source"),
    )
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        deepseek_pilot_script.run_deepseek_strict_continuation_pilot(
            provider="deepseek",
            api_base="https://api.deepseek.com",
            api_key="",
            api_key_env_name="DEEPSEEK_API_KEY",
            task_model="deepseek-v4-flash",
            reflection_model="deepseek-v4-pro",
            max_metric_calls=50,
            seed=42,
            execute=True,
            output_root=tmp_path,
        )


def test_execute_applies_guard_patch(tmp_path, monkeypatch) -> None:
    """execute=True 时，patch_default_adapter_batch_completion_guard 被正确应用。"""
    guard_calls = {"entered": False, "exited": False}
    from contextlib import contextmanager

    @contextmanager
    def _fake_guard():
        guard_calls["entered"] = True
        try:
            yield
        finally:
            guard_calls["exited"] = True

    monkeypatch.setattr(
        deepseek_pilot_script,
        "load_dataset_via_strict_readme_path",
        lambda: ([{"input": "q"}], [{"input": "q"}], [{"input": "q"}], "dataset-source"),
    )
    monkeypatch.setattr(deepseek_pilot_script.gepa, "optimize", lambda **kwargs: _FakeResult())
    monkeypatch.setattr(deepseek_pilot_script, "temporary_openai_compatible_env", _null_context)
    monkeypatch.setattr(deepseek_pilot_script, "patch_default_adapter_batch_completion_guard", _fake_guard)

    deepseek_pilot_script.run_deepseek_strict_continuation_pilot(
        provider="deepseek",
        api_base="https://api.deepseek.com",
        api_key="ds-test-key",
        api_key_env_name="DEEPSEEK_API_KEY",
        task_model="deepseek-v4-flash",
        reflection_model="deepseek-v4-pro",
        max_metric_calls=50,
        seed=42,
        execute=True,
        output_root=tmp_path,
    )
    assert guard_calls["entered"] is True
    assert guard_calls["exited"] is True


def test_execute_captures_traceback_on_failure(tmp_path, monkeypatch) -> None:
    """optimize 抛出异常时，result summary 包含 traceback 且 api key 被脱敏。"""
    secret = "ds-super-secret-key-12345"

    def _failing_optimize(**kwargs):
        raise RuntimeError(f"API call failed with key {secret}")

    monkeypatch.setattr(
        deepseek_pilot_script,
        "load_dataset_via_strict_readme_path",
        lambda: ([{"input": "q"}], [{"input": "q"}], [{"input": "q"}], "dataset-source"),
    )
    monkeypatch.setattr(deepseek_pilot_script.gepa, "optimize", _failing_optimize)
    monkeypatch.setattr(deepseek_pilot_script, "temporary_openai_compatible_env", _null_context)

    run_dir = deepseek_pilot_script.run_deepseek_strict_continuation_pilot(
        provider="deepseek",
        api_base="https://api.deepseek.com",
        api_key=secret,
        api_key_env_name="DEEPSEEK_API_KEY",
        task_model="deepseek-v4-flash",
        reflection_model="deepseek-v4-pro",
        max_metric_calls=50,
        seed=42,
        execute=True,
        output_root=tmp_path,
    )
    summary_path = run_dir / "deepseek_strict_continuation_pilot_result_summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["execution_completed"] is False
    assert summary["error_type"] == "RuntimeError"
    assert secret not in summary["error_message"]
    assert secret not in summary.get("traceback", "")


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


def _null_context(*args, **kwargs):
    return _NullContext()
