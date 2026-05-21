from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any

import gepa
from gepa.examples.aime import init_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DEFAULT_BACKEND_FAMILY, get_provider_settings
from src.logging_utils import create_run_dir, create_timestamp, write_json, write_text
from src.openai_compatible_utils import (
    build_litellm_model_name,
    redact_secret,
    temporary_openai_compatible_env,
)


README_QUICKSTART_SEED_PROMPT = {
    "system_prompt": "You are a helpful assistant. Answer the question. Put your final answer in the format '### <answer>'"
}

PATH_TYPE = "deepseek_strict_continuation_smoke"
DEFAULT_MAX_METRIC_CALLS = 10
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "deepseek_strict_continuation_smoke"


def load_dataset_via_strict_readme_path() -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]] | None,
    str,
]:
    dataset_source = f"{inspect.getsourcefile(init_dataset)}:{inspect.getsourcelines(init_dataset)[1]}"
    dataset_result = init_dataset()
    if not isinstance(dataset_result, tuple) or len(dataset_result) not in (2, 3):
        raise RuntimeError("官方 `init_dataset()` 返回结构不符合 DeepSeek strict continuation smoke 预期。")

    if len(dataset_result) == 3:
        trainset, valset, testset = dataset_result
    else:
        trainset, valset = dataset_result
        testset = None

    return list(trainset), list(valset), list(testset) if testset is not None else None, dataset_source


def build_optimize_kwargs(
    *,
    task_model: str,
    reflection_model: str,
    max_metric_calls: int,
    seed: int,
    trainset: list[dict[str, Any]],
    valset: list[dict[str, Any]],
    run_dir: Path,
) -> dict[str, Any]:
    return {
        "seed_candidate": README_QUICKSTART_SEED_PROMPT,
        "trainset": trainset,
        "valset": valset,
        "task_lm": build_litellm_model_name(task_model),
        "reflection_lm": build_litellm_model_name(reflection_model),
        "max_metric_calls": max_metric_calls,
        "seed": seed,
        "run_dir": str(run_dir),
    }


def build_input_snapshot(
    *,
    provider: str,
    api_base: str,
    task_model: str,
    reflection_model: str,
    optimize_kwargs: dict[str, Any],
    dataset_source: str,
    trainset: list[dict[str, Any]],
    valset: list[dict[str, Any]],
    testset: list[dict[str, Any]] | None,
    execute: bool,
) -> dict[str, Any]:
    return {
        "path_type": PATH_TYPE,
        "continuation_track": "deepseek_strict_readme_continuation",
        "provider": provider,
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
        "not_stage1_rewrite": True,
        "not_same_model_reproduction": True,
        "not_official_budget": True,
        "not_paper_level_claim": True,
    }


