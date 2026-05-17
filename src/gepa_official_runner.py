from __future__ import annotations

import importlib
import inspect
import pickle
import pkgutil
import traceback
from pathlib import Path
from typing import Any, Callable

import gepa

from src.config import ExperimentConfig
from src.deepseek_utils import (
    ProbeResult,
    build_litellm_model_name,
    probe_model_with_openai_client,
    redact_secret,
    temporary_openai_compatible_env,
)
from src.logging_utils import (
    append_text,
    build_manifest,
    capture_stdout_stderr,
    create_run_dir,
    create_timestamp,
    write_json,
    write_package_versions,
    write_text,
    write_yaml,
)


SEED_PROMPT = {
    "system_prompt": "You are a helpful assistant. Answer the question. Put your final answer in the format '### <answer>'"
}


def _locate_aime_init_dataset() -> tuple[Callable[[], Any], list[str]]:
    adaptation_notes: list[str] = []
    examples = getattr(gepa, "examples", None)
    aime_module = getattr(examples, "aime", None) if examples is not None else None
    init_dataset = getattr(aime_module, "init_dataset", None) if aime_module is not None else None
    if callable(init_dataset):
        source_file = inspect.getsourcefile(init_dataset) or "unknown"
        source_line = inspect.getsourcelines(init_dataset)[1]
        adaptation_notes.append(
            f"当前安装版本直接提供 `gepa.examples.aime.init_dataset()`，入口位于 `{source_file}:{source_line}`。"
        )
        return init_dataset, adaptation_notes

    if examples is None or not hasattr(examples, "__path__"):
        raise RuntimeError("当前 GEPA 安装不包含可扫描的 examples 包，无法定位官方 AIME 入口。")

    for module_info in pkgutil.iter_modules(examples.__path__, prefix=f"{examples.__name__}."):
        if "aime" not in module_info.name.lower():
            continue
        module = importlib.import_module(module_info.name)
        init_dataset = getattr(module, "init_dataset", None)
        if callable(init_dataset):
            source_file = inspect.getsourcefile(init_dataset) or "unknown"
            source_line = inspect.getsourcelines(init_dataset)[1]
            adaptation_notes.append(
                "当前安装版本未直接暴露 `gepa.examples.aime.init_dataset()`，"
                f"已通过 introspection 回退定位到 `{module_info.name}.init_dataset`（`{source_file}:{source_line}`）。"
            )
            return init_dataset, adaptation_notes

    raise RuntimeError("未能在当前 GEPA 安装中定位官方 AIME `init_dataset()`。")


def _locate_optimize() -> tuple[Callable[..., Any], list[str]]:
    optimize = getattr(gepa, "optimize", None)
    if callable(optimize):
        source_file = inspect.getsourcefile(optimize) or "unknown"
        source_line = inspect.getsourcelines(optimize)[1]
        return optimize, [f"当前安装版本直接暴露 `gepa.optimize()`，入口位于 `{source_file}:{source_line}`。"]
    raise RuntimeError("当前 GEPA 安装未暴露可调用的 `gepa.optimize()`。")


def load_official_aime_dataset() -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]] | None,
    str,
    list[str],
]:
    init_dataset, adaptation_notes = _locate_aime_init_dataset()
    dataset_source = f"{inspect.getsourcefile(init_dataset)}:{inspect.getsourcelines(init_dataset)[1]}"
    dataset_result = init_dataset()
    if not isinstance(dataset_result, tuple):
        raise RuntimeError("官方 AIME `init_dataset()` 返回结果不是 tuple，无法继续。")
    if len(dataset_result) == 3:
        trainset, valset, testset = dataset_result
    elif len(dataset_result) == 2:
        trainset, valset = dataset_result
        testset = None
    else:
        raise RuntimeError(f"无法识别的 AIME 数据返回长度：{len(dataset_result)}。")
    return list(trainset), list(valset), list(testset) if testset is not None else None, dataset_source, adaptation_notes


def _sanitize_value(value: Any, secret: str) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_value(inner, secret) for key, inner in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(inner, secret) for inner in value]
    if isinstance(value, str):
        return redact_secret(value, secret)
    return value


