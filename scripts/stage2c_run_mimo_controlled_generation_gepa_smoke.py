from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import gepa


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DEFAULT_BACKEND_FAMILY
from src.logging_utils import create_run_dir, create_timestamp, write_json, write_text
from src.mimo_controlled_generation import ControlledGenerationConfig, controlled_litellm_generation
from src.openai_compatible_utils import build_litellm_model_name, redact_secret, temporary_openai_compatible_env

from scripts.stage2c_run_mimo_controlled_generation_gepa_sanity import (
    DEFAULT_REFLECTION_MODEL,
    DEFAULT_SEED,
    DEFAULT_TASK_MODEL,
    README_QUICKSTART_SEED_PROMPT,
    build_controlled_generation_config,
    build_optimize_kwargs,
    load_dataset_via_stage2c_path,
    _extract_result_summary,
)


DEFAULT_MAX_METRIC_CALLS = 10
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "stage2c_mimo_controlled_generation_gepa_smoke"
PATH_TYPE = "stage2c_mimo_controlled_generation_gepa_smoke"


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def build_input_snapshot(
    *,
    api_base: str,
    task_model: str,
    reflection_model: str,
    optimize_kwargs: dict[str, Any],
    dataset_source: str,
    trainset: list[dict[str, Any]],
    valset: list[dict[str, Any]],
    testset: list[dict[str, Any]] | None,
    execute: bool,
    controlled_generation_config: ControlledGenerationConfig,
) -> dict[str, Any]:
    cg = controlled_generation_config.to_public_dict()
    return {
        "path_type": PATH_TYPE,
        "provider": "mimo",
        "backend_family": DEFAULT_BACKEND_FAMILY,
        "api_base": api_base,
        "task_model": task_model,
        "reflection_model": reflection_model,
        "task_lm": optimize_kwargs["task_lm"],
        "reflection_lm": optimize_kwargs["reflection_lm"],
        "seed_prompt": README_QUICKSTART_SEED_PROMPT,
        "seed_prompt_type": "readme_quickstart_seed_prompt",
        "dataset_source": dataset_source,
        "trainset_size": len(trainset),
        "valset_size": len(valset),
        "testset_size": len(testset) if testset is not None else None,
        "max_metric_calls": optimize_kwargs["max_metric_calls"],
        "seed": optimize_kwargs["seed"],
        "execute_optimize": execute,
        "controlled_generation": {
            "enabled": True,
            "thinking_type": cg["thinking_type"],
            "max_completion_tokens": cg["max_completion_tokens"],
            "timeout_seconds": cg["timeout_seconds"],
        },
        "not_strict_official_path": True,
        "not_performance_claim": True,
        "not_original_same_model_reproduction": True,
        "not_baseline": True,
        "not_pilot": True,
        "no_saved_prompt_eval": True,
    }


