from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (
    DEFAULT_MIMO_API_BASE,
    load_experiment_config,
)


def _load(relative_path: str):
    return load_experiment_config(PROJECT_ROOT / relative_path, require_api_key=False)


def test_five_yaml_files_can_load(monkeypatch) -> None:
    monkeypatch.setenv("TASK_MODEL", "custom-task-model")
    monkeypatch.setenv("REFLECTION_MODEL", "custom-reflection-model")
    for relative_path in [
        "configs/deepseek_smoke.yaml",
        "configs/deepseek_pilot.yaml",
        "configs/deepseek_official_budget.yaml",
        "configs/mimo_smoke.yaml",
        "configs/mimo_pilot.yaml",
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
        "configs/mimo_smoke.yaml",
        "configs/mimo_pilot.yaml",
    ]:
        assert _load(relative_path).allow_model_substitution is False


def test_save_raw_pickle_defaults_to_false(monkeypatch) -> None:
    monkeypatch.setenv("TASK_MODEL", "task-model-a")
    monkeypatch.setenv("REFLECTION_MODEL", "reflection-model-b")
    for relative_path in [
        "configs/deepseek_smoke.yaml",
        "configs/deepseek_pilot.yaml",
        "configs/deepseek_official_budget.yaml",
        "configs/mimo_smoke.yaml",
        "configs/mimo_pilot.yaml",
    ]:
        assert _load(relative_path).save_raw_pickle is False


def test_reproduction_type_must_be_method_level_reproduction(monkeypatch) -> None:
    monkeypatch.setenv("TASK_MODEL", "task-model-a")
    monkeypatch.setenv("REFLECTION_MODEL", "reflection-model-b")
    for relative_path in [
        "configs/deepseek_smoke.yaml",
        "configs/deepseek_pilot.yaml",
        "configs/deepseek_official_budget.yaml",
        "configs/mimo_smoke.yaml",
        "configs/mimo_pilot.yaml",
    ]:
        assert _load(relative_path).reproduction_type == "method_level_reproduction"


def test_max_metric_calls_must_be_positive_integer(monkeypatch) -> None:
    monkeypatch.setenv("TASK_MODEL", "task-model-a")
    monkeypatch.setenv("REFLECTION_MODEL", "reflection-model-b")
    for relative_path in [
        "configs/deepseek_smoke.yaml",
        "configs/deepseek_pilot.yaml",
        "configs/deepseek_official_budget.yaml",
        "configs/mimo_smoke.yaml",
        "configs/mimo_pilot.yaml",
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


def test_deepseek_provider_reads_provider_specific_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("DEEPSEEK_API_BASE", "https://deepseek-env.example.com")
    config_path = tmp_path / "deepseek-config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "experiment_name: x",
                "reproduction_type: method_level_reproduction",
                "provider: deepseek",
                "backend_family: openai_compatible",
                "api_base: https://api.deepseek.com",
                "benchmark: aime",
                "task_model: deepseek-v4-flash",
                "reflection_model: deepseek-v4-pro",
                "max_metric_calls: 1",
                "temperature_task: 0.0",
                "temperature_reflection: 0.7",
                "seed: 42",
                "output_dir: outputs/tmp",
                "allow_model_substitution: false",
                "save_raw_pickle: false",
            ]
        ),
        encoding="utf-8",
    )
    config = load_experiment_config(config_path, project_root=PROJECT_ROOT)
    assert config.provider == "deepseek"
    assert config.api_key == "deepseek-key"
    assert config.api_base == "https://deepseek-env.example.com"


