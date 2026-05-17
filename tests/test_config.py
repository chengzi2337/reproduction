from __future__ import annotations

import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_experiment_config


def _load(relative_path: str):
    return load_experiment_config(PROJECT_ROOT / relative_path, require_api_key=False)


def test_three_yaml_files_can_load(monkeypatch) -> None:
    monkeypatch.setenv("TASK_MODEL", "custom-task-model")
    monkeypatch.setenv("REFLECTION_MODEL", "custom-reflection-model")
    for relative_path in [
        "configs/deepseek_smoke.yaml",
        "configs/deepseek_pilot.yaml",
        "configs/deepseek_official_budget.yaml",
    ]:
        config = _load(relative_path)
        assert config.experiment_name


def test_allow_model_substitution_must_be_false(monkeypatch) -> None:
    monkeypatch.setenv("TASK_MODEL", "task-model-a")
    monkeypatch.setenv("REFLECTION_MODEL", "reflection-model-b")
    for relative_path in [
        "configs/deepseek_smoke.yaml",
        "configs/deepseek_pilot.yaml",
        "configs/deepseek_official_budget.yaml",
    ]:
        assert _load(relative_path).allow_model_substitution is False


def test_reproduction_type_must_be_method_level_reproduction(monkeypatch) -> None:
    monkeypatch.setenv("TASK_MODEL", "task-model-a")
    monkeypatch.setenv("REFLECTION_MODEL", "reflection-model-b")
    for relative_path in [
        "configs/deepseek_smoke.yaml",
        "configs/deepseek_pilot.yaml",
        "configs/deepseek_official_budget.yaml",
    ]:
        assert _load(relative_path).reproduction_type == "method_level_reproduction"


def test_max_metric_calls_must_be_positive_integer(monkeypatch) -> None:
    monkeypatch.setenv("TASK_MODEL", "task-model-a")
    monkeypatch.setenv("REFLECTION_MODEL", "reflection-model-b")
    for relative_path in [
        "configs/deepseek_smoke.yaml",
        "configs/deepseek_pilot.yaml",
        "configs/deepseek_official_budget.yaml",
    ]:
        config = _load(relative_path)
        assert isinstance(config.max_metric_calls, int)
        assert config.max_metric_calls > 0


def test_output_dir_can_be_created(monkeypatch) -> None:
    monkeypatch.setenv("TASK_MODEL", "task-model-a")
    monkeypatch.setenv("REFLECTION_MODEL", "reflection-model-b")
    config = _load("configs/deepseek_smoke.yaml")
    output_dir = config.ensure_output_dir()
    assert output_dir.exists()
    assert output_dir.is_dir()


def test_task_and_reflection_model_can_be_resolved_from_env(monkeypatch) -> None:
    monkeypatch.setenv("TASK_MODEL", "env-task-model")
    monkeypatch.setenv("REFLECTION_MODEL", "env-reflection-model")
    config = _load("configs/deepseek_smoke.yaml")
    assert config.task_model == "env-task-model"
    assert config.reflection_model == "env-reflection-model"


def test_yaml_placeholders_exist() -> None:
    payload = yaml.safe_load((PROJECT_ROOT / "configs/deepseek_smoke.yaml").read_text(encoding="utf-8"))
    assert payload["task_model"] == "${TASK_MODEL}"
    assert payload["reflection_model"] == "${REFLECTION_MODEL}"