def _save_raw_result(run_dir: Path, result: Any, api_key: str) -> Path:
    try:
        raw_payload = _sanitize_value(result.to_dict(), api_key)
        raw_result_path = run_dir / "raw_result.json"
        write_json(raw_result_path, raw_payload)
        return raw_result_path
    except Exception:
        raw_result_path = run_dir / "raw_result.pkl"
        with raw_result_path.open("wb") as handle:
            pickle.dump(result, handle)
        return raw_result_path


def _collect_probe_results(config: ExperimentConfig) -> list[tuple[str, ProbeResult]]:
    return [
        (
            "task_model",
            probe_model_with_openai_client(
                api_key=config.api_key,
                api_base=config.api_base,
                model_name=config.task_model,
            ),
        ),
        (
            "reflection_model",
            probe_model_with_openai_client(
                api_key=config.api_key,
                api_base=config.api_base,
                model_name=config.reflection_model,
            ),
        ),
    ]


def _build_notes(
    *,
    config: ExperimentConfig,
    dataset_source: str,
    train_size: int,
    val_size: int,
    test_size: int | None,
    adaptation_notes: list[str],
) -> str:
    lines = [
        "# 运行备注",
        "",
        "- 实验性质：GEPA method-level reproduction with DeepSeek backend。",
        "- 复用策略：尽量沿用 GEPA 官方 AIME 数据入口、官方 optimize API 和官方默认适配器语义，只替换模型后端。",
        f"- 官方 AIME 入口：`{dataset_source}`",
        f"- trainset 大小：{train_size}",
        f"- valset 大小：{val_size}",
        f"- testset 大小：{test_size if test_size is not None else '未暴露'}",
        f"- task_model：`{config.task_model}`",
        f"- reflection_model：`{config.reflection_model}`",
        f"- max_metric_calls：`{config.max_metric_calls}`",
        "- 未修改 GEPA 源码。",
        "",
        "## 适配记录",
        "",
    ]
    lines.extend(f"- {note}" for note in adaptation_notes)
    lines.append("- `task_lm` 采用官方 `gepa.optimize()` 的字符串模型路径，不再使用自写 callable。")
    lines.append("- DeepSeek 只通过 OpenAI-compatible 环境变量桥接到 LiteLLM。")
    lines.append("")
    if test_size is None:
        lines.extend(
            [
                "## 评估限制",
                "",
                "- current GEPA official example did not expose a test split in this package version; using validation sanity check only.",
                "",
            ]
        )
    return "\n".join(lines)