def run_deepseek_strict_continuation_smoke(
    *,
    provider: str,
    api_base: str,
    api_key: str,
    api_key_env_name: str,
    task_model: str,
    reflection_model: str,
    max_metric_calls: int,
    seed: int,
    execute: bool,
    output_root: Path | None = None,
) -> Path:
    if provider.strip() != "deepseek":
        raise ValueError("DeepSeek strict continuation smoke 只允许 provider=deepseek。")
    if not api_base.strip():
        raise ValueError("DeepSeek strict continuation smoke 缺少 DEEPSEEK_API_BASE 或 --api-base。")
    if not task_model.strip():
        raise ValueError("DeepSeek strict continuation smoke 缺少 TASK_MODEL。")
    if not reflection_model.strip():
        raise ValueError("DeepSeek strict continuation smoke 缺少 REFLECTION_MODEL。")
    if max_metric_calls <= 0:
        raise ValueError("max_metric_calls 必须大于 0。")
    if execute and not api_key.strip():
        raise ValueError(f"DeepSeek strict continuation smoke execute 缺少 {api_key_env_name}。")

    base_output_dir = output_root or DEFAULT_OUTPUT_DIR
    base_output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = create_run_dir(base_output_dir)
    timestamp = create_timestamp()

    trainset, valset, testset, dataset_source = load_dataset_via_strict_readme_path()
    optimize_kwargs = build_optimize_kwargs(
        task_model=task_model,
        reflection_model=reflection_model,
        max_metric_calls=max_metric_calls,
        seed=seed,
        trainset=trainset,
        valset=valset,
        run_dir=run_dir,
    )

    write_json(
        run_dir / "deepseek_strict_continuation_smoke_input_snapshot.json",
        build_input_snapshot(
            provider=provider,
            api_base=api_base,
            task_model=task_model,
            reflection_model=reflection_model,
            optimize_kwargs=optimize_kwargs,
            dataset_source=dataset_source,
            trainset=trainset,
            valset=valset,
            testset=testset,
            execute=execute,
        ),
    )
    write_text(
        run_dir / "notes.md",
        "\n".join(
            [
                "# DeepSeek strict continuation smoke",
                "",
                f"- 路径类型：`{PATH_TYPE}`",
                "- 路径身份：`DeepSeek strict-readme continuation`",
                "- 说明：该路径不是 Stage 1 历史结果改写，不是 same-model reproduction，不是 official_budget。",
                f"- provider：`{provider}`",
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
        "continuation_track": "deepseek_strict_readme_continuation",
        "execution_completed": False,
        "not_stage1_rewrite": True,
        "not_same_model_reproduction": True,
        "not_official_budget": True,
        "not_paper_level_claim": True,
    }

    try:
        with temporary_openai_compatible_env(api_key=api_key, api_base=api_base):
            result = gepa.optimize(**optimize_kwargs)
        best_idx = result.best_idx
        best_score = result.val_aggregate_scores[best_idx]
        result_summary.update(
            {
                "best_idx": best_idx,
                "best_score": best_score,
                "total_metric_calls": result.total_metric_calls,
                "num_candidates": result.num_candidates,
                "num_val_instances": result.num_val_instances,
                "num_full_val_evals": result.num_full_val_evals,
                "execution_completed": True,
            }
        )
    except Exception as exc:
        result_summary["error_type"] = type(exc).__name__
        result_summary["error_message"] = redact_secret(str(exc), api_key)

    write_json(run_dir / "deepseek_strict_continuation_smoke_result_summary.json", result_summary)
    return run_dir


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _resolve_provider_runtime(provider: str, explicit_api_base: str = "") -> tuple[str, str, str]:
    settings = get_provider_settings(provider)
    api_base = explicit_api_base.strip() or _env(
        settings["api_base_env"],
        settings["default_api_base"],
    )
    api_key_env_name = settings["api_key_env"]
    api_key = _env(api_key_env_name)
    return api_base, api_key, api_key_env_name


def main() -> None:
    parser = argparse.ArgumentParser(
        description="运行 DeepSeek strict continuation smoke。默认只输出 dry-run snapshot，不自动执行 optimize。"
    )
    parser.add_argument("--provider", default="deepseek", help="固定为 deepseek。")
    parser.add_argument("--api-base", default="", help="显式 DeepSeek API Base。")
    parser.add_argument("--task-model", default=_env("TASK_MODEL"), help="任务模型名，默认读取 TASK_MODEL。")
    parser.add_argument(
        "--reflection-model",
        default=_env("REFLECTION_MODEL"),
        help="反思模型名，默认读取 REFLECTION_MODEL。",
    )
    parser.add_argument(
        "--max-metric-calls",
        type=int,
        default=DEFAULT_MAX_METRIC_CALLS,
        help="GEPA max_metric_calls，默认 10。",
    )
    parser.add_argument("--seed", type=int, default=42, help="随机种子。")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_DIR),
        help="输出目录，默认 outputs/deepseek_strict_continuation_smoke。",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="显式调用 `gepa.optimize()`；默认只做 dry-run。",
    )
    args = parser.parse_args()

    api_base, api_key, api_key_env_name = _resolve_provider_runtime(args.provider, args.api_base)

    try:
        run_dir = run_deepseek_strict_continuation_smoke(
            provider=args.provider,
            api_base=api_base,
            api_key=api_key,
            api_key_env_name=api_key_env_name,
            task_model=args.task_model,
            reflection_model=args.reflection_model,
            max_metric_calls=args.max_metric_calls,
            seed=args.seed,
            execute=args.execute,
            output_root=Path(args.output_root).resolve(),
        )
    except Exception as exc:
        print(redact_secret(str(exc), api_key), file=sys.stderr)
        raise

    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "execute_optimize": args.execute,
                "path_type": PATH_TYPE,
                "provider": args.provider,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