def run_stage2c_smoke(
    *,
    api_base: str,
    api_key: str,
    task_model: str,
    reflection_model: str,
    max_metric_calls: int,
    seed: int,
    execute: bool,
    output_root: Path | None = None,
    controlled_generation_config: ControlledGenerationConfig | None = None,
) -> Path:
    if not api_base.strip():
        raise ValueError("Stage 2C smoke 必须显式提供 MIMO_API_BASE 或 --api-base。")
    if not task_model.strip():
        raise ValueError("缺少 task_model。")
    if not reflection_model.strip():
        raise ValueError("缺少 reflection_model。")
    if max_metric_calls <= 0:
        raise ValueError("max_metric_calls 必须大于 0。")
    if execute and not api_key.strip():
        raise ValueError("Stage 2C smoke execute 模式缺少 MIMO_API_KEY。")

    base_output_dir = output_root or DEFAULT_OUTPUT_DIR
    base_output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = create_run_dir(base_output_dir)
    timestamp = create_timestamp()
    trainset, valset, testset, dataset_source = load_dataset_via_stage2c_path()

    config = controlled_generation_config or build_controlled_generation_config(
        model=task_model,
        api_base=api_base,
    )
    optimize_kwargs = build_optimize_kwargs(
        task_model=task_model,
        reflection_model=reflection_model,
        max_metric_calls=max_metric_calls,
        seed=seed,
        trainset=trainset,
        valset=valset,
        run_dir=run_dir,
    )
    snapshot = build_input_snapshot(
        api_base=api_base,
        task_model=task_model,
        reflection_model=reflection_model,
        optimize_kwargs=optimize_kwargs,
        dataset_source=dataset_source,
        trainset=trainset,
        valset=valset,
        testset=testset,
        execute=execute,
        controlled_generation_config=config,
    )
    write_json(run_dir / "stage2c_smoke_input_snapshot.json", snapshot)
    write_text(
        run_dir / "notes.md",
        "\n".join(
            [
                "# Stage 2C MiMo controlled-generation GEPA smoke",
                "",
                f"- 路径类型：`{PATH_TYPE}`",
                "- 路径身份：`non-strict controlled-generation smoke path`",
                "- 说明：本路径不是 strict official path，不构成性能结论，不是 baseline，不是 pilot。",
                f"- provider：`mimo`",
                f"- backend_family：`{DEFAULT_BACKEND_FAMILY}`",
                f"- api_base：`{api_base}`",
                f"- 时间戳：{timestamp}",
                f"- execute_optimize：{execute}",
                f"- dataset_source：{dataset_source}",
                "- 说明：默认只做 dry-run；只有显式 `--execute` 才调用 `gepa.optimize()`。",
                "",
            ]
        ),
    )

    if not execute:
        return run_dir

    result_summary: dict[str, Any] = {
        "run_dir": str(run_dir),
        "path_type": PATH_TYPE,
        "controlled_generation_applied": True,
        "execution_completed": False,
        "not_performance_claim": True,
        "not_baseline": True,
        "not_pilot": True,
    }

    try:
        with temporary_openai_compatible_env(api_key=api_key, api_base=api_base):
            with controlled_litellm_generation(config):
                result = gepa.optimize(**optimize_kwargs)
        result_summary.update(_extract_result_summary(result))
        result_summary["execution_completed"] = True
    except Exception as exc:
        result_summary["error_type"] = type(exc).__name__
        result_summary["error_message"] = redact_secret(str(exc), api_key)

    write_json(run_dir / "stage2c_smoke_result_summary.json", result_summary)
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="运行 Stage 2C MiMo controlled-generation GEPA smoke。默认仅生成 dry-run snapshot，不自动执行 optimize。"
    )
    parser.add_argument("--api-base", default=_env("MIMO_API_BASE"), help="显式 MIMO API Base。")
    parser.add_argument("--task-model", default=_env("TASK_MODEL", DEFAULT_TASK_MODEL), help="任务模型。")
    parser.add_argument(
        "--reflection-model",
        default=_env("REFLECTION_MODEL", DEFAULT_REFLECTION_MODEL),
        help="反思模型。",
    )
    parser.add_argument(
        "--max-metric-calls",
        type=int,
        default=DEFAULT_MAX_METRIC_CALLS,
        help="GEPA max_metric_calls，默认 10。",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="随机种子。")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_DIR),
        help="输出目录，默认 outputs/stage2c_mimo_controlled_generation_gepa_smoke。",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="显式调用 `gepa.optimize()`；默认只做 dry-run。",
    )
    args = parser.parse_args()

    api_key = _env("MIMO_API_KEY")
    run_dir = run_stage2c_smoke(
        api_base=args.api_base,
        api_key=api_key,
        task_model=args.task_model,
        reflection_model=args.reflection_model,
        max_metric_calls=args.max_metric_calls,
        seed=args.seed,
        execute=args.execute,
        output_root=Path(args.output_root).resolve(),
    )
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "path_type": PATH_TYPE,
                "execute_optimize": args.execute,
                "provider": "mimo",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