def run_gepa_aime_experiment(config: ExperimentConfig) -> Path:
    config.ensure_output_dir()
    run_dir = create_run_dir(config.output_dir)
    run_id = run_dir.name
    timestamp = create_timestamp()

    trainset, valset, testset, dataset_source, adaptation_notes = load_official_aime_dataset()
    optimize, optimize_notes = _locate_optimize()
    adaptation_notes.extend(optimize_notes)

    probe_results = _collect_probe_results(config)
    model_check_passed = all(result.ok for _, result in probe_results)
    manifest = build_manifest(
        run_id=run_id,
        timestamp=timestamp,
        project_root=config.project_root,
        provider=config.provider,
        api_base=config.api_base,
        task_model=config.task_model,
        reflection_model=config.reflection_model,
        max_metric_calls=config.max_metric_calls,
        seed=config.seed,
        benchmark=config.benchmark,
        reproduction_type=config.reproduction_type,
        allow_model_substitution=config.allow_model_substitution,
        model_check_passed=model_check_passed,
        output_dir=run_dir,
        code_modified_from_gepa_official=False,
        notes=adaptation_notes,
    )
    write_json(run_dir / "manifest.json", manifest)
    write_yaml(run_dir / "config_resolved.yaml", config.to_public_dict())
    write_package_versions(run_dir / "package_versions.txt")
    write_json(
        run_dir / "seed_prompt.json",
        {
            "candidate": SEED_PROMPT,
            "source": "GEPA official quick start semantic equivalent",
        },
    )
    write_text(
        run_dir / "notes.md",
        _build_notes(
            config=config,
            dataset_source=dataset_source,
            train_size=len(trainset),
            val_size=len(valset),
            test_size=(len(testset) if testset is not None else None),
            adaptation_notes=adaptation_notes,
        ),
    )

    for label, result in probe_results:
        if result.ok:
            continue
        append_text(
            run_dir / "notes.md",
            "\n## 启动前阻塞\n\n"
            f"- 失败模型：`{label}` / `{result.model}`\n"
            f"- 状态码：`{result.status_code}`\n"
            f"- 失败原因：`{result.error_type}: {result.error_message}`\n"
            f"- 错误体：`{result.error_body or ''}`\n"
            "- 当前阶段禁止模型替换。\n"
            "- 请检查 key、base_url、model id、余额、权限或限流状态。\n",
        )
        raise RuntimeError(f"{label} 启动前检查失败：{result.error_type}: {result.error_message}")

    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    task_model_name = build_litellm_model_name(config.task_model)
    reflection_model_name = build_litellm_model_name(config.reflection_model)

    with capture_stdout_stderr(stdout_path=stdout_path, stderr_path=stderr_path):
        print(f"[INFO] 运行目录: {run_dir}")
        print(f"[INFO] experiment_name={config.experiment_name}")
        print(f"[INFO] benchmark={config.benchmark}")
        print(f"[INFO] task_model={config.task_model}")
        print(f"[INFO] reflection_model={config.reflection_model}")
        print(f"[INFO] max_metric_calls={config.max_metric_calls}")
        print(f"[INFO] seed={config.seed}")
        print(f"[INFO] AIME 数据来源: {dataset_source}")
        print(f"[INFO] train={len(trainset)} val={len(valset)} test={len(testset) if testset is not None else 'N/A'}")
        print(f"[INFO] LiteLLM task model={task_model_name}")
        print(f"[INFO] LiteLLM reflection model={reflection_model_name}")
        print("[INFO] 开始调用官方 gepa.optimize()")

        try:
            with temporary_openai_compatible_env(api_key=config.api_key, api_base=config.api_base):
                result = optimize(
                    seed_candidate=SEED_PROMPT,
                    trainset=trainset,
                    valset=valset,
                    task_lm=task_model_name,
                    reflection_lm=reflection_model_name,
                    max_metric_calls=config.max_metric_calls,
                    seed=config.seed,
                    run_dir=str(run_dir),
                )
        except Exception as exc:
            append_text(
                run_dir / "notes.md",
                "\n## 运行失败\n\n"
                f"- 异常类型：`{type(exc).__name__}`\n"
                f"- 异常信息：`{redact_secret(str(exc), config.api_key)}`\n"
                "- 已保留 stdout/stderr 供排查。\n",
            )
            print("[ERROR] GEPA 运行失败")
            print(redact_secret(traceback.format_exc(), config.api_key))
            raise

        best_idx = result.best_idx
        best_score = result.val_aggregate_scores[best_idx]
        optimized_prompt = result.best_candidate
        print(f"[INFO] GEPA 完成，best_idx={best_idx}, best_score={best_score}")

        write_json(
            run_dir / "optimized_prompt.json",
            {
                "candidate": optimized_prompt,
                "best_idx": best_idx,
                "best_score": best_score,
                "total_metric_calls": result.total_metric_calls,
            },
        )

        raw_result_path = _save_raw_result(run_dir, result, config.api_key)
        write_json(
            run_dir / "gepa_result_summary.json",
            {
                "best_idx": best_idx,
                "best_score": best_score,
                "num_candidates": result.num_candidates,
                "num_val_instances": result.num_val_instances,
                "total_metric_calls": result.total_metric_calls,
                "num_full_val_evals": result.num_full_val_evals,
                "raw_result_path": raw_result_path.name,
                "seed_prompt": SEED_PROMPT,
                "optimized_prompt": optimized_prompt,
            },
        )

        append_text(
            run_dir / "notes.md",
            "\n## 运行结果\n\n"
            f"- best_idx：`{best_idx}`\n"
            f"- best_score：`{best_score}`\n"
            f"- total_metric_calls：`{result.total_metric_calls}`\n"
            f"- num_candidates：`{result.num_candidates}`\n",
        )

    return run_dir
