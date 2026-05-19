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

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "strict_readme_quickstart_path"


def load_dataset_via_strict_readme_path() -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]] | None,
    str,
]:
    dataset_source = f"{inspect.getsourcefile(init_dataset)}:{inspect.getsourcelines(init_dataset)[1]}"
    dataset_result = init_dataset()
    if not isinstance(dataset_result, tuple) or len(dataset_result) not in (2, 3):
        raise RuntimeError("官方 `init_dataset()` 返回结构不符合 strict README quickstart 路径预期。")

    if len(dataset_result) == 3:
        trainset, valset, testset = dataset_result
    else:
        trainset, valset = dataset_result
        testset = None

    return list(trainset), list(valset), list(testset) if testset is not None else None, dataset_source


def build_strict_optimize_kwargs(
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
    backend_family: str,
    api_base: str,
    dataset_source: str,
    task_model: str,
    reflection_model: str,
    optimize_kwargs: dict[str, Any],
    trainset: list[dict[str, Any]],
    valset: list[dict[str, Any]],
    testset: list[dict[str, Any]] | None,
    execute: bool,
) -> dict[str, Any]:
    return {
        "path_type": "strict_readme_quickstart_path",
        "provider": provider,
        "backend_family": backend_family,
        "api_base": api_base,
        "dataset_source": dataset_source,
        "task_model": task_model,
        "reflection_model": reflection_model,
        "task_lm": optimize_kwargs["task_lm"],
        "reflection_lm": optimize_kwargs["reflection_lm"],
        "max_metric_calls": optimize_kwargs["max_metric_calls"],
        "seed": optimize_kwargs["seed"],
        "trainset_size": len(trainset),
        "valset_size": len(valset),
        "testset_size": len(testset) if testset is not None else None,
        "seed_candidate": optimize_kwargs["seed_candidate"],
        "execute_optimize": execute,
    }


def run_strict_readme_quickstart_path(
    *,
    provider: str,
    task_model: str,
    reflection_model: str,
    max_metric_calls: int,
    seed: int,
    api_base: str,
    api_key: str,
    api_key_env_name: str,
    execute: bool,
    output_root: Path | None = None,
) -> Path:
    if not provider.strip():
        raise ValueError("缺少 provider。")
    if not task_model.strip():
        raise ValueError("缺少 TASK_MODEL。")
    if not reflection_model.strip():
        raise ValueError("缺少 REFLECTION_MODEL。")
    if max_metric_calls <= 0:
        raise ValueError("max_metric_calls 必须大于 0。")

    base_output_dir = output_root or DEFAULT_OUTPUT_DIR
    base_output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = create_run_dir(base_output_dir)
    timestamp = create_timestamp()

    trainset, valset, testset, dataset_source = load_dataset_via_strict_readme_path()
    optimize_kwargs = build_strict_optimize_kwargs(
        task_model=task_model,
        reflection_model=reflection_model,
        max_metric_calls=max_metric_calls,
        seed=seed,
        trainset=trainset,
        valset=valset,
        run_dir=run_dir,
    )

    write_json(
        run_dir / "strict_input_snapshot.json",
        build_input_snapshot(
            provider=provider,
            backend_family=DEFAULT_BACKEND_FAMILY,
            api_base=api_base,
            dataset_source=dataset_source,
            task_model=task_model,
            reflection_model=reflection_model,
            optimize_kwargs=optimize_kwargs,
            trainset=trainset,
            valset=valset,
            testset=testset,
            execute=execute,
        ),
    )
    write_json(run_dir / "strict_seed_prompt.json", README_QUICKSTART_SEED_PROMPT)
    write_text(
        run_dir / "notes.md",
        "\n".join(
            [
                "# strict README quickstart path",
                "",
                "- 路径类型：`strict_readme_quickstart_path`",
                "- 项目身份：`GEPA method-level reproduction`",
                f"- provider：`{provider}`",
                f"- backend_family：`{DEFAULT_BACKEND_FAMILY}`",
                f"- api_base：`{api_base}`",
                f"- 时间戳：{timestamp}",
                f"- execute_optimize：{execute}",
                f"- dataset_source：{dataset_source}",
                "- 说明：该脚本默认只输出 input snapshot；显式 `--execute` 才调用 `gepa.optimize()`。",
                "",
            ]
        ),
    )

    if not execute:
        return run_dir

    if not api_key.strip():
        raise ValueError(f"执行 strict README quickstart path 时缺少 {api_key_env_name}。")

    with temporary_openai_compatible_env(api_key=api_key, api_base=api_base):
        result = gepa.optimize(**optimize_kwargs)

    best_idx = result.best_idx
    best_score = result.val_aggregate_scores[best_idx]
    write_json(
        run_dir / "strict_result_summary.json",
        {
            "best_idx": best_idx,
            "best_score": best_score,
            "total_metric_calls": result.total_metric_calls,
            "num_candidates": result.num_candidates,
            "num_val_instances": result.num_val_instances,
            "num_full_val_evals": result.num_full_val_evals,
        },
    )
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
        description="执行 strict README quickstart path；默认只输出 input snapshot，不调用模型。"
    )
    parser.add_argument(
        "--provider",
        default=_env("PROVIDER", "deepseek"),
        help="provider，支持 deepseek / mimo；默认读取 PROVIDER 或使用 deepseek。",
    )
    parser.add_argument("--task-model", default=_env("TASK_MODEL"), help="任务模型名，默认读取 TASK_MODEL。")
    parser.add_argument(
        "--reflection-model",
        default=_env("REFLECTION_MODEL"),
        help="反思模型名，默认读取 REFLECTION_MODEL。",
    )
    parser.add_argument(
        "--api-base",
        default="",
        help="OpenAI-compatible API base；默认按 provider 读取对应环境变量。",
    )
    parser.add_argument(
        "--max-metric-calls",
        type=int,
        default=10,
        help="GEPA max_metric_calls。默认 10；建议先用极小预算做 sanity run。",
    )
    parser.add_argument("--seed", type=int, default=42, help="随机种子。")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_DIR),
        help="输出根目录。默认 outputs/strict_readme_quickstart_path。",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="显式调用 `gepa.optimize()`；默认只写 input snapshot。",
    )
    args = parser.parse_args()

    api_base, api_key, api_key_env_name = _resolve_provider_runtime(args.provider, args.api_base)

    try:
        run_dir = run_strict_readme_quickstart_path(
            provider=args.provider,
            task_model=args.task_model,
            reflection_model=args.reflection_model,
            max_metric_calls=args.max_metric_calls,
            seed=args.seed,
            api_base=api_base,
            api_key=api_key,
            api_key_env_name=api_key_env_name,
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
                "path_type": "strict_readme_quickstart_path",
                "provider": args.provider,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
