from __future__ import annotations

import argparse
import contextlib
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

from src.config import DEFAULT_BACKEND_FAMILY, DEFAULT_MIMO_API_BASE
from src.logging_utils import create_run_dir, create_timestamp, write_json, write_text
from src.mimo_controlled_generation import ControlledGenerationConfig, controlled_litellm_generation
from src.openai_compatible_utils import (
    build_litellm_model_name,
    redact_secret,
    temporary_openai_compatible_env,
)


README_QUICKSTART_SEED_PROMPT = {
    "system_prompt": "You are a helpful assistant. Answer the question. Put your final answer in the format '### <answer>'"
}
DEFAULT_TASK_MODEL = "mimo-v2.5-pro"
DEFAULT_REFLECTION_MODEL = "mimo-v2.5-pro"
DEFAULT_MAX_METRIC_CALLS = 1
DEFAULT_SEED = 42
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "stage2c_mimo_controlled_generation_gepa_sanity"
PATH_TYPE = "stage2c_mimo_controlled_generation_gepa_sanity"


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _resolve_cached_arrow(dataset_dir_name: str, arrow_filename: str) -> Path:
    cache_root = Path.home() / ".cache" / "huggingface" / "datasets" / dataset_dir_name / "default" / "0.0.0"
    if not cache_root.exists():
        raise RuntimeError(f"未找到本地缓存目录：{cache_root}")
    candidates = sorted(cache_root.glob(f"*/{arrow_filename}"))
    if not candidates:
        raise RuntimeError(f"未找到本地缓存文件：{cache_root / arrow_filename}")
    return candidates[-1]


@contextlib.contextmanager
def _patch_datasets_load_dataset_from_local_cache() -> Any:
    import datasets
    from datasets import Dataset

    original_load_dataset = datasets.load_dataset
    aime_arrow = _resolve_cached_arrow("AI-MO___aimo-validation-aime", "aimo-validation-aime-train.arrow")
    matharena_arrow = _resolve_cached_arrow("MathArena___aime_2025", "aime_2025-train.arrow")

    def _load_dataset(name: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if name == "AI-MO/aimo-validation-aime":
            return {"train": Dataset.from_file(str(aime_arrow))}
        if name == "MathArena/aime_2025":
            return {"train": Dataset.from_file(str(matharena_arrow))}
        return original_load_dataset(name, *args, **kwargs)

    datasets.load_dataset = _load_dataset
    try:
        yield
    finally:
        datasets.load_dataset = original_load_dataset


def load_dataset_via_stage2c_path() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]] | None, str]:
    with _patch_datasets_load_dataset_from_local_cache():
        dataset_result = init_dataset()
    if not isinstance(dataset_result, tuple) or len(dataset_result) not in (2, 3):
        raise RuntimeError("官方 `init_dataset()` 返回结构不符合 Stage 2C 预期。")
    if len(dataset_result) == 3:
        trainset, valset, testset = dataset_result
    else:
        trainset, valset = dataset_result
        testset = None
    return (
        list(trainset),
        list(valset),
        list(testset) if testset is not None else None,
        "gepa.examples.aime.init_dataset() with local cache-backed load_dataset",
    )


def build_controlled_generation_config(
    *,
    model: str,
    api_base: str,
    thinking_type: str = "disabled",
    max_completion_tokens: int = 512,
    timeout_seconds: float = 120.0,
) -> ControlledGenerationConfig:
    return ControlledGenerationConfig(
        model=model,
        api_base=api_base,
        provider="mimo",
        thinking_type=thinking_type,
        max_completion_tokens=max_completion_tokens,
        timeout_seconds=timeout_seconds,
    )


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
        "no_saved_prompt_eval": True,
    }


def _extract_result_summary(result: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    if hasattr(result, "best_idx") and hasattr(result, "val_aggregate_scores"):
        best_idx = getattr(result, "best_idx")
        val_scores = getattr(result, "val_aggregate_scores")
        summary["best_idx"] = best_idx
        try:
            summary["best_score"] = val_scores[best_idx]
        except Exception:
            summary["best_score"] = None
    else:
        summary["best_score"] = getattr(result, "best_score", None)
    summary["total_metric_calls"] = getattr(result, "total_metric_calls", None)
    summary["num_candidates"] = getattr(result, "num_candidates", None)
    summary["num_full_val_evals"] = getattr(result, "num_full_val_evals", None)
    return summary


def run_stage2c_sanity(
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
        raise ValueError("Stage 2C 必须显式提供 MIMO_API_BASE 或 --api-base。")
    if not task_model.strip():
        raise ValueError("缺少 task_model。")
    if not reflection_model.strip():
        raise ValueError("缺少 reflection_model。")
    if max_metric_calls <= 0:
        raise ValueError("max_metric_calls 必须大于 0。")
    if execute and not api_key.strip():
        raise ValueError("Stage 2C execute 模式缺少 MIMO_API_KEY。")

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
    write_json(run_dir / "stage2c_input_snapshot.json", snapshot)
    write_text(
        run_dir / "notes.md",
        "\n".join(
            [
                "# Stage 2C MiMo controlled-generation GEPA sanity",
                "",
                "- 路径类型：`stage2c_mimo_controlled_generation_gepa_sanity`",
                "- 路径身份：`non-strict controlled-generation path`",
                f"- provider：`mimo`",
                f"- backend_family：`{DEFAULT_BACKEND_FAMILY}`",
                f"- api_base：`{api_base}`",
                f"- 时间戳：{timestamp}",
                f"- execute_optimize：{execute}",
                f"- dataset_source：{dataset_source}",
                "- 说明：默认只做 dry-run；只有显式 `--execute` 才调用 `gepa.optimize()`。",
                "- 说明：本路径不是 strict official path，不构成性能结论。",
                "",
            ]
        ),
    )

    if not execute:
        return run_dir

    result_summary: dict[str, Any] = {
        "run_dir": str(run_dir),
        "controlled_generation_applied": True,
        "execution_completed": False,
        "not_performance_claim": True,
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

    write_json(run_dir / "stage2c_result_summary.json", result_summary)
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="运行 Stage 2C MiMo controlled-generation GEPA sanity。默认仅生成 dry-run snapshot，不自动执行 optimize。"
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
        help="GEPA max_metric_calls，默认 1。",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="随机种子。")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_DIR),
        help="输出目录，默认 outputs/stage2c_mimo_controlled_generation_gepa_sanity。",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="显式调用 `gepa.optimize()`；默认只做 dry-run。",
    )
    args = parser.parse_args()

    api_key = _env("MIMO_API_KEY")
    run_dir = run_stage2c_sanity(
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
