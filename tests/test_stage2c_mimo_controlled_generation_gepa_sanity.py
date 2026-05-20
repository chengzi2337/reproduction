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
    "stage2c_mimo_controlled_generation_gepa_sanity_script",
    PROJECT_ROOT / "scripts" / "stage2c_run_mimo_controlled_generation_gepa_sanity.py",
)
assert SPEC is not None and SPEC.loader is not None
stage2c_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage2c_script)


class _FakeResult:
    best_idx = 0
    val_aggregate_scores = [0.25]
    total_metric_calls = 45
    num_candidates = 1
    num_full_val_evals = 1


def test_dry_run_does_not_call_gepa_optimize(tmp_path, monkeypatch) -> None:
    called = {"optimize": False}

    monkeypatch.setattr(
        stage2c_script,
        "load_dataset_via_stage2c_path",
        lambda: ([{"input": "q"}], [{"input": "q"}], [{"input": "q"}], "dataset-source"),
    )
    monkeypatch.setattr(
        stage2c_script.gepa,
        "optimize",
        lambda **kwargs: called.__setitem__("optimize", True),
    )

    run_dir = stage2c_script.run_stage2c_sanity(
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        api_key="",
        task_model="mimo-v2.5-pro",
        reflection_model="mimo-v2.5-pro",
        max_metric_calls=1,
        seed=42,
        execute=False,
        output_root=tmp_path,
    )
    snapshot = json.loads((run_dir / "stage2c_input_snapshot.json").read_text(encoding="utf-8"))
    assert called["optimize"] is False
    assert snapshot["path_type"] == "stage2c_mimo_controlled_generation_gepa_sanity"
    assert snapshot["controlled_generation"]["enabled"] is True
    assert snapshot["controlled_generation"]["thinking_type"] == "disabled"
    assert snapshot["controlled_generation"]["max_completion_tokens"] == 512
    assert snapshot["not_strict_official_path"] is True
    assert snapshot["not_performance_claim"] is True
    assert "stage2c_result_summary.json" not in {path.name for path in run_dir.iterdir()}


def test_execute_calls_gepa_optimize_with_mock(tmp_path, monkeypatch) -> None:
    called = {"optimize": False}

    monkeypatch.setattr(
        stage2c_script,
        "load_dataset_via_stage2c_path",
        lambda: ([{"input": "q"}], [{"input": "q"}], [{"input": "q"}], "dataset-source"),
    )

    def _fake_optimize(**kwargs):
        called["optimize"] = True
        return _FakeResult()

    monkeypatch.setattr(stage2c_script.gepa, "optimize", _fake_optimize)
    monkeypatch.setattr(stage2c_script, "temporary_openai_compatible_env", _null_context)
    monkeypatch.setattr(stage2c_script, "controlled_litellm_generation", _null_context)

    run_dir = stage2c_script.run_stage2c_sanity(
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        api_key="tp-secret-do-not-leak",
        task_model="mimo-v2.5-pro",
        reflection_model="mimo-v2.5-pro",
        max_metric_calls=1,
        seed=42,
        execute=True,
        output_root=tmp_path,
    )
    summary_text = (run_dir / "stage2c_result_summary.json").read_text(encoding="utf-8")
    summary = json.loads(summary_text)
    assert called["optimize"] is True
    assert summary["execution_completed"] is True
    assert summary["controlled_generation_applied"] is True
    assert summary["best_score"] == 0.25
    assert "tp-secret-do-not-leak" not in summary_text


def test_missing_api_base_raises(tmp_path) -> None:
    with pytest.raises(ValueError, match="MIMO_API_BASE"):
        stage2c_script.run_stage2c_sanity(
            api_base="",
            api_key="",
            task_model="mimo-v2.5-pro",
            reflection_model="mimo-v2.5-pro",
            max_metric_calls=1,
            seed=42,
            execute=False,
            output_root=tmp_path,
        )


def test_execute_requires_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        stage2c_script,
        "load_dataset_via_stage2c_path",
        lambda: ([{"input": "q"}], [{"input": "q"}], [{"input": "q"}], "dataset-source"),
    )
    with pytest.raises(ValueError, match="MIMO_API_KEY"):
        stage2c_script.run_stage2c_sanity(
            api_base="https://token-plan-cn.xiaomimimo.com/v1",
            api_key="",
            task_model="mimo-v2.5-pro",
            reflection_model="mimo-v2.5-pro",
            max_metric_calls=1,
            seed=42,
            execute=True,
            output_root=tmp_path,
        )


def test_dry_run_can_work_without_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        stage2c_script,
        "load_dataset_via_stage2c_path",
        lambda: ([{"input": "q"}], [{"input": "q"}], [{"input": "q"}], "dataset-source"),
    )
    run_dir = stage2c_script.run_stage2c_sanity(
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        api_key="",
        task_model="mimo-v2.5-pro",
        reflection_model="mimo-v2.5-pro",
        max_metric_calls=1,
        seed=42,
        execute=False,
        output_root=tmp_path,
    )
    assert (run_dir / "stage2c_input_snapshot.json").exists()


def test_snapshot_does_not_leak_api_key_and_stage1_file_unchanged(tmp_path, monkeypatch) -> None:
    stage1_file = PROJECT_ROOT / "reports" / "stage1_final_status.md"
    before = stage1_file.read_text(encoding="utf-8")
    monkeypatch.setattr(
        stage2c_script,
        "load_dataset_via_stage2c_path",
        lambda: ([{"input": "q"}], [{"input": "q"}], [{"input": "q"}], "dataset-source"),
    )

    run_dir = stage2c_script.run_stage2c_sanity(
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        api_key="tp-secret-do-not-leak",
        task_model="mimo-v2.5-pro",
        reflection_model="mimo-v2.5-pro",
        max_metric_calls=1,
        seed=42,
        execute=False,
        output_root=tmp_path,
    )
    snapshot_text = (run_dir / "stage2c_input_snapshot.json").read_text(encoding="utf-8")
    after = stage1_file.read_text(encoding="utf-8")
    assert "tp-secret-do-not-leak" not in snapshot_text
    assert before == after


class _NullContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


def _null_context(*args, **kwargs):
    return _NullContext()
