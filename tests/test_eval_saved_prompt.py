from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ExperimentConfig


SPEC = importlib.util.spec_from_file_location(
    "eval_saved_prompt_script",
    PROJECT_ROOT / "scripts" / "05_eval_saved_prompt.py",
)
assert SPEC is not None and SPEC.loader is not None
eval_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(eval_script)


def _build_config(run_dir: Path) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_name="pilot",
        reproduction_type="method_level_reproduction",
        provider="deepseek",
        api_base="https://api.deepseek.com",
        benchmark="aime",
        task_model="deepseek-v4-flash",
        reflection_model="deepseek-v4-pro",
        max_metric_calls=50,
        temperature_task=0.0,
        temperature_reflection=0.7,
        seed=42,
        output_dir=run_dir.parent,
        allow_model_substitution=False,
        save_raw_pickle=False,
        config_path=run_dir / "config_resolved.yaml",
        project_root=PROJECT_ROOT,
        api_key="fake-key",
    )


def test_saved_prompt_eval_writes_auditable_summary(tmp_path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "notes.md").write_text("# notes\n", encoding="utf-8")

    monkeypatch.setattr(
        eval_script,
        "load_experiment_config",
        lambda *args, **kwargs: _build_config(run_dir),
    )
    monkeypatch.setattr(
        eval_script,
        "load_prompt_candidate",
        lambda path: {"system_prompt": f"loaded-from-{Path(path).name}"},
    )
    monkeypatch.setattr(
        eval_script,
        "load_official_aime_dataset",
        lambda: (
            [{"input": "train-q", "answer": "1"}],
            [{"input": "val-q", "answer": "2"}],
            [{"input": "test-q", "answer": "3"}],
            None,
            [],
        ),
    )

    def fake_evaluate_candidate(**kwargs):
        prompt_version = kwargs["prompt_version"]
        score = 0.25 if prompt_version == "seed" else 0.75
        return (
            [
                {
                    "sample_id": f"{prompt_version}-1",
                    "prompt_version": prompt_version,
                    "question": "q",
                    "prediction": "p",
                    "gold": "g",
                    "score": score,
                    "error": None,
                }
            ],
            {
                "split": kwargs["split_name"],
                "eval_model": kwargs["task_model"],
                "num_examples": 1,
                "evaluated_sample_count": 1,
                "average_score": score,
                "num_errors": 0,
            },
        )

    monkeypatch.setattr(eval_script, "evaluate_candidate", fake_evaluate_candidate)
    monkeypatch.setattr(eval_script, "create_timestamp", lambda: "20260517T160000+0800")
    monkeypatch.setattr(sys, "argv", ["05_eval_saved_prompt.py", "--run-dir", str(run_dir)])

    eval_script.main()

    summary = json.loads((run_dir / "saved_prompt_eval_summary.json").read_text(encoding="utf-8"))
    assert summary["split"] == "test"
    assert summary["split_label"] == "test split"
    assert summary["eval_model"] == "deepseek-v4-flash"
    assert summary["eval_timestamp"] == "20260517T160000+0800"
    assert summary["evaluated_sample_count"] == 1
    assert summary["seed_prompt_score"] == 0.25
    assert summary["optimized_prompt_score"] == 0.75
    assert summary["score_delta"] == 0.5

    records = (run_dir / "per_example_eval.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(records) == 2


def test_saved_prompt_eval_records_validation_sanity_check_note(tmp_path, monkeypatch) -> None:
    run_dir = tmp_path / "run-val"
    run_dir.mkdir()
    (run_dir / "notes.md").write_text("# notes\n", encoding="utf-8")

    monkeypatch.setattr(
        eval_script,
        "load_experiment_config",
        lambda *args, **kwargs: _build_config(run_dir),
    )
    monkeypatch.setattr(
        eval_script,
        "load_prompt_candidate",
        lambda path: {"system_prompt": f"loaded-from-{Path(path).name}"},
    )
    monkeypatch.setattr(
        eval_script,
        "load_official_aime_dataset",
        lambda: (
            [{"input": "train-q", "answer": "1"}],
            [{"input": "val-q", "answer": "2"}],
            None,
            None,
            [],
        ),
    )
    monkeypatch.setattr(
        eval_script,
        "evaluate_candidate",
        lambda **kwargs: (
            [],
            {
                "split": kwargs["split_name"],
                "eval_model": kwargs["task_model"],
                "num_examples": 0,
                "evaluated_sample_count": 0,
                "average_score": 0.0,
                "num_errors": 0,
            },
        ),
    )
    monkeypatch.setattr(eval_script, "create_timestamp", lambda: "20260517T160500+0800")
    monkeypatch.setattr(sys, "argv", ["05_eval_saved_prompt.py", "--run-dir", str(run_dir)])

    eval_script.main()

    summary = json.loads((run_dir / "saved_prompt_eval_summary.json").read_text(encoding="utf-8"))
    assert summary["split"] == "val"
    assert summary["split_label"] == "validation sanity check only"

    notes = (run_dir / "notes.md").read_text(encoding="utf-8")
    assert "validation sanity check only" in notes
