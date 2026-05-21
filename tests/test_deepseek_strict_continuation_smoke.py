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
    "deepseek_strict_continuation_smoke_script",
    PROJECT_ROOT / "scripts" / "deepseek_run_strict_continuation_smoke.py",
)
assert SPEC is not None and SPEC.loader is not None
deepseek_smoke_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deepseek_smoke_script)


class _FakeResult:
    best_idx = 0
    val_aggregate_scores = [0.33]
    total_metric_calls = 45
    num_candidates = 1
    num_val_instances = 45
    num_full_val_evals = 1


def test_dry_run_does_not_call_gepa_optimize(tmp_path, monkeypatch) -> None:
    called = {"optimize": False}
    monkeypatch.setattr(
        deepseek_smoke_script,
        "load_dataset_via_strict_readme_path",
        lambda: ([{"input": "q"}], [{"input": "q"}], [{"input": "q"}], "dataset-source"),
    )
    monkeypatch.setattr(
        deepseek_smoke_script.gepa,
        "optimize",
        lambda **kwargs: called.__setitem__("optimize", True),
    )

    run_dir = deepseek_smoke_script.run_deepseek_strict_continuation_smoke(
        provider="deepseek",
        api_base="https://api.deepseek.com",
        api_key="",
        api_key_env_name="DEEPSEEK_API_KEY",
        task_model="deepseek-v4-flash",
        reflection_model="deepseek-v4-pro",
        max_metric_calls=10,
        seed=42,
        execute=False,
        output_root=tmp_path,
    )
    snapshot = json.loads(
        (run_dir / "deepseek_strict_continuation_smoke_input_snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    assert called["optimize"] is False
    assert snapshot["path_type"] == "deepseek_strict_continuation_smoke"
    assert snapshot["provider"] == "deepseek"
    assert snapshot["task_lm"] == "openai/deepseek-v4-flash"
    assert snapshot["reflection_lm"] == "openai/deepseek-v4-pro"
    assert snapshot["not_stage1_rewrite"] is True
    assert snapshot["not_same_model_reproduction"] is True
    assert snapshot["not_official_budget"] is True
    assert "deepseek_strict_continuation_smoke_result_summary.json" not in {
        path.name for path in run_dir.iterdir()
    }


def test_execute_calls_gepa_optimize_with_mock(tmp_path, monkeypatch) -> None:
    called = {"optimize": False}
    monkeypatch.setattr(
        deepseek_smoke_script,
        "load_dataset_via_strict_readme_path",
        lambda: ([{"input": "q"}], [{"input": "q"}], [{"input": "q"}], "dataset-source"),
    )

    def _fake_optimize(**kwargs):
        called["optimize"] = True
        return _FakeResult()

    monkeypatch.setattr(deepseek_smoke_script.gepa, "optimize", _fake_optimize)
    monkeypatch.setattr(deepseek_smoke_script, "temporary_openai_compatible_env", _null_context)

    run_dir = deepseek_smoke_script.run_deepseek_strict_continuation_smoke(
        provider="deepseek",
        api_base="https://api.deepseek.com",
        api_key="ds-secret-do-not-leak",
        api_key_env_name="DEEPSEEK_API_KEY",
        task_model="deepseek-v4-flash",
        reflection_model="deepseek-v4-pro",
        max_metric_calls=10,
        seed=42,
        execute=True,
        output_root=tmp_path,
    )
    summary_text = (run_dir / "deepseek_strict_continuation_smoke_result_summary.json").read_text(
        encoding="utf-8"
    )
    summary = json.loads(summary_text)
    assert called["optimize"] is True
    assert summary["path_type"] == "deepseek_strict_continuation_smoke"
    assert summary["execution_completed"] is True
    assert summary["best_score"] == 0.33
    assert "ds-secret-do-not-leak" not in summary_text


def test_missing_api_base_raises(tmp_path) -> None:
    with pytest.raises(ValueError, match="DEEPSEEK_API_BASE"):
        deepseek_smoke_script.run_deepseek_strict_continuation_smoke(
            provider="deepseek",
            api_base="",
            api_key="",
            api_key_env_name="DEEPSEEK_API_KEY",
            task_model="deepseek-v4-flash",
            reflection_model="deepseek-v4-pro",
            max_metric_calls=10,
            seed=42,
            execute=False,
            output_root=tmp_path,
        )


def test_execute_requires_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        deepseek_smoke_script,
        "load_dataset_via_strict_readme_path",
        lambda: ([{"input": "q"}], [{"input": "q"}], [{"input": "q"}], "dataset-source"),
    )
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        deepseek_smoke_script.run_deepseek_strict_continuation_smoke(
            provider="deepseek",
            api_base="https://api.deepseek.com",
            api_key="",
            api_key_env_name="DEEPSEEK_API_KEY",
            task_model="deepseek-v4-flash",
            reflection_model="deepseek-v4-pro",
            max_metric_calls=10,
            seed=42,
            execute=True,
            output_root=tmp_path,
        )


def test_only_allows_deepseek_provider(tmp_path) -> None:
    with pytest.raises(ValueError, match="provider=deepseek"):
        deepseek_smoke_script.run_deepseek_strict_continuation_smoke(
            provider="mimo",
            api_base="https://api.deepseek.com",
            api_key="",
            api_key_env_name="MIMO_API_KEY",
            task_model="deepseek-v4-flash",
            reflection_model="deepseek-v4-pro",
            max_metric_calls=10,
            seed=42,
            execute=False,
            output_root=tmp_path,
        )


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


def _null_context(*args, **kwargs):
    return _NullContext()
