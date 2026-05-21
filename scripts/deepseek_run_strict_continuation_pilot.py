from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.deepseek_run_strict_continuation_smoke import (
    README_QUICKSTART_SEED_PROMPT,
    _env,
    _resolve_provider_runtime,
    build_input_snapshot as build_smoke_input_snapshot,
    build_optimize_kwargs,
    load_dataset_via_strict_readme_path,
    redact_secret,
    run_deepseek_strict_continuation_smoke,
    temporary_openai_compatible_env,
)
from src.config import DEFAULT_BACKEND_FAMILY
from src.litellm_error_guard import patch_default_adapter_batch_completion_guard
from src.logging_utils import create_run_dir, create_timestamp, write_json, write_text

import argparse
import gepa


PATH_TYPE = "deepseek_strict_continuation_pilot"
DEFAULT_MAX_METRIC_CALLS = 50
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "deepseek_strict_continuation_pilot"


def build_input_snapshot(
    *,
    provider: str,
    api_base: str,
    task_model: str,
    reflection_model: str,
    optimize_kwargs: dict,
    dataset_source: str,
    trainset: list[dict],
    valset: list[dict],
    testset: list[dict] | None,
    execute: bool,
) -> dict:
    snapshot = build_smoke_input_snapshot(
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
    )
    snapshot["path_type"] = PATH_TYPE
    return snapshot


def run_deepseek_strict_continuation_pilot(
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
        raise ValueError("DeepSeek strict continuation pilot 只允许 provider=deepseek。")
    if not api_base.strip():
        raise ValueError("DeepSeek strict continuation pilot 缺少 DEEPSEEK_API_BASE 或 --api-base。")
    if not task_model.strip():
        raise ValueError("DeepSeek strict continuation pilot 缺少 TASK_MODEL。")
    if not reflection_model.strip():
        raise ValueError("DeepSeek strict continuation pilot 缺少 REFLECTION_MODEL。")
    if max_metric_calls <= 0:
        raise ValueError("max_metric_calls 必须大于 0。")
    if execute and not api_key.strip():
        raise ValueError(f"DeepSeek strict continuation pilot execute 缺少 {api_key_env_name}。")

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
        run_dir / "deepseek_strict_continuation_pilot_input_snapshot.json",
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
                "# DeepSeek strict continuation pilot",
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

    result_summary: dict[str, object] = {
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
        with patch_default_adapter_batch_completion_guard(), temporary_openai_compatible_env(api_key=api_key, api_base=api_base):
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
        result_summary["traceback"] = redact_secret(traceback.format_exc(), api_key)

    write_json(run_dir / "deepseek_strict_continuation_pilot_result_summary.json", result_summary)
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="运行 DeepSeek strict continuation pilot。默认只输出 dry-run snapshot，不自动执行 optimize。"
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
        help="GEPA max_metric_calls，默认 50。",
    )
    parser.add_argument("--seed", type=int, default=42, help="随机种子。")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_DIR),
        help="输出目录，默认 outputs/deepseek_strict_continuation_pilot。",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="显式调用 `gepa.optimize()`；默认只做 dry-run。",
    )
    args = parser.parse_args()

    api_base, api_key, api_key_env_name = _resolve_provider_runtime(args.provider, args.api_base)

    try:
        run_dir = run_deepseek_strict_continuation_pilot(
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
