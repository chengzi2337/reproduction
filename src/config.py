from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


DEFAULT_DEEPSEEK_API_BASE = "https://api.deepseek.com"
EXPECTED_PROVIDER = "deepseek"
EXPECTED_REPRODUCTION_TYPE = "method_level_reproduction"


def _resolve_env_reference(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], "")
    return value


def _pick_config_or_env(
    raw_config: dict[str, Any],
    key: str,
    env_name: str,
    default: str = "",
) -> str:
    env_value = str(os.getenv(env_name) or "").strip()
    if env_value:
        return env_value
    config_value = _resolve_env_reference(raw_config.get(key))
    if config_value in (None, ""):
        config_value = default
    return str(config_value or "").strip()


@dataclass(slots=True)
class ExperimentConfig:
    experiment_name: str
    reproduction_type: str
    provider: str
    api_base: str
    benchmark: str
    task_model: str
    reflection_model: str
    max_metric_calls: int
    temperature_task: float
    temperature_reflection: float
    seed: int
    output_dir: Path
    allow_model_substitution: bool
    save_raw_pickle: bool
    config_path: Path
    project_root: Path
    api_key: str

    def ensure_output_dir(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "experiment_name": self.experiment_name,
            "reproduction_type": self.reproduction_type,
            "provider": self.provider,
            "api_base": self.api_base,
            "benchmark": self.benchmark,
            "task_model": self.task_model,
            "reflection_model": self.reflection_model,
            "max_metric_calls": self.max_metric_calls,
            "temperature_task": self.temperature_task,
            "temperature_reflection": self.temperature_reflection,
            "seed": self.seed,
            "output_dir": str(self.output_dir),
            "allow_model_substitution": self.allow_model_substitution,
            "save_raw_pickle": self.save_raw_pickle,
            "config_path": str(self.config_path),
        }


def load_yaml_file(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在：{path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"配置文件必须解析为字典：{path}")
    return payload


def load_experiment_config(
    config_path: str | Path,
    *,
    project_root: str | Path | None = None,
    require_api_key: bool = True,
) -> ExperimentConfig:
    load_dotenv()
    path = Path(config_path).resolve()
    raw_config = load_yaml_file(path)
    root = Path(project_root).resolve() if project_root is not None else path.parents[1]

    experiment_name = str(raw_config.get("experiment_name") or "").strip()
    reproduction_type = str(raw_config.get("reproduction_type") or "").strip()
    provider = str(raw_config.get("provider") or "").strip()
    benchmark = str(raw_config.get("benchmark") or "").strip()
    task_model = _pick_config_or_env(raw_config, "task_model", "TASK_MODEL")
    reflection_model = _pick_config_or_env(raw_config, "reflection_model", "REFLECTION_MODEL")
    api_base = _pick_config_or_env(
        raw_config,
        "api_base",
        "DEEPSEEK_API_BASE",
        DEFAULT_DEEPSEEK_API_BASE,
    )
    api_key = str(os.getenv("DEEPSEEK_API_KEY") or "").strip()
    save_raw_pickle = raw_config.get("save_raw_pickle", False)

    if not experiment_name:
        raise ValueError("配置缺少 experiment_name。")
    if reproduction_type != EXPECTED_REPRODUCTION_TYPE:
        raise ValueError(
            f"reproduction_type 必须为 {EXPECTED_REPRODUCTION_TYPE!r}，当前值为 {reproduction_type!r}。"
        )
    if provider != EXPECTED_PROVIDER:
        raise ValueError(f"provider 必须为 {EXPECTED_PROVIDER!r}，当前值为 {provider!r}。")
    if benchmark != "aime":
        raise ValueError(f"当前第一阶段只支持 AIME，收到 benchmark={benchmark!r}。")
    if not task_model:
        raise ValueError("缺少 TASK_MODEL。请通过环境变量或 YAML 配置 task_model。")
    if not reflection_model:
        raise ValueError("缺少 REFLECTION_MODEL。请通过环境变量或 YAML 配置 reflection_model。")
    if require_api_key and not api_key:
        raise ValueError("缺少 DEEPSEEK_API_KEY 环境变量。真实 key 只能从环境变量读取。")

    max_metric_calls = raw_config.get("max_metric_calls")
    if not isinstance(max_metric_calls, int) or max_metric_calls <= 0:
        raise ValueError("max_metric_calls 必须是大于 0 的整数。")

    seed = raw_config.get("seed", 42)
    if not isinstance(seed, int):
        raise ValueError("seed 必须是整数。")

    allow_model_substitution = raw_config.get("allow_model_substitution")
    if allow_model_substitution is not False:
        raise ValueError("第一阶段必须保持 allow_model_substitution=false。")
    if not isinstance(save_raw_pickle, bool):
        raise ValueError("save_raw_pickle 必须是布尔值。")

    temperature_task = float(raw_config.get("temperature_task", 0.0))
    temperature_reflection = float(raw_config.get("temperature_reflection", 0.7))

    output_dir_value = str(raw_config.get("output_dir") or "").strip()
    if not output_dir_value:
        raise ValueError("配置缺少 output_dir。")
    output_dir = (root / output_dir_value).resolve()

    return ExperimentConfig(
        experiment_name=experiment_name,
        reproduction_type=reproduction_type,
        provider=provider,
        api_base=api_base,
        benchmark=benchmark,
        task_model=task_model,
        reflection_model=reflection_model,
        max_metric_calls=max_metric_calls,
        temperature_task=temperature_task,
        temperature_reflection=temperature_reflection,
        seed=seed,
        output_dir=output_dir,
        allow_model_substitution=allow_model_substitution,
        save_raw_pickle=save_raw_pickle,
        config_path=path,
        project_root=root,
        api_key=api_key,
    )
