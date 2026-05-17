from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_experiment_config
from src.deepseek_utils import build_litellm_model_name


def test_core_code_does_not_hardcode_example_models() -> None:
    disallowed_literals = {"deepseek-v4-flash", "deepseek-v4-pro"}
    for path in (PROJECT_ROOT / "src").rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert all(literal not in content for literal in disallowed_literals), f"发现核心代码硬编码模型：{path}"


def test_model_name_must_come_from_config_or_env(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TASK_MODEL", raising=False)
    monkeypatch.delenv("REFLECTION_MODEL", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "experiment_name: x",
                "reproduction_type: method_level_reproduction",
                "provider: deepseek",
                "api_base: https://api.deepseek.com",
                "benchmark: aime",
                "task_model: model-from-config",
                "reflection_model: reflection-from-config",
                "max_metric_calls: 1",
                "temperature_task: 0.0",
                "temperature_reflection: 0.7",
                "seed: 42",
                "output_dir: outputs/tmp",
                "allow_model_substitution: false",
            ]
        ),
        encoding="utf-8",
    )
    config = load_experiment_config(config_path, project_root=PROJECT_ROOT, require_api_key=False)
    assert config.task_model == "model-from-config"
    assert config.reflection_model == "reflection-from-config"


def test_missing_task_or_reflection_model_raises_clear_error(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TASK_MODEL", raising=False)
    monkeypatch.delenv("REFLECTION_MODEL", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "experiment_name: x",
                "reproduction_type: method_level_reproduction",
                "provider: deepseek",
                "api_base: https://api.deepseek.com",
                "benchmark: aime",
                "task_model: ${TASK_MODEL}",
                "reflection_model: ${REFLECTION_MODEL}",
                "max_metric_calls: 1",
                "temperature_task: 0.0",
                "temperature_reflection: 0.7",
                "seed: 42",
                "output_dir: outputs/tmp",
                "allow_model_substitution: false",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="TASK_MODEL|REFLECTION_MODEL"):
        load_experiment_config(config_path, project_root=PROJECT_ROOT, require_api_key=False)


def test_environment_variables_override_yaml_placeholders(monkeypatch) -> None:
    monkeypatch.setenv("TASK_MODEL", "overridden-task")
    monkeypatch.setenv("REFLECTION_MODEL", "overridden-reflection")
    config = load_experiment_config(
        PROJECT_ROOT / "configs/deepseek_smoke.yaml",
        require_api_key=False,
    )
    assert config.task_model == "overridden-task"
    assert config.reflection_model == "overridden-reflection"


def test_no_automatic_model_substitution(monkeypatch) -> None:
    monkeypatch.setenv("TASK_MODEL", "user-specified-task")
    monkeypatch.setenv("REFLECTION_MODEL", "user-specified-reflection")
    config = load_experiment_config(
        PROJECT_ROOT / "configs/deepseek_smoke.yaml",
        require_api_key=False,
    )
    assert config.task_model == "user-specified-task"
    assert config.reflection_model == "user-specified-reflection"
    assert config.allow_model_substitution is False


def test_build_litellm_model_name_uses_standard_openai_prefix() -> None:
    assert build_litellm_model_name("deepseek-v4-flash") == "openai/deepseek-v4-flash"
    assert build_litellm_model_name("openai/deepseek-v4-flash") == "openai/deepseek-v4-flash"


def test_runner_uses_official_string_model_path() -> None:
    runner_path = PROJECT_ROOT / "src" / "gepa_official_runner.py"
    content = runner_path.read_text(encoding="utf-8")
    assert "task_lm=task_model_name" in content
    assert "reflection_lm=reflection_model_name" in content
    assert "make_task_lm_callable" not in content
    assert "make_reflection_lm_callable" not in content


def test_eval_uses_default_adapter_with_model_string() -> None:
    eval_utils_path = PROJECT_ROOT / "src" / "eval_utils.py"
    content = eval_utils_path.read_text(encoding="utf-8")
    assert "DefaultAdapter(model=build_litellm_model_name(task_model))" in content
