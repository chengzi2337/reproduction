from __future__ import annotations

import argparse
import json
import os
import random
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import gepa
import litellm
from datasets import Dataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.deepseek_utils import build_litellm_model_name, redact_secret
from src.gepa_official_runner import SEED_PROMPT, _locate_aime_init_dataset, load_official_aime_dataset
from src.logging_utils import create_run_dir, create_timestamp, write_json, write_text
from src.mimo_streaming_gepa_bridge import (
    MiMoStreamingBridgeConfig,
    patch_litellm_for_mimo_streaming,
    execute_health_check,
)


DEFAULT_OUTPUT_DIR = "outputs/stage4c_mimo_streaming_gepa_sanity"
DEFAULT_REPORT_PATH = "reports/stage4c_mimo_streaming_gepa_sanity_result.md"
DEFAULT_PROVIDER = "mimo"
DEFAULT_MODEL = "mimo-v2.5-pro"
DEFAULT_API_BASE = "https://token-plan-cn.xiaomimimo.com/v1"
DEFAULT_FIRST_TOKEN_TIMEOUT_SECONDS = 1800.0
DEFAULT_SDK_TIMEOUT_SECONDS = 1800.0
DEFAULT_DIAGNOSTIC_VAL_LIMIT = 1
ALLOWED_MAX_METRIC_CALLS = (1, 2)

DIAGNOSTIC_FLAGS: dict[str, bool] = {
    "diagnostic_only": True,
    "not_official_budget": True,
    "not_performance_claim": True,
    "not_model_ranking": True,
    "not_strict_default_path": True,
    "streaming_path_only": True,
    "thinking_enabled": True,
    "first_token_only_deadline": True,
    "gepa_optimize_called": False,
    "no_api_key_written": True,
    "stage4c_mimo_streaming_gepa_sanity": True,
}


@dataclass(slots=True)
class RuntimeConfig:
    provider: str
    model: str
    api_base: str
    api_key_env: str
    api_key: str
    output_dir: Path
    report_path: Path
    run_dir: Path | None
    first_token_timeout_seconds: float
    sdk_timeout_seconds: float
    emergency_after_first_token_seconds: float | None
    max_metric_calls: int
    diagnostic_val_limit: int

    @property
    def api_base_present(self) -> bool:
        return bool(self.api_base.strip())

    @property
    def model_present(self) -> bool:
        return bool(self.model.strip())

    def missing_config_reasons(self) -> list[str]:
        reasons: list[str] = []
        if not self.api_base_present:
            reasons.append("missing api_base")
        if not self.api_key.strip():
            reasons.append(f"missing credential env: {self.api_key_env}")
        if not self.model_present:
            reasons.append("missing model")
        return reasons


class Stage4CMiMoStreamingGEPASanityError(RuntimeError):
    """Stage 4C MiMo streaming GEPA sanity 失败。"""


