from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path
from typing import Any

import gepa


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ExperimentConfig, load_experiment_config
from src.deepseek_utils import build_litellm_model_name, redact_secret, temporary_openai_compatible_env
from src.gepa_official_runner import SEED_PROMPT
from src.logging_utils import append_text, create_run_dir, create_timestamp, write_json, write_text


def load_dataset_via_direct_official_path() -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]] | None,
    str,
]:
    examples = getattr(gepa, "examples", None)
    aime_module = getattr(examples, "aime", None) if examples is not None else None
    init_dataset = getattr(aime_module, "init_dataset", None) if aime_module is not None else None
    if not callable(init_dataset):
        raise RuntimeError("当前 GEPA 安装未直接暴露 `gepa.examples.aime.init_dataset()`，无法执行最小官方路径校验。")

    dataset_source = f"{inspect.getsourcefile(init_dataset)}:{inspect.getsourcelines(init_dataset)[1]}"
    dataset_result = init_dataset()
    if not isinstance(dataset_result, tuple) or len(dataset_result) not in (2, 3):
        raise RuntimeError("官方 `init_dataset()` 返回结构不符合当前最小校验脚本预期。")

    if len(dataset_result) == 3:
        trainset, valset, testset = dataset_result
    else:
        trainset, valset = dataset_result
        testset = None

    return list(trainset), list(valset), list(testset) if testset is not None else None, dataset_source


def build_core_optimize_kwargs(
    *,
    config: ExperimentConfig,
    trainset: list[dict[str, Any]],
    valset: list[dict[str, Any]],
    run_dir: Path,
) -> dict[str, Any]:
    return {
        "seed_candidate": SEED_PROMPT,
        "trainset": trainset,
        "valset": valset,
        "task_lm": build_litellm_model_name(config.task_model),
        "reflection_lm": build_litellm_model_name(config.reflection_model),
        "max_metric_calls": config.max_metric_calls,
        "seed": config.seed,
        "run_dir": str(run_dir),
    }


def _build_core_snapshot(
    *,
    config: ExperimentConfig,
    dataset_source: str,
    trainset: list[dict[str, Any]],
    valset: list[dict[str, Any]],
    testset: list[dict[str, Any]] | None,
    optimize_kwargs: dict[str, Any],
    execute: bool,
) -> dict[str, Any]:
    return {
        "experiment_name": config.experiment_name,
        "dataset_source": dataset_source,
        "task_model": config.task_model,
        "reflection_model": config.reflection_model,
        "task_lm": optimize_kwargs["task_lm"],
        "reflection_lm": optimize_kwargs["reflection_lm"],
        "max_metric_calls": optimize_kwargs["max_metric_calls"],
        "seed": optimize_kwargs["seed"],
        "trainset_size": len(trainset),
        "valset_size": len(valset),
        "testset_size": len(testset) if testset is not None else None,
        "seed_candidate": optimize_kwargs["seed_candidate"],
        "execute_optimize": execute,
        "temperature_task_recorded_only": config.temperature_task,
        "temperature_reflection_recorded_only": config.temperature_reflection,
    }


def run_minimal_official_path_sanity(
    config: ExperimentConfig,
    *,
    execute: bool,
    output_root: Path | None = None,
) -> Path:
    base_output_dir = output_root or (config.project_root / "outputs" / "official_path_sanity")
    base_output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = create_run_dir(base_output_dir)
    timestamp = create_timestamp()

    trainset, valset, testset, dataset_source = load_dataset_via_direct_official_path()
    optimize_kwargs = build_core_optimize_kwargs(
        config=config,
        trainset=trainset,
        valset=valset,
        run_dir=run_dir,
    )

    write_json(
        run_dir / "core_optimize_kwargs.json",
        _build_core_snapshot(
            config=config,
            dataset_source=dataset_source,
            trainset=trainset,
            valset=valset,
            testset=testset,
            optimize_kwargs=optimize_kwargs,
            execute=execute,
        ),
    )
    write_text(
        run_dir / "notes.md",
        "\n".join(
            [
                "# 最小官方路径校验",
                "",
                "- 目的：用最薄外壳证明 wrapper 没有改变 `gepa.optimize()` 的核心输入语义。",
                "- 该脚本直接依赖 `gepa.examples.aime.init_dataset()` 和 `gepa.optimize()`。",
                f"- 时间戳：{timestamp}",
                f"- execute_optimize：{execute}",
                f"- dataset_source：{dataset_source}",
                "- 注意：temperature_task / temperature_reflection 当前仅记录，不会自动接入官方批量调用路径。",
                "",
            ]
        ),
    )

    if not execute:
        return run_dir

    with temporary_openai_compatible_env(api_key=config.api_key, api_base=config.api_base):
        result = gepa.optimize(**optimize_kwargs)

    best_idx = result.best_idx
    best_score = result.val_aggregate_scores[best_idx]
    write_json(
        run_dir / "minimal_result_summary.json",
        {
            "best_idx": best_idx,
            "best_score": best_score,
            "total_metric_calls": result.total_metric_calls,
            "num_candidates": result.num_candidates,
            "num_val_instances": result.num_val_instances,
            "num_full_val_evals": result.num_full_val_evals,
        },
    )
    append_text(
        run_dir / "notes.md",
        "\n## 运行结果\n\n"
        f"- best_idx: {best_idx}\n"
        f"- best_score: {best_score}\n"
        f"- total_metric_calls: {result.total_metric_calls}\n",
    )
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="执行最小官方路径校验，默认只导出核心参数快照。")
    parser.add_argument("--config", required=True, help="配置文件路径，例如 configs/deepseek_pilot.yaml")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="显式调用 `gepa.optimize()`；默认只导出核心参数快照，不增加联网实验负担。",
    )
    args = parser.parse_args()

    config = load_experiment_config(
        PROJECT_ROOT / args.config,
        project_root=PROJECT_ROOT,
    )

    try:
        run_dir = run_minimal_official_path_sanity(config, execute=args.execute)
    except Exception as exc:
        print(redact_secret(str(exc), config.api_key), file=sys.stderr)
        raise

    print(json.dumps({"run_dir": str(run_dir), "execute_optimize": args.execute}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
