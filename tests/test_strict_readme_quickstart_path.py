from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SPEC = importlib.util.spec_from_file_location(
    "strict_readme_quickstart_path_script",
    PROJECT_ROOT / "scripts" / "07_strict_readme_quickstart_path.py",
)
assert SPEC is not None and SPEC.loader is not None
strict_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(strict_script)


class _FakeResult:
    best_idx = 0
    val_aggregate_scores = [0.7]
    total_metric_calls = 3
    num_candidates = 1
    num_val_instances = 2
    num_full_val_evals = 1


def test_strict_readme_quickstart_dry_run_writes_input_snapshot(tmp_path, monkeypatch) -> None:
    dataset = (
        [{"input": "train-q", "answer": "### 1"}],
        [{"input": "val-q", "answer": "### 2"}],
        [{"input": "test-q", "answer": "### 3"}],
        "official-source",
    )
    monkeypatch.setattr(strict_script, "load_dataset_via_strict_readme_path", lambda: dataset)
    monkeypatch.setattr(strict_script, "create_timestamp", lambda: "20260518T210000+0800")
    monkeypatch.setattr(
        strict_script.gepa,
        "optimize",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("dry-run 不应调用 optimize")),
    )

    run_dir = strict_script.run_strict_readme_quickstart_path(
        task_model="deepseek-v4-flash",
        reflection_model="deepseek-v4-pro",
        max_metric_calls=5,
        seed=42,
        api_base="https://api.deepseek.com",
        api_key="fake-key",
        execute=False,
        output_root=tmp_path / "strict-dry-run",
    )

    snapshot = json.loads((run_dir / "strict_input_snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["path_type"] == "strict_readme_quickstart_path"
    assert snapshot["task_lm"] == "openai/deepseek-v4-flash"
    assert snapshot["reflection_lm"] == "openai/deepseek-v4-pro"
    assert snapshot["max_metric_calls"] == 5
    assert snapshot["seed"] == 42
    assert snapshot["trainset_size"] == 1
    assert snapshot["valset_size"] == 1
    assert snapshot["testset_size"] == 1
    assert snapshot["execute_optimize"] is False
    assert snapshot["seed_candidate"] == strict_script.README_QUICKSTART_SEED_PROMPT


def test_strict_readme_quickstart_execute_writes_result_summary(tmp_path, monkeypatch) -> None:
    dataset = (
        [{"input": "train-q", "answer": "### 1"}],
        [{"input": "val-q", "answer": "### 2"}],
        None,
        "official-source",
    )
    monkeypatch.setattr(strict_script, "load_dataset_via_strict_readme_path", lambda: dataset)
    monkeypatch.setattr(strict_script, "create_timestamp", lambda: "20260518T210500+0800")
    monkeypatch.setattr(strict_script.gepa, "optimize", lambda **kwargs: _FakeResult())

    run_dir = strict_script.run_strict_readme_quickstart_path(
        task_model="deepseek-v4-flash",
        reflection_model="deepseek-v4-pro",
        max_metric_calls=3,
        seed=7,
        api_base="https://api.deepseek.com",
        api_key="fake-key",
        execute=True,
        output_root=tmp_path / "strict-exec",
    )

    summary = json.loads((run_dir / "strict_result_summary.json").read_text(encoding="utf-8"))
    assert summary["best_score"] == 0.7
    assert summary["total_metric_calls"] == 3


def test_strict_readme_quickstart_requires_models() -> None:
    try:
        strict_script.run_strict_readme_quickstart_path(
            task_model="",
            reflection_model="deepseek-v4-pro",
            max_metric_calls=3,
            seed=7,
            api_base="https://api.deepseek.com",
            api_key="fake-key",
            execute=False,
            output_root=PROJECT_ROOT / "outputs" / "tmp-test",
        )
    except ValueError as exc:
        assert "TASK_MODEL" in str(exc)
    else:
        raise AssertionError("缺少 task model 时必须失败。")


def test_strict_readme_quickstart_execute_requires_api_key(tmp_path, monkeypatch) -> None:
    dataset = (
        [{"input": "train-q", "answer": "### 1"}],
        [{"input": "val-q", "answer": "### 2"}],
        None,
        "official-source",
    )
    monkeypatch.setattr(strict_script, "load_dataset_via_strict_readme_path", lambda: dataset)

    try:
        strict_script.run_strict_readme_quickstart_path(
            task_model="deepseek-v4-flash",
            reflection_model="deepseek-v4-pro",
            max_metric_calls=3,
            seed=7,
            api_base="https://api.deepseek.com",
            api_key="",
            execute=True,
            output_root=tmp_path / "strict-exec-no-key",
        )
    except ValueError as exc:
        assert "DEEPSEEK_API_KEY" in str(exc)
    else:
        raise AssertionError("execute 模式缺少 API key 时必须失败。")