def build_diagnostic_flags() -> dict[str, bool]:
    return dict(DIAGNOSTIC_FLAGS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage 4C MiMo streaming GEPA feasibility sanity。默认 dry-run，不自动调用 gepa.optimize。"
    )
    parser.add_argument("--provider", choices=(DEFAULT_PROVIDER,), default=DEFAULT_PROVIDER)
    parser.add_argument("--api-key-env", default="MIMO_API_KEY")
    parser.add_argument("--api-base-env", default="MIMO_API_BASE")
    parser.add_argument("--model-env", default="MIMO_MODEL")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-path", default=DEFAULT_REPORT_PATH)
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--first-token-timeout", type=float, default=DEFAULT_FIRST_TOKEN_TIMEOUT_SECONDS)
    parser.add_argument("--sdk-timeout", type=float, default=DEFAULT_SDK_TIMEOUT_SECONDS)
    parser.add_argument("--emergency-after-first-token", type=float, default=None)
    parser.add_argument("--max-metric-calls", type=int, default=1)
    parser.add_argument("--diagnostic-val-limit", type=int, default=DEFAULT_DIAGNOSTIC_VAL_LIMIT)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def project_relative(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def build_runtime_config(args: argparse.Namespace) -> RuntimeConfig:
    api_base = str(os.getenv(args.api_base_env) or DEFAULT_API_BASE).strip()
    model = str(os.getenv(args.model_env) or DEFAULT_MODEL).strip()
    api_key = str(os.getenv(args.api_key_env) or "").strip()
    return RuntimeConfig(
        provider=str(args.provider),
        model=model,
        api_base=api_base,
        api_key_env=str(args.api_key_env),
        api_key=api_key,
        output_dir=PROJECT_ROOT / args.output_dir,
        report_path=PROJECT_ROOT / args.report_path,
        run_dir=(PROJECT_ROOT / args.run_dir).resolve() if args.run_dir else None,
        first_token_timeout_seconds=float(args.first_token_timeout),
        sdk_timeout_seconds=float(args.sdk_timeout),
        emergency_after_first_token_seconds=args.emergency_after_first_token,
        max_metric_calls=int(args.max_metric_calls),
        diagnostic_val_limit=int(args.diagnostic_val_limit),
    )


def enforce_bounds(args: argparse.Namespace, runtime_config: RuntimeConfig) -> None:
    if args.provider != DEFAULT_PROVIDER:
        raise Stage4CMiMoStreamingGEPASanityError("当前仅允许 provider=mimo。")
    if runtime_config.max_metric_calls not in ALLOWED_MAX_METRIC_CALLS:
        raise Stage4CMiMoStreamingGEPASanityError("Stage 4C sanity 当前仅允许 max_metric_calls=1 或 2。")
    if runtime_config.diagnostic_val_limit <= 0:
        raise Stage4CMiMoStreamingGEPASanityError("--diagnostic-val-limit 必须大于 0。")
    if runtime_config.first_token_timeout_seconds <= 0:
        raise Stage4CMiMoStreamingGEPASanityError("--first-token-timeout 必须大于 0。")
    if runtime_config.sdk_timeout_seconds <= 0:
        raise Stage4CMiMoStreamingGEPASanityError("--sdk-timeout 必须大于 0。")
    if (
        runtime_config.emergency_after_first_token_seconds is not None
        and runtime_config.emergency_after_first_token_seconds <= 0
    ):
        raise Stage4CMiMoStreamingGEPASanityError("--emergency-after-first-token 必须大于 0。")


def load_dataset_metadata(
    diagnostic_val_limit: int,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]] | None,
    str,
    list[str],
    dict[str, Any],
]:
    return load_cached_official_aime_dataset(diagnostic_val_limit)


