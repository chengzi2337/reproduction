from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ExperimentConfig
from src.deepseek_utils import ProbeResult
import src.gepa_official_runner as runner


class _FakeResultWithDict:
    best_idx = 0
    val_aggregate_scores = [0.5]
    best_candidate = {"system_prompt": "optimized prompt"}
    total_metric_calls = 9
    num_candidates = 1
    num_val_instances = 2
    num_full_val_evals = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_idx": self.best_idx,
            "total_metric_calls": self.total_metric_calls,
            "best_candidate": self.best_candidate,
        }


class _FakeResultWithoutDict:
    best_idx = 0
    val_aggregate_scores = [0.25]
    best_candidate = {"system_prompt": "optimized prompt without dict"}
    total_metric_calls = 7
    num_candidates = 1
    num_val_instances = 2
    num_full_val_evals = 1


def _build_config(tmp_path: Path, *, save_raw_pickle: bool) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_name="test_experiment",
        reproduction_type="method_level_reproduction",
        provider="deepseek",
        api_base="https://api.deepseek.com",
        benchmark="aime",
        task_model="test-task-model",
        reflection_model="test-reflection-model",
        max_metric_calls=3,
        temperature_task=0.0,
        temperature_reflection=0.7,
        seed=42,
        output_dir=tmp_path / "outputs",
        allow_model_substitution=False,
        save_raw_pickle=save_raw_pickle,
        config_path=tmp_path / "config.yaml",
        project_root=PROJECT_ROOT,
        api_key="test-key",
    )


def _ok_probe(model_name: str) -> ProbeResult:
    return ProbeResult(
        ok=True,
        model=model_name,
        response_text="OK",
    )


def test_runner_passes_expected_arguments_and_saves_raw_json(tmp_path: Path, monkeypatch) -> None:
    trainset = [{"input": "q1", "answer": "a1"}]
    valset = [{"input": "q2", "answer": "a2"}]
    captured_optimize_kwargs: dict[str, Any] = {}
    run_dir = tmp_path / "run-json"

    def fake_create_run_dir(_: Path) -> Path:
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    def fake_optimize(**kwargs: Any) -> _FakeResultWithDict:
        captured_optimize_kwargs.update(kwargs)
        return _FakeResultWithDict()

    monkeypatch.setattr(
        runner,
        "load_official_aime_dataset",
        lambda: (trainset, valset, None, "fake-dataset-source", ["dataset note"]),
    )
    monkeypatch.setattr(
        runner,
        "probe_model_with_openai_client",
        lambda *, api_key, api_base, model_name: _ok_probe(model_name),
    )
    monkeypatch.setattr(runner.gepa, "optimize", fake_optimize)
    monkeypatch.setattr(runner, "create_run_dir", fake_create_run_dir)

    config = _build_config(tmp_path, save_raw_pickle=False)
    result_run_dir = runner.run_gepa_aime_experiment(config)

    assert result_run_dir == run_dir
    assert captured_optimize_kwargs["seed_candidate"] == runner.SEED_PROMPT
    assert captured_optimize_kwargs["trainset"] == trainset
    assert captured_optimize_kwargs["valset"] == valset
    assert captured_optimize_kwargs["task_lm"] == "openai/test-task-model"
    assert captured_optimize_kwargs["reflection_lm"] == "openai/test-reflection-model"
    assert captured_optimize_kwargs["max_metric_calls"] == 3
    assert captured_optimize_kwargs["seed"] == 42

    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "config_resolved.yaml").exists()
    assert (run_dir / "seed_prompt.json").exists()
    assert (run_dir / "optimized_prompt.json").exists()
    assert (run_dir / "gepa_result_summary.json").exists()
    assert (run_dir / "notes.md").exists()
    assert (run_dir / "raw_result.json").exists()
    assert not (run_dir / "raw_result.pkl").exists()

    summary = json.loads((run_dir / "gepa_result_summary.json").read_text(encoding="utf-8"))
    assert summary["raw_result_path"] == "raw_result.json"


def test_runner_skips_pickle_when_to_dict_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run-no-pickle"

    def fake_create_run_dir(_: Path) -> Path:
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    monkeypatch.setattr(
        runner,
        "load_official_aime_dataset",
        lambda: ([{"input": "q1", "answer": "a1"}], [{"input": "q2", "answer": "a2"}], None, "fake-dataset-source", ["dataset note"]),
    )
    monkeypatch.setattr(
        runner,
        "probe_model_with_openai_client",
        lambda *, api_key, api_base, model_name: _ok_probe(model_name),
    )
    monkeypatch.setattr(runner.gepa, "optimize", lambda **kwargs: _FakeResultWithoutDict())
    monkeypatch.setattr(runner, "create_run_dir", fake_create_run_dir)

    config = _build_config(tmp_path, save_raw_pickle=False)
    runner.run_gepa_aime_experiment(config)

    assert not (run_dir / "raw_result.json").exists()
    assert not (run_dir / "raw_result.pkl").exists()

    summary = json.loads((run_dir / "gepa_result_summary.json").read_text(encoding="utf-8"))
    assert summary["raw_result_path"] is None

    notes = (run_dir / "notes.md").read_text(encoding="utf-8")
    assert (
        "raw result was not serialized because result.to_dict() is unavailable and save_raw_pickle=false."
        in notes
    )