def test_mimo_provider_reads_provider_specific_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIMO_API_KEY", "mimo-key")
    monkeypatch.setenv("MIMO_API_BASE", "https://mimo-env.example.com/v1")
    config_path = tmp_path / "mimo-config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "experiment_name: x",
                "reproduction_type: method_level_reproduction",
                "provider: mimo",
                "backend_family: openai_compatible",
                "api_base: https://api.xiaomimimo.com/v1",
                "benchmark: aime",
                "task_model: mimo-v2-flash",
                "reflection_model: mimo-v2.5-pro",
                "max_metric_calls: 1",
                "temperature_task: null",
                "temperature_reflection: null",
                "thinking_task: disabled",
                "thinking_reflection: provider_default",
                "seed: 42",
                "output_dir: outputs/tmp",
                "allow_model_substitution: false",
                "save_raw_pickle: false",
            ]
        ),
        encoding="utf-8",
    )
    config = load_experiment_config(config_path, project_root=PROJECT_ROOT)
    assert config.provider == "mimo"
    assert config.api_key == "mimo-key"
    assert config.api_base == "https://mimo-env.example.com/v1"


def test_mimo_provider_uses_default_api_base(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("MIMO_API_BASE", raising=False)
    config_path = tmp_path / "mimo-config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "experiment_name: x",
                "reproduction_type: method_level_reproduction",
                "provider: mimo",
                "backend_family: openai_compatible",
                "benchmark: aime",
                "task_model: mimo-v2-flash",
                "reflection_model: mimo-v2.5-pro",
                "max_metric_calls: 1",
                "temperature_task: null",
                "temperature_reflection: null",
                "seed: 42",
                "output_dir: outputs/tmp",
                "allow_model_substitution: false",
                "save_raw_pickle: false",
            ]
        ),
        encoding="utf-8",
    )
    config = load_experiment_config(config_path, project_root=PROJECT_ROOT, require_api_key=False)
    assert config.api_base == DEFAULT_MIMO_API_BASE


def test_mimo_config_allows_null_temperature(monkeypatch) -> None:
    monkeypatch.delenv("TASK_MODEL", raising=False)
    monkeypatch.delenv("REFLECTION_MODEL", raising=False)
    config = _load("configs/mimo_smoke.yaml")
    assert config.temperature_task is None
    assert config.temperature_reflection is None
    public_dict = config.to_public_dict()
    assert public_dict["temperature_task"] is None
    assert public_dict["temperature_reflection"] is None


def test_allow_model_substitution_not_false_raises(tmp_path) -> None:
    config_path = tmp_path / "bad-config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "experiment_name: x",
                "reproduction_type: method_level_reproduction",
                "provider: mimo",
                "backend_family: openai_compatible",
                "benchmark: aime",
                "task_model: mimo-v2-flash",
                "reflection_model: mimo-v2.5-pro",
                "max_metric_calls: 1",
                "temperature_task: null",
                "temperature_reflection: null",
                "seed: 42",
                "output_dir: outputs/tmp",
                "allow_model_substitution: true",
                "save_raw_pickle: false",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="allow_model_substitution=false"):
        load_experiment_config(config_path, project_root=PROJECT_ROOT, require_api_key=False)


def test_benchmark_non_aime_raises(tmp_path) -> None:
    config_path = tmp_path / "bad-config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "experiment_name: x",
                "reproduction_type: method_level_reproduction",
                "provider: mimo",
                "backend_family: openai_compatible",
                "benchmark: gsm8k",
                "task_model: mimo-v2-flash",
                "reflection_model: mimo-v2.5-pro",
                "max_metric_calls: 1",
                "temperature_task: null",
                "temperature_reflection: null",
                "seed: 42",
                "output_dir: outputs/tmp",
                "allow_model_substitution: false",
                "save_raw_pickle: false",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="AIME"):
        load_experiment_config(config_path, project_root=PROJECT_ROOT, require_api_key=False)


def test_yaml_placeholders_exist() -> None:
    payload = yaml.safe_load((PROJECT_ROOT / "configs/deepseek_smoke.yaml").read_text(encoding="utf-8"))
    assert payload["task_model"] == "${TASK_MODEL}"
    assert payload["reflection_model"] == "${REFLECTION_MODEL}"