def _latest_matching_file(pattern: str) -> Path:
    candidates = sorted(Path.home().glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        raise Stage4CMiMoStreamingGEPASanityError(f"未找到匹配缓存文件：{pattern}")
    return candidates[0]


def _cache_display_path(path: Path) -> str:
    parts = path.parts
    if ".cache" in parts:
        start = parts.index(".cache")
        return "/".join(parts[start:])
    return path.name


def load_cached_official_aime_dataset(diagnostic_val_limit: int) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]] | None,
    str,
    list[str],
    dict[str, Any],
]:
    try:
        init_dataset, adaptation_notes = _locate_aime_init_dataset()
        official_source = f"{init_dataset.__module__}.init_dataset"
    except Exception:
        adaptation_notes = []
        official_source = "gepa.examples.aime.init_dataset (source unavailable)"

    aime_arrow = _latest_matching_file(
        ".cache/huggingface/datasets/AI-MO___aimo-validation-aime/default/0.0.0/*/aimo-validation-aime-train.arrow"
    )
    aime_2025_arrow = _latest_matching_file(
        ".cache/huggingface/datasets/MathArena___aime_2025/default/0.0.0/*/aime_2025-train.arrow"
    )

    train_split = [
        {
            "input": row["problem"],
            "additional_context": {"solution": row["solution"]},
            "answer": "### " + str(row["answer"]),
        }
        for row in Dataset.from_file(str(aime_arrow))
    ]
    random.Random(0).shuffle(train_split)
    test_split = [
        {
            "input": row["problem"],
            "answer": "### " + str(row["answer"]),
        }
        for row in Dataset.from_file(str(aime_2025_arrow))
    ]

    adaptation_notes.extend(
        [
            f"Stage 4C 直接复用官方 `init_dataset()` 的拆分语义，但为避免当前环境对 Hugging Face Hub 的探测重试，改为直接读取本地缓存 Arrow：`{_cache_display_path(aime_arrow)}` 与 `{_cache_display_path(aime_2025_arrow)}`。",
            f"官方语义来源：`{official_source}`。",
            "本地缓存路径只用于 Stage 4C GEPA sanity，未修改 GEPA optimizer、evaluator 或 AIME metric。",
        ]
    )
    dataset_source = (
        "local_hf_cache::"
        f"{_cache_display_path(aime_arrow)}|{_cache_display_path(aime_2025_arrow)}|semantic_source={official_source}"
    )
    trainset = train_split[: len(train_split) // 2]
    valset_full = train_split[len(train_split) // 2 :]
    valset = valset_full[:diagnostic_val_limit]
    testset = test_split * 5
    dataset_meta = {
        "trainset_size_full": len(trainset),
        "valset_size_full": len(valset_full),
        "valset_size_used": len(valset),
        "diagnostic_val_limit": diagnostic_val_limit,
        "testset_size": len(testset),
    }
    adaptation_notes.append(
        f"Stage 4C MiMo sanity 默认仅使用前 {len(valset)} 条 validation 样本，以避免 full validation 让 `max_metric_calls=1` 失去可解释性。"
    )
    return trainset, valset, testset, dataset_source, adaptation_notes, dataset_meta


def build_metric_call_semantics(*, valset_size_used: int, max_metric_calls: int) -> dict[str, Any]:
    seed_full_eval_metric_calls = int(valset_size_used)
    effective_min_metric_calls = int(valset_size_used) + 1
    return {
        "seed_full_eval_metric_calls": seed_full_eval_metric_calls,
        "effective_min_metric_calls": effective_min_metric_calls,
        "requested_max_metric_calls": int(max_metric_calls),
        "requested_budget_reaches_loop_entry": int(max_metric_calls) >= effective_min_metric_calls,
    }


def classify_stage4c_scope(metric_call_semantics: dict[str, Any]) -> str:
    if metric_call_semantics["requested_budget_reaches_loop_entry"]:
        return "optimization_loop_entry_followup"
    return "seed_evaluation_sanity"


def interpret_execute_result(
    *,
    run_summary: dict[str, Any],
    execution: dict[str, Any],
) -> tuple[str, list[str]]:
    if not run_summary["optimize_attempted"]:
        return "未进入 optimize", ["- 本次未进入 `gepa.optimize()`，因此没有 Stage 4C execute 结论。"]

    result_summary = run_summary.get("result_summary") or {}
    error_type = run_summary.get("error_type")
    total_metric_calls = result_summary.get("total_metric_calls")
    num_candidates = result_summary.get("num_candidates")
    effective_min_metric_calls = execution["effective_min_metric_calls"]

    if run_summary["optimize_succeeded"]:
        if (
            isinstance(total_metric_calls, int)
            and total_metric_calls >= effective_min_metric_calls
            and isinstance(num_candidates, int)
            and num_candidates > 1
        ):
            return (
                "optimization-loop entry passed",
                [
                    "- 该 run 已超过 seed-evaluation 所需的最小 metric call 门槛。",
                    f"- `total_metric_calls = {total_metric_calls}`，`num_candidates = {num_candidates}`，已出现非 seed candidate 证据。",
                    "- 当前可写成 `MiMo streaming GEPA optimization-loop entry passed`。",
                    "- 但这仍然不是 full-val、smoke 或 official_budget 结论。",
                ],
            )
        if (
            isinstance(total_metric_calls, int)
            and total_metric_calls >= effective_min_metric_calls
            and isinstance(num_candidates, int)
            and num_candidates <= 1
        ):
            return (
                "additional metric call passed, but candidate-generation evidence insufficient",
                [
                    "- 该 run 已完成超过 seed-evaluation 的额外 metric call。",
                    f"- `total_metric_calls = {total_metric_calls}`，但 `num_candidates = {num_candidates}`。",
                    "- 因此当前只能写成 `additional metric call passed, but candidate-generation evidence insufficient`。",
                ],
            )
        return (
            "seed-evaluation only",
            [
                "- optimize 虽返回成功，但当前 artifact 仍只支持 `seed-evaluation sanity` 口径。",
                f"- `total_metric_calls = {total_metric_calls}`，`effective_min_metric_calls = {effective_min_metric_calls}`。",
            ],
        )

    detail_lines = [
        "- optimize 未成功完成，当前不能写成 loop entry passed。",
        f"- `error_type = {error_type}`。",
    ]
    if isinstance(total_metric_calls, int):
        detail_lines.append(f"- 失败前已记录 `total_metric_calls = {total_metric_calls}`。")
    if isinstance(num_candidates, int):
        detail_lines.append(f"- 失败前已记录 `num_candidates = {num_candidates}`。")
    return ("optimization-loop entry blocked", detail_lines)


def build_optimize_kwargs(
    *,
    runtime_config: RuntimeConfig,
    run_dir: Path,
    trainset: list[dict[str, Any]],
    valset: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "seed_candidate": SEED_PROMPT,
        "trainset": trainset,
        "valset": valset,
        "task_lm": build_litellm_model_name(runtime_config.model),
        "reflection_lm": build_litellm_model_name(runtime_config.model),
        "max_metric_calls": runtime_config.max_metric_calls,
        "seed": 0,
        "run_dir": str(run_dir),
    }


def build_bridge_config(runtime_config: RuntimeConfig) -> MiMoStreamingBridgeConfig:
    return MiMoStreamingBridgeConfig(
        model=runtime_config.model,
        api_base=runtime_config.api_base,
        api_key=runtime_config.api_key,
        provider=runtime_config.provider,
        thinking_type="enabled",
        first_token_timeout_seconds=runtime_config.first_token_timeout_seconds,
        sdk_timeout_seconds=runtime_config.sdk_timeout_seconds,
        emergency_after_first_token_seconds=runtime_config.emergency_after_first_token_seconds,
    )


def build_input_snapshot(
    *,
    runtime_config: RuntimeConfig,
    optimize_kwargs: dict[str, Any],
    dataset_source: str,
    dataset_meta: dict[str, Any],
    metric_call_semantics: dict[str, Any],
    run_dir: Path,
    execute: bool,
    diagnostic_flags: dict[str, bool],
) -> dict[str, Any]:
    return {
        "metadata": {
            "generated_at": create_timestamp(),
            "mode": "execute" if execute else "dry_run",
            "run_dir": project_relative(run_dir),
            "model_called": bool(execute),
            "api_called": bool(execute),
            "new_experiment_executed": bool(execute),
            **diagnostic_flags,
        },
        "requested_execution": {
            "provider": runtime_config.provider,
            "model": runtime_config.model,
            "api_key_env": runtime_config.api_key_env,
            "api_base_present": runtime_config.api_base_present,
            "path_type": "stage4c_mimo_streaming_gepa_sanity",
            "streaming": True,
            "thinking": {"type": "enabled"},
            "first_token_timeout_seconds": runtime_config.first_token_timeout_seconds,
            "post_first_token_total_timeout_seconds": None,
            "no_application_total_wall_clock_timeout_after_first_token": True,
            "sdk_timeout_seconds": runtime_config.sdk_timeout_seconds,
            "emergency_after_first_token_seconds": runtime_config.emergency_after_first_token_seconds,
            "max_metric_calls": runtime_config.max_metric_calls,
            "diagnostic_val_limit": runtime_config.diagnostic_val_limit,
            "seed_full_eval_metric_calls": metric_call_semantics["seed_full_eval_metric_calls"],
            "effective_min_metric_calls": metric_call_semantics["effective_min_metric_calls"],
            "requested_budget_reaches_loop_entry": metric_call_semantics["requested_budget_reaches_loop_entry"],
            "stage4c_scope": classify_stage4c_scope(metric_call_semantics),
            "execute_optimize": bool(execute),
            "seed_prompt_source": "src.gepa_official_runner.SEED_PROMPT",
            "dataset_source": dataset_source,
            "task_lm": optimize_kwargs["task_lm"],
            "reflection_lm": optimize_kwargs["reflection_lm"],
            "gepa_optimize_called": False,
            "no_api_key_written": True,
        },
        "dataset_meta": {
            "dataset_source": dataset_source,
            "trainset_size": dataset_meta["trainset_size_full"],
            "valset_size_full": dataset_meta["valset_size_full"],
            "valset_size_used": dataset_meta["valset_size_used"],
            "diagnostic_val_limit": dataset_meta["diagnostic_val_limit"],
            "testset_size": dataset_meta["testset_size"],
        },
        "provider_config": {
            "provider": runtime_config.provider,
            "model": runtime_config.model,
            "api_base_present": runtime_config.api_base_present,
            "model_present": runtime_config.model_present,
            "missing_config_reasons": runtime_config.missing_config_reasons(),
        },
    }


def summarize_health_checks(records: list[dict[str, Any]], diagnostic_flags: dict[str, bool]) -> dict[str, Any]:
    latencies = [float(item["latency_seconds"]) for item in records if item.get("latency_seconds") is not None]
    return {
        "check_count": len(records),
        "ok_count": sum(1 for item in records if item.get("content_exact_ok")),
        "error_count": sum(1 for item in records if item.get("error_type")),
        "avg_latency_seconds": round(sum(latencies) / len(latencies), 6) if latencies else None,
        **diagnostic_flags,
    }


def build_run_summary(
    *,
    execute: bool,
    health_checks: list[dict[str, Any]],
    bridge_call_records: list[dict[str, Any]],
    optimize_attempted: bool,
    optimize_succeeded: bool,
    error_type: str | None,
    error_message: str | None,
    result_summary: dict[str, Any] | None,
    diagnostic_flags: dict[str, bool],
) -> dict[str, Any]:
    return {
        "generated_at": create_timestamp(),
        "mode": "execute" if execute else "dry_run",
        "optimize_attempted": optimize_attempted,
        "optimize_succeeded": optimize_succeeded,
        "health_check_summary": summarize_health_checks(health_checks, diagnostic_flags) if execute else {},
        "bridge_call_count": len(bridge_call_records),
        "bridge_calls": bridge_call_records if execute else [],
        "result_summary": result_summary or {},
        "error_type": error_type,
        "error_message_sanitized": error_message,
        **diagnostic_flags,
    }


def render_report(payload: dict[str, Any], run_summary: dict[str, Any]) -> str:
    metadata = payload["metadata"]
    execution = payload["requested_execution"]
    dataset_meta = payload["dataset_meta"]
    provider_config = payload["provider_config"]
    lines = [
        "# Stage 4C MiMo streaming GEPA sanity 结果",
        "",
        "## 定位",
        "",
        "- 本报告只记录 MiMo streaming GEPA feasibility sanity。",
        "- 本路径不是 strict default path。",
        "- 本路径不是 official_budget 结果。",
        "- 本路径不是模型排名，也不是性能结论。",
        "- 默认 dry-run；只有显式 `--execute` 才允许进入 `gepa.optimize()`。",
        "",
        "## 边界标记",
        "",
        f"- `model_called = {str(metadata['model_called']).lower()}`",
        f"- `api_called = {str(metadata['api_called']).lower()}`",
        f"- `new_experiment_executed = {str(metadata['new_experiment_executed']).lower()}`",
        "- `diagnostic_only = true`",
        "- `not_official_budget = true`",
        "- `not_performance_claim = true`",
        "- `not_model_ranking = true`",
        "- `not_strict_default_path = true`",
        "- `streaming_path_only = true`",
        "- `thinking_enabled = true`",
        "",
        "## 请求快照",
        "",
        f"- provider：`{execution['provider']}`",
        f"- model：`{execution['model']}`",
        "- path_type：`stage4c_mimo_streaming_gepa_sanity`",
        "- streaming：`true`",
        "- thinking：`{\"type\": \"enabled\"}`",
        f"- first_token_timeout_seconds：`{execution['first_token_timeout_seconds']}`",
        f"- sdk_timeout_seconds：`{execution['sdk_timeout_seconds']}`",
        f"- emergency_after_first_token_seconds：`{execution['emergency_after_first_token_seconds']}`",
        f"- max_metric_calls：`{execution['max_metric_calls']}`",
        f"- execute_optimize：`{str(execution['execute_optimize']).lower()}`",
        f"- stage4c_scope：`{execution['stage4c_scope']}`",
        f"- task_lm：`{execution['task_lm']}`",
        f"- reflection_lm：`{execution['reflection_lm']}`",
        f"- seed_prompt_source：`{execution['seed_prompt_source']}`",
        f"- dataset_source：`{execution['dataset_source']}`",
        f"- trainset_size：`{dataset_meta['trainset_size']}`",
        f"- valset_size_full：`{dataset_meta['valset_size_full']}`",
        f"- valset_size_used：`{dataset_meta['valset_size_used']}`",
        f"- diagnostic_val_limit：`{execution['diagnostic_val_limit']}`",
        f"- effective_min_metric_calls：`{execution['effective_min_metric_calls']}`",
        f"- requested_budget_reaches_loop_entry：`{str(execution['requested_budget_reaches_loop_entry']).lower()}`",
        f"- testset_size：`{dataset_meta['testset_size']}`",
        f"- gepa_optimize_called：`{str(run_summary['optimize_attempted']).lower()}`",
        "- no_api_key_written：`true`",
        "",
        "## 配置状态",
        "",
        f"- api_base_present：`{str(provider_config['api_base_present']).lower()}`",
        f"- model_present：`{str(provider_config['model_present']).lower()}`",
        f"- missing_config_reasons：`{', '.join(provider_config['missing_config_reasons']) if provider_config['missing_config_reasons'] else 'none'}`",
        "",
        "## 执行状态",
        "",
    ]

    if metadata["mode"] == "dry_run":
        lines.extend(
            [
                "- 当前状态：dry-run，未调用模型，未调用 API，未进入 `gepa.optimize()`。",
                "- 本次只验证 Stage 4C 脚手架、MiMo streaming bridge 契约、artifact schema 和报告骨架。",
                "- health check：未真实执行；真实 `--execute` 前后都必须执行 `Return exactly: OK`。",
                f"- 当前 budget 语义：seed full evaluation 会先消耗 `valset_size_used = {dataset_meta['valset_size_used']}` 个 metric calls；只有 `max_metric_calls >= {execution['effective_min_metric_calls']}` 才可能进入 optimization loop。",
                f"- 当前 scope：`{execution['stage4c_scope']}`。",
                "",
                "## 待执行判读框架",
                "",
                "1. 若 pre health check 失败，则直接判为 provider/key/endpoint/network blocker，不进入 GEPA。",
                "2. 若 task path 失败，必须区分失败发生在 health check、patch、GEPA optimize、response 组装还是 artifact parsing。",
                "3. 若首 token 前超时，必须标记 `FirstTokenTimeout`；首 token 后的紧急保护只能标为 emergency。",
                "4. 即使未来 execute 成功，也不能写成 strict path 成功或 official_budget 结论。",
            ]
        )
        return "\n".join(lines) + "\n"

    health_summary = run_summary["health_check_summary"]
    lines.extend(
        [
            f"- optimize_attempted：`{str(run_summary['optimize_attempted']).lower()}`",
            f"- optimize_succeeded：`{str(run_summary['optimize_succeeded']).lower()}`",
            f"- error_type：`{run_summary['error_type']}`",
            "",
            "## health check 汇总",
            "",
            f"- check_count：`{health_summary['check_count']}`",
            f"- ok_count：`{health_summary['ok_count']}`",
            f"- error_count：`{health_summary['error_count']}`",
            f"- avg_latency_seconds：`{health_summary['avg_latency_seconds']}`",
            "",
            "## bridge 调用摘要",
            "",
            f"- bridge_call_count：`{run_summary['bridge_call_count']}`",
        ]
    )
    result_summary = run_summary.get("result_summary") or {}
    loop_entry_label, loop_entry_lines = interpret_execute_result(run_summary=run_summary, execution=execution)
    lines.extend(
        [
            "",
            "## optimize 结果摘要",
            "",
            f"- best_idx：`{result_summary.get('best_idx')}`",
            f"- best_score：`{result_summary.get('best_score')}`",
            f"- total_metric_calls：`{result_summary.get('total_metric_calls')}`",
            f"- num_candidates：`{result_summary.get('num_candidates')}`",
            f"- num_val_instances：`{result_summary.get('num_val_instances')}`",
            f"- num_full_val_evals：`{result_summary.get('num_full_val_evals')}`",
            "",
            "## 判读",
            "",
            f"- 当前判读标签：`{loop_entry_label}`",
            *loop_entry_lines,
        ]
    )
    if run_summary["bridge_calls"]:
        lines.extend(
            [
                "",
                "## 首条 bridge 调用快照",
                "",
                f"- first_token_observed：`{run_summary['bridge_calls'][0].get('first_token_observed')}`",
                f"- time_to_first_token_seconds：`{run_summary['bridge_calls'][0].get('time_to_first_token_seconds')}`",
                f"- time_after_first_token_seconds：`{run_summary['bridge_calls'][0].get('time_after_first_token_seconds')}`",
                f"- time_to_complete_seconds：`{run_summary['bridge_calls'][0].get('time_to_complete_seconds')}`",
                f"- finish_reason：`{run_summary['bridge_calls'][0].get('finish_reason')}`",
                f"- content_nonempty：`{run_summary['bridge_calls'][0].get('content_nonempty')}`",
                f"- error_type：`{run_summary['bridge_calls'][0].get('error_type')}`",
            ]
        )
    return "\n".join(lines) + "\n"


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def execute_plan(
    *,
    runtime_config: RuntimeConfig,
    bridge_config: MiMoStreamingBridgeConfig,
    optimize_kwargs: dict[str, Any],
    run_dir: Path,
    diagnostic_flags: dict[str, bool],
) -> dict[str, Any]:
    health_checks: list[dict[str, Any]] = []
    bridge_call_records: list[dict[str, Any]] = []
    raw_payloads: list[dict[str, Any]] = []
    error_type: str | None = None
    error_message: str | None = None
    result_summary: dict[str, Any] | None = None
    optimize_attempted = False
    optimize_succeeded = False

    missing_config_reasons = runtime_config.missing_config_reasons()
    if missing_config_reasons:
        return {
            "health_checks": health_checks,
            "bridge_call_records": bridge_call_records,
            "raw_payloads": raw_payloads,
            "optimize_attempted": optimize_attempted,
            "optimize_succeeded": optimize_succeeded,
            "error_type": "ConfigMissing",
            "error_message": "; ".join(missing_config_reasons),
            "result_summary": {
                "failure_mode": "config_missing_before_health_check",
                "missing_config_reasons": missing_config_reasons,
                **diagnostic_flags,
            },
        }

    pre_health, _ = execute_health_check(bridge_config=bridge_config, original_completion=litellm.completion)
    health_checks.append({"phase": "pre", **pre_health})
    if not pre_health["content_exact_ok"]:
        error_type = pre_health.get("error_type") or "HealthCheckFailed"
        error_message = pre_health.get("error_message_sanitized") or "health check failed before optimize"
        return {
            "health_checks": health_checks,
            "bridge_call_records": bridge_call_records,
            "raw_payloads": raw_payloads,
            "optimize_attempted": optimize_attempted,
            "optimize_succeeded": optimize_succeeded,
            "error_type": error_type,
            "error_message": error_message,
            "result_summary": result_summary,
        }

    try:
        with patch_litellm_for_mimo_streaming(
            bridge_config=bridge_config,
            call_records=bridge_call_records,
            raw_payloads=raw_payloads,
        ):
            optimize_attempted = True
            result = gepa.optimize(**optimize_kwargs)
            optimize_succeeded = True
            best_idx = result.best_idx
            best_score = result.val_aggregate_scores[best_idx]
            result_summary = {
                "best_idx": best_idx,
                "best_score": best_score,
                "total_metric_calls": result.total_metric_calls,
                "num_candidates": result.num_candidates,
                "num_val_instances": result.num_val_instances,
                "num_full_val_evals": result.num_full_val_evals,
            }
    except Exception as exc:  # pragma: no cover - 真实 execute 路径
        error_type = type(exc).__name__
        error_message = redact_secret(str(exc), runtime_config.api_key)
        bridge_record = getattr(exc, "bridge_record", None)
        bridge_raw_payload = getattr(exc, "bridge_raw_payload", None)
        if isinstance(bridge_record, dict):
            bridge_call_records.append(bridge_record)
        if isinstance(bridge_raw_payload, dict):
            raw_payloads.append(bridge_raw_payload)
        result_summary = {
            "stack_trace_summary": redact_secret(traceback.format_exc(limit=8), runtime_config.api_key)[:1200],
            "failure_mode": "patch_or_gepa_optimize_or_response_assembly",
            "raw_preview": bridge_record.get("raw_preview") if isinstance(bridge_record, dict) else None,
            **diagnostic_flags,
        }

    post_health, _ = execute_health_check(bridge_config=bridge_config, original_completion=litellm.completion)
    health_checks.append({"phase": "post", **post_health})
    if not post_health["content_exact_ok"] and error_type is None:
        error_type = post_health.get("error_type") or "PostHealthCheckFailed"
        error_message = post_health.get("error_message_sanitized") or "health check failed after optimize"

    return {
        "health_checks": health_checks,
        "bridge_call_records": bridge_call_records,
        "raw_payloads": raw_payloads,
        "optimize_attempted": optimize_attempted,
        "optimize_succeeded": optimize_succeeded,
        "error_type": error_type,
        "error_message": error_message,
        "result_summary": result_summary,
    }


def main() -> None:
    args = parse_args()
    runtime_config = build_runtime_config(args)
    enforce_bounds(args, runtime_config)
    runtime_config.output_dir.mkdir(parents=True, exist_ok=True)
    runtime_config.report_path.parent.mkdir(parents=True, exist_ok=True)
    run_dir = runtime_config.run_dir or create_run_dir(runtime_config.output_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    diagnostic_flags = build_diagnostic_flags()
    trainset, valset, testset, dataset_source, adaptation_notes, dataset_meta = load_dataset_metadata(
        runtime_config.diagnostic_val_limit
    )
    metric_call_semantics = build_metric_call_semantics(
        valset_size_used=dataset_meta["valset_size_used"],
        max_metric_calls=runtime_config.max_metric_calls,
    )
    optimize_kwargs = build_optimize_kwargs(
        runtime_config=runtime_config,
        run_dir=run_dir,
        trainset=trainset,
        valset=valset,
    )
    bridge_config = build_bridge_config(runtime_config)

    input_snapshot = build_input_snapshot(
        runtime_config=runtime_config,
        optimize_kwargs=optimize_kwargs,
        dataset_source=dataset_source,
        dataset_meta=dataset_meta,
        metric_call_semantics=metric_call_semantics,
        run_dir=run_dir,
        execute=args.execute,
        diagnostic_flags=diagnostic_flags,
    )

    if args.execute:
        execution_result = execute_plan(
            runtime_config=runtime_config,
            bridge_config=bridge_config,
            optimize_kwargs=optimize_kwargs,
            run_dir=run_dir,
            diagnostic_flags=diagnostic_flags,
        )
        run_summary = build_run_summary(
            execute=True,
            health_checks=execution_result["health_checks"],
            bridge_call_records=execution_result["bridge_call_records"],
            optimize_attempted=execution_result["optimize_attempted"],
            optimize_succeeded=execution_result["optimize_succeeded"],
            error_type=execution_result["error_type"],
            error_message=execution_result["error_message"],
            result_summary=execution_result["result_summary"],
            diagnostic_flags={**diagnostic_flags, "gepa_optimize_called": execution_result["optimize_attempted"]},
        )
        bridge_paths = []
        if execution_result["raw_payloads"]:
            raw_dir = run_dir / "raw_responses"
            raw_dir.mkdir(parents=True, exist_ok=True)
            for index, payload in enumerate(execution_result["raw_payloads"], start=1):
                path = raw_dir / f"bridge_call_{index:03d}.json"
                write_json(path, payload)
                bridge_paths.append(project_relative(path))
        write_jsonl(run_dir / "health_checks.jsonl", execution_result["health_checks"])
        write_jsonl(run_dir / "bridge_call_records.jsonl", execution_result["bridge_call_records"])
        write_json(
            run_dir / "execute_artifacts.json",
            {
                "adaptation_notes": adaptation_notes,
                "bridge_raw_paths": bridge_paths,
                **diagnostic_flags,
            },
        )
    else:
        run_summary = build_run_summary(
            execute=False,
            health_checks=[],
            bridge_call_records=[],
            optimize_attempted=False,
            optimize_succeeded=False,
            error_type=None,
            error_message=None,
            result_summary=None,
            diagnostic_flags=diagnostic_flags,
        )
        write_json(run_dir / "dry_run_stub.json", {"adaptation_notes": adaptation_notes, **diagnostic_flags})

    write_json(run_dir / "input_snapshot.json", input_snapshot)
    write_json(run_dir / "run_summary.json", run_summary)
    write_text(runtime_config.report_path, render_report(input_snapshot, run_summary))


if __name__ == "__main__":
    main()
