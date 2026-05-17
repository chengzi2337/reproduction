from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ExperimentConfig
import src.gepa_official_runner as runner


SPEC = importlib.util.spec_from_file_location(
    "minimal_official_path_sanity_script",
    PROJECT_ROOT / "scripts" / "06_minimal_official_path_sanity.py",
)
assert SPEC is not None and SPEC.loader is not None
sanity_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sanity_script)


class _FakeResult:
    best_idx = 0
    val_aggregate_scores = [0.6]
    best_candidate = {"system_prompt": "optimized"}
    total_metric_calls = 4
    num_candidates = 1
    num_val_instances = 2
    num_full_val_evals = 1

    def to_dict(self):
        return {"best_idx": self.best_idx}


def _build_config(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_name="pilot",
        reproduction_type="method_level_reproduction",
        provider="deepseek",
        api_base="https://api.deepseek.com",
        benchmark="aime",
        task_model="deepseek-v4-flash",
        reflection_model="deepseek-v4-pro",
        max_metric_calls=7,
        temperature_task=0.0,
        temperature_reflection=0.7,
        seed=42,
        output_dir=tmp_path / "outputs",
        allow_model_substitution=False,
        save_raw_pickle=False,
        config_path=tmp_path / "config.yaml",
        project_root=PROJECT_ROOT,
        api_key="fake-key",
    )


def test_minimal_official_path_dry_run_writes_core_snapshot(tmp_path, monkeypatch) -> None:
    config = _build_config(tmp_path)
    dataset = (
        [{"input": "train-q", "answer": "### 1"}],
        [{"input": "val-q", "answer": "### 2"}],
        [{"input": "test-q", "answer": "### 3"}],
        "official-source",
    )
    monkeypatch.setattr(sanity_script, "load_dataset_via_direct_official_path", lambda: dataset)
    monkeypatch.setattr(sanity_script, "create_timestamp", lambda: "20260517T161000+0800")

    run_dir = sanity_script.run_minimal_official_path_sanity(
        config,
        execute=False,
        output_root=tmp_path / "sanity-outputs",
    )

    snapshot = json.loads((run_dir / "core_optimize_kwargs.json").read_text(encoding="utf-8"))
    assert snapshot["task_lm"] == "openai/deepseek-v4-flash"
    assert snapshot["reflection_lm"] == "openai/deepseek-v4-pro"
    assert snapshot["max_metric_calls"] == 7
    assert snapshot["seed"] == 42
    assert snapshot["trainset_size"] == 1
    assert snapshot["valset_size"] == 1
    assert snapshot["testset_size"] == 1
    assert snapshot["execute_optimize"] is False


def test_wrapper_and_minimal_sanity_share_same_core_optimize_kwargs(tmp_path, monkeypatch) -> None:
    config = _build_config(tmp_path)
    trainset = [{"input": "train-q", "answer": "### 1"}]
    valset = [{"input": "val-q", "answer": "### 2"}]
    captured_wrapper_kwargs: dict[str, object] = {}
    wrapper_run_dir = tmp_path / "wrapper-run"

    def fake_create_run_dir(_: Path) -> Path:
        wrapper_run_dir.mkdir(parents=True, exist_ok=False)
        return wrapper_run_dir

    def fake_optimize(**kwargs):
        captured_wrapper_kwargs.update(kwargs)
        return _FakeResult()

    monkeypatch.setattr(
        runner,
        "load_official_aime_dataset",
        lambda: (trainset, valset, None, "official-source", []),
    )
    monkeypatch.setattr(
        runner,
        "_collect_probe_results",
        lambda config: [],
    )
    monkeypatch.setattr(runner, "create_run_dir", fake_create_run_dir)
    monkeypatch.setattr(runner.gepa, "optimize", fake_optimize)

    runner.run_gepa_aime_experiment(config)

    sanity_kwargs = sanity_script.build_core_optimize_kwargs(
        config=config,
        trainset=trainset,
        valset=valset,
        run_dir=wrapper_run_dir,
    )

    for key in [
        "seed_candidate",
        "trainset",
        "valset",
        "task_lm",
        "reflection_lm",
        "max_metric_calls",
        "seed",
        "run_dir",
    ]:
        assert captured_wrapper_kwargs[key] == sanity_kwargs[key]


def test_minimal_official_path_execute_writes_minimal_result(tmp_path, monkeypatch) -> None:
    config = _build_config(tmp_path)
    dataset = (
        [{"input": "train-q", "answer": "### 1"}],
        [{"input": "val-q", "answer": "### 2"}],
        None,
        "official-source",
    )
    monkeypatch.setattr(sanity_script, "load_dataset_via_direct_official_path", lambda: dataset)
    monkeypatch.setattr(sanity_script, "create_timestamp", lambda: "20260517T161500+0800")
    monkeypatch.setattr(sanity_script.gepa, "optimize", lambda **kwargs: _FakeResult())

    run_dir = sanity_script.run_minimal_official_path_sanity(
        config,
        execute=True,
        output_root=tmp_path / "sanity-exec",
    )

    summary = json.loads((run_dir / "minimal_result_summary.json").read_text(encoding="utf-8"))
    assert summary["best_score"] == 0.6
    assert summary["total_metric_calls"] == 4
