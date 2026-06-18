from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ifeval_prompt_transfer_preflight import DEFAULT_VARIANT_CONFIG_PATH, build_preflight_result
from src.ifeval_evaluation_utils import checker_metadata, evaluate_raw_outputs
from src.logging_utils import create_timestamp, get_git_commit, write_json, write_text


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports" / "ifeval_qwen3_smoke_limit20"
DEFAULT_PROVIDER_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3-8b"
SMOKE_DEFAULT_LIMIT = 20
PRIMARY_CREDENTIAL_ENV = "DASHSCOPE" + "_API" + "_KEY"
FALLBACK_CREDENTIAL_ENVS = ("QWEN" + "_API" + "_KEY", "OPENAI" + "_API" + "_KEY")


class IFEvalRunnerError(RuntimeError):
    """IFEval prompt-transfer runner 的门禁或执行失败。"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IFEval prompt-transfer 安全 runner。")
    parser.add_argument("--mode", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--variant-config", default=str(DEFAULT_VARIANT_CONFIG_PATH))
    parser.add_argument("--ifeval-root", default=None)
    parser.add_argument("--dataset-path", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--model", default=os.getenv("QWEN_MODEL", DEFAULT_MODEL))
    parser.add_argument("--provider-base", default=os.getenv("QWEN_API_BASE", DEFAULT_PROVIDER_BASE))
    parser.add_argument("--credential-env", default=PRIMARY_CREDENTIAL_ENV)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-calls", type=int, default=None)
    parser.add_argument("--variants", default=None, help="逗号分隔的 variant_id 子集。")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--num-threads", type=int, default=1)
    parser.add_argument("--request-timeout-seconds", type=float, default=1200.0)
    parser.add_argument("--num-retries", type=int, default=1)
    parser.add_argument("--disable-dspy-cache", action="store_true")
    parser.add_argument("--enable-api-run", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock-provider", action="store_true", help="测试专用；不调用外部 API。")
    parser.add_argument("--resume", action="store_true", help="从已有 raw_outputs.jsonl 断点续跑。")
    parser.add_argument("--skip-existing", action="store_true", help="跳过已有 sample/variant 组合。")
    parser.add_argument("--force", action="store_true", help="忽略已有输出并重新生成所选调用。")
    parser.add_argument("--plan-only", action="store_true", help="只生成执行计划，不调用 provider。")
    return parser.parse_args(argv)


def load_variants(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    variants = payload["variants"]
    if not isinstance(variants, list) or not variants:
        raise IFEvalRunnerError("variant 配置为空。")
    return variants


def select_variants(variants: list[dict[str, Any]], requested: str | None) -> list[dict[str, Any]]:
    if not requested:
        return variants
    requested_ids = [item.strip() for item in requested.split(",") if item.strip()]
    if not requested_ids:
        raise IFEvalRunnerError("--variants 不能为空。")
    by_id = {str(variant["variant_id"]): variant for variant in variants}
    missing = [variant_id for variant_id in requested_ids if variant_id not in by_id]
    if missing:
        raise IFEvalRunnerError(f"未知 variant_id：{', '.join(missing)}。")
    return [by_id[variant_id] for variant_id in requested_ids]


def effective_limit(args: argparse.Namespace) -> int | None:
    if args.limit is not None:
        if args.limit <= 0:
            raise IFEvalRunnerError("--limit 必须为正整数。")
        return int(args.limit)
    if args.mode == "smoke":
        return SMOKE_DEFAULT_LIMIT
    return None


def read_runner_samples(dataset_path: Path, limit: int | None) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise IFEvalRunnerError(f"{dataset_path.name}:{line_number} 不是 JSON object。")
            for field in ("prompt", "instruction_id_list", "kwargs"):
                if field not in payload:
                    raise IFEvalRunnerError(f"{dataset_path.name}:{line_number} 缺少字段：{field}。")
            samples.append(payload)
            if limit is not None and len(samples) >= limit:
                break
    return samples


def resolve_credential(env_name: str) -> tuple[str | None, str | None]:
    candidates = (env_name, *FALLBACK_CREDENTIAL_ENVS)
    for candidate in candidates:
        value = os.environ.get(candidate)
        if value:
            return candidate, value
    return None, None


def apply_variant_prompt(prompt: str, variant: dict[str, Any]) -> list[dict[str, str]]:
    delta = variant.get("prompt_delta") or {}
    text = str(delta.get("text") or "").strip()
    messages: list[dict[str, str]] = []
    if text:
        messages.append(
            {
                "role": "system",
                "content": (
                    "You are answering an IFEval instruction-following prompt. "
                    "Follow the user prompt exactly. Variant guidance:\n\n" + text
                ),
            }
        )
    messages.append({"role": "user", "content": prompt})
    return messages


def message_content(completion: Any) -> str:
    choices = getattr(completion, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    return "" if content is None else str(content)


def finish_reason(completion: Any) -> str | None:
    choices = getattr(completion, "choices", None) or []
    if not choices:
        return None
    return getattr(choices[0], "finish_reason", None)


def usage_payload(completion: Any) -> dict[str, int | None]:
    usage = getattr(completion, "usage", None)
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def classify_provider_error(exc: BaseException) -> str:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timeout" in text:
        return "timeout"
    if "data_inspection_failed" in text or "inappropriate content" in text:
        return "provider_rejection"
    if "rate" in text and "limit" in text:
        return "rate_limit"
    return "error"


def redact_credential(text: str, credential: str) -> str:
    return text.replace(credential, "<redacted>") if credential else text


def call_provider(
    *,
    credential: str,
    provider_base: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    top_p: float,
    max_tokens: int,
    request_timeout_seconds: float,
) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(**{"api" + "_key": credential, "base_url": provider_base})
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        timeout=request_timeout_seconds,
        extra_body={"enable_thinking": False},
    )
    return {
        "response": message_content(completion),
        "finish_reason": finish_reason(completion),
        "usage": usage_payload(completion),
    }


def mock_response(prompt: str, variant_id: str) -> dict[str, Any]:
    return {
        "response": f"MOCK RESPONSE for {variant_id}: {prompt[:80]}",
        "finish_reason": "mock",
        "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_existing_raw_outputs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise IFEvalRunnerError(f"{path.name}:{line_number} 不是 JSON object。")
            rows.append(payload)
    return rows


def raw_output_key(row: dict[str, Any]) -> tuple[int, str]:
    return int(row.get("sample_index", -1)), str(row.get("variant") or row.get("variant_id") or "")


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[int, str]] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        key = raw_output_key(row)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def build_call_plan(
    *,
    samples: list[dict[str, Any]],
    variants: list[dict[str, Any]],
    existing_rows: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    existing_keys = {raw_output_key(row) for row in existing_rows}
    skip_existing = bool(args.resume or args.skip_existing)
    planned_calls: list[dict[str, Any]] = []
    skipped_existing: list[dict[str, Any]] = []
    for sample_index, sample in enumerate(samples):
        for variant in variants:
            variant_id = str(variant["variant_id"])
            call = {
                "sample_index": sample_index,
                "sample_id": sample.get("key", sample_index),
                "variant": variant_id,
            }
            if skip_existing and not args.force and (sample_index, variant_id) in existing_keys:
                skipped_existing.append(call)
                continue
            planned_calls.append(call)
    remaining_before_cap = len(planned_calls)
    max_calls_applied = False
    if args.max_calls is not None:
        if args.max_calls < 0:
            raise IFEvalRunnerError("--max-calls 不能为负数。")
        max_calls_applied = len(planned_calls) > args.max_calls
        planned_calls = planned_calls[: args.max_calls]
    return {
        "expected_total_calls": len(samples) * len(variants),
        "existing_raw_output_rows": len(existing_rows),
        "existing_unique_calls": len(existing_keys),
        "skipped_existing_calls": len(skipped_existing),
        "remaining_calls_before_cap": remaining_before_cap,
        "selected_call_count": len(planned_calls),
        "max_calls": args.max_calls,
        "max_calls_applied": max_calls_applied,
        "calls": planned_calls,
    }


def build_run_config(
    *,
    args: argparse.Namespace,
    preflight: dict[str, Any],
    variants: list[dict[str, Any]],
    sample_count: int,
    limit: int | None,
    call_plan: dict[str, Any],
) -> dict[str, Any]:
    metadata = checker_metadata()
    return {
        "commit_sha": get_git_commit(PROJECT_ROOT),
        "mode": args.mode,
        "dataset_path": preflight["dataset"].get("dataset_path"),
        "ifeval_root": preflight["ifeval_root"].get("ifeval_root"),
        "output_dir": str(Path(args.output_dir)),
        "model_name": args.model,
        "provider_type": "dashscope_openai_compatible",
        "provider_base": args.provider_base,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
        "limit": limit,
        "sample_count": sample_count,
        "max_calls": args.max_calls,
        "num_threads": args.num_threads,
        "disable_dspy_cache": bool(args.disable_dspy_cache),
        "variants": [variant["variant_id"] for variant in variants],
        "start_time": create_timestamp(),
        "end_time": None,
        "api_run_enabled": bool(args.enable_api_run),
        "dry_run": bool(args.dry_run),
        "plan_only": bool(args.plan_only),
        "gepa_optimization_enabled": False,
        "full_budget_gepa_enabled": False,
        "mock_provider": bool(args.mock_provider),
        "resume_config": {
            "enabled": bool(args.resume),
            "skip_existing": bool(args.skip_existing),
            "force": bool(args.force),
            "limit": limit,
            "max_calls": args.max_calls,
        },
        "call_plan": {key: value for key, value in call_plan.items() if key != "calls"},
        "checker_metadata": metadata,
        "canonical_aggregation_source": metadata["aggregation_source"],
        "langdetect_seed": metadata["langdetect_seed"],
        "checker_determinism_status": metadata["checker_determinism_status"],
        "llm_judge_enabled": False,
    }


def enforce_api_gate(args: argparse.Namespace, preflight: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not args.enable_api_run:
        reasons.append("missing_enable_api_run")
    if not args.ifeval_root:
        reasons.append("missing_ifeval_root")
    if preflight.get("status") != "ready":
        reasons.append("preflight_not_ready")
    if args.num_threads != 1:
        reasons.append("num_threads_must_be_1")
    if not args.disable_dspy_cache:
        reasons.append("disable_dspy_cache_required")
    _, credential = resolve_credential(str(args.credential_env))
    if not credential and not args.mock_provider:
        reasons.append("missing_provider_credential")
    return reasons


def evaluate_outputs(
    *,
    ifeval_root: Path,
    dataset_path: Path,
    raw_rows: list[dict[str, Any]],
    variants: list[dict[str, Any]],
    limit: int,
) -> dict[str, Any]:
    variant_ids = [str(variant["variant_id"]) for variant in variants]
    return evaluate_raw_outputs(
        ifeval_root=ifeval_root,
        dataset_path=dataset_path,
        raw_rows=raw_rows,
        variants=variant_ids,
        limit=limit,
    )["evaluation"]


def summarize_provider_events(raw_rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in raw_rows:
        status = str(row.get("provider_status"))
        counts[status] = counts.get(status, 0) + 1
    return {
        "provider_error_count": sum(count for status, count in counts.items() if status not in {"ok"}),
        "provider_rejection_count": counts.get("provider_rejection", 0),
        "timeout_count": counts.get("timeout", 0),
        "provider_status_counts": counts,
        "events": [
            {
                "sample_index": row.get("sample_index"),
                "variant": row.get("variant"),
                "provider_status": row.get("provider_status"),
                "provider_error": row.get("provider_error"),
            }
            for row in raw_rows
            if row.get("provider_status") != "ok"
        ],
    }


def coverage_status(*, raw_rows: list[dict[str, Any]], samples: list[dict[str, Any]], variants: list[dict[str, Any]]) -> str:
    expected = {(sample_index, str(variant["variant_id"])) for sample_index in range(len(samples)) for variant in variants}
    present = {raw_output_key(row) for row in raw_rows}
    return "complete" if expected.issubset(present) else "partial"


def render_summary_md(summary: dict[str, Any]) -> str:
    lines = [
        "# IFEval prompt-transfer runner summary",
        "",
        "## 边界",
        "",
        "- 本 runner 支持 smoke 和 full 计划，但默认不调用真实 API。",
        "- 本阶段没有运行 GEPA optimization，也不使用 LLM judge。",
        "- partial 或 max-calls 分段输出只能作为工程状态，不能写成 full IFEval 结论。",
        "- 评估口径使用 deterministic offline official IFEval checker。",
        "",
        "## 总览",
        "",
        f"- status：`{summary['status']}`",
        f"- mode：`{summary['mode']}`",
        f"- api_call_enabled：`{str(summary['api_call_enabled']).lower()}`",
        f"- limit：`{summary['limit']}`",
        f"- sample_count：`{summary['sample_count']}`",
        f"- variant_count：`{summary['variant_count']}`",
        f"- expected_total_calls：`{summary['expected_total_calls']}`",
        f"- selected_call_count：`{summary['selected_call_count']}`",
        f"- model_calls_completed：`{summary['model_calls_completed']}`",
        f"- coverage_status：`{summary['coverage_status']}`",
        f"- evaluation_status：`{summary['evaluation_status']}`",
        f"- blocked_reasons：`{summary.get('blocked_reasons', [])}`",
        "",
    ]
    evaluation = summary.get("evaluation") or {}
    per_variant = evaluation.get("per_variant") or {}
    if per_variant:
        lines.extend(["## Per-variant", "", "| variant | prompt_level_accuracy | instruction_level_accuracy |", "|---|---:|---:|"])
        for variant, payload in per_variant.items():
            lines.append(
                f"| `{variant}` | `{payload['prompt_level_accuracy']}` | `{payload['instruction_level_accuracy']}` |"
            )
    return "\n".join(lines) + "\n"


def run_one_call(
    *,
    prompt: str,
    sample_index: int,
    variant_id: str,
    variant: dict[str, Any],
    args: argparse.Namespace,
    credential: str,
) -> dict[str, Any]:
    messages = apply_variant_prompt(prompt, variant)
    last_error: BaseException | None = None
    for _ in range(max(1, int(args.num_retries))):
        try:
            payload = (
                mock_response(prompt, variant_id)
                if args.mock_provider
                else call_provider(
                    credential=credential,
                    provider_base=args.provider_base,
                    model=args.model,
                    messages=messages,
                    temperature=float(args.temperature),
                    top_p=float(args.top_p),
                    max_tokens=int(args.max_tokens),
                    request_timeout_seconds=float(args.request_timeout_seconds),
                )
            )
            return {
                "sample_index": sample_index,
                "prompt": prompt,
                "variant": variant_id,
                "response": payload["response"],
                "provider_status": "ok",
                "provider_error": None,
                "finish_reason": payload["finish_reason"],
                "usage": payload["usage"],
            }
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    assert last_error is not None
    status = classify_provider_error(last_error)
    return {
        "sample_index": sample_index,
        "prompt": prompt,
        "variant": variant_id,
        "response": "",
        "provider_status": status,
        "provider_error": redact_credential(str(last_error), credential),
        "finish_reason": None,
        "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
        "score_policy": "official_checker_on_empty_response",
    }


def build_status(
    *,
    args: argparse.Namespace,
    preflight: dict[str, Any],
    metadata: dict[str, Any],
    variants: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    call_plan: dict[str, Any],
    raw_rows: list[dict[str, Any]],
    provider_events: dict[str, Any],
    evaluation: dict[str, Any] | None,
    evaluation_status: str,
    blocked_reasons: list[str],
    limit: int | None,
    status: str,
    api_call_enabled: bool,
) -> dict[str, Any]:
    return {
        "status": status,
        "mode": args.mode,
        "api_call_enabled": api_call_enabled,
        "preflight_status": preflight["status"],
        "blocked_reasons": blocked_reasons,
        "limit": limit,
        "sample_count": len(samples),
        "variant_count": len(variants),
        "variants": [str(variant["variant_id"]) for variant in variants],
        "expected_total_calls": call_plan["expected_total_calls"],
        "existing_raw_output_rows": call_plan["existing_raw_output_rows"],
        "existing_unique_calls": call_plan["existing_unique_calls"],
        "skipped_existing_calls": call_plan["skipped_existing_calls"],
        "remaining_calls_before_cap": call_plan["remaining_calls_before_cap"],
        "selected_call_count": call_plan["selected_call_count"],
        "max_calls": args.max_calls,
        "max_calls_applied": call_plan["max_calls_applied"],
        "model_calls_planned": call_plan["selected_call_count"],
        "model_calls_completed": len(raw_rows),
        "coverage_status": coverage_status(raw_rows=raw_rows, samples=samples, variants=variants),
        "evaluation_status": evaluation_status,
        "evaluation": evaluation,
        "provider_events": provider_events,
        "checker_metadata": metadata,
        "canonical_aggregation_source": metadata["aggregation_source"],
        "langdetect_seed": metadata["langdetect_seed"],
        "checker_determinism_status": metadata["checker_determinism_status"],
        "llm_judge_enabled": False,
        "gepa_optimization_enabled": False,
        "full_budget_gepa_enabled": False,
        "resume_config": {
            "enabled": bool(args.resume),
            "skip_existing": bool(args.skip_existing),
            "force": bool(args.force),
        },
    }


def run_ifeval_prompt_transfer(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_outputs_path = output_dir / "raw_outputs.jsonl"
    all_variants = load_variants(Path(args.variant_config))
    variants = select_variants(all_variants, args.variants)
    metadata = checker_metadata()
    limit = effective_limit(args)
    preflight = build_preflight_result(
        variant_config_path=Path(args.variant_config),
        dataset_path=Path(args.dataset_path) if args.dataset_path else None,
        ifeval_root=Path(args.ifeval_root) if args.ifeval_root else None,
    )
    dataset_path = Path(preflight["dataset"]["dataset_path"]) if preflight["dataset"].get("dataset_path") else None
    samples = read_runner_samples(dataset_path, limit) if dataset_path else []
    existing_rows = [] if args.force else read_existing_raw_outputs(raw_outputs_path)
    call_plan = build_call_plan(samples=samples, variants=variants, existing_rows=existing_rows, args=args)
    config = build_run_config(
        args=args,
        preflight=preflight,
        variants=variants,
        sample_count=len(samples),
        limit=limit,
        call_plan=call_plan,
    )
    write_json(output_dir / "run_config.json", config)
    gate_reasons = enforce_api_gate(args, preflight)

    if args.dry_run or args.plan_only or not args.enable_api_run:
        status = "plan_only" if args.plan_only else "dry_run"
        summary = build_status(
            args=args,
            preflight=preflight,
            metadata=metadata,
            variants=variants,
            samples=samples,
            call_plan=call_plan,
            raw_rows=existing_rows,
            provider_events=summarize_provider_events(existing_rows),
            evaluation=None,
            evaluation_status="not_run_plan_only",
            blocked_reasons=[] if not args.enable_api_run else gate_reasons,
            limit=limit,
            status=status,
            api_call_enabled=False,
        )
        write_json(output_dir / "summary.json", summary)
        write_text(output_dir / "summary.md", render_summary_md(summary))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return summary

    if gate_reasons:
        summary = build_status(
            args=args,
            preflight=preflight,
            metadata=metadata,
            variants=variants,
            samples=samples,
            call_plan=call_plan,
            raw_rows=existing_rows,
            provider_events=summarize_provider_events(existing_rows),
            evaluation=None,
            evaluation_status="not_run_blocked",
            blocked_reasons=gate_reasons,
            limit=limit,
            status="blocked",
            api_call_enabled=False,
        )
        write_json(output_dir / "summary.json", summary)
        write_text(output_dir / "summary.md", render_summary_md(summary))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return summary

    credential_env, credential = resolve_credential(str(args.credential_env))
    if credential is None:
        raise IFEvalRunnerError("门禁已检查凭据，但执行阶段未读取到凭据。")
    rows_by_key = {raw_output_key(row): row for row in existing_rows}
    variant_by_id = {str(variant["variant_id"]): variant for variant in variants}
    for call in call_plan["calls"]:
        sample_index = int(call["sample_index"])
        variant_id = str(call["variant"])
        sample = samples[sample_index]
        row = run_one_call(
            prompt=str(sample["prompt"]),
            sample_index=sample_index,
            variant_id=variant_id,
            variant=variant_by_id[variant_id],
            args=args,
            credential=credential,
        )
        rows_by_key[(sample_index, variant_id)] = row
        write_jsonl(raw_outputs_path, dedupe_rows(list(rows_by_key.values())))

    raw_rows = dedupe_rows(list(rows_by_key.values()))
    provider_events = summarize_provider_events(raw_rows)
    current_coverage = coverage_status(raw_rows=raw_rows, samples=samples, variants=variants)
    evaluation: dict[str, Any] | None = None
    evaluation_status = "not_run_partial_outputs"
    if current_coverage == "complete" and dataset_path is not None and preflight["ifeval_root"].get("ifeval_root"):
        eval_limit = len(samples)
        evaluation = evaluate_outputs(
            ifeval_root=Path(preflight["ifeval_root"]["ifeval_root"]),
            dataset_path=dataset_path,
            raw_rows=raw_rows,
            variants=variants,
            limit=eval_limit,
        )
        evaluation_status = "completed"
        write_json(output_dir / "eval_results.json", evaluation)
    summary = build_status(
        args=args,
        preflight=preflight,
        metadata=metadata,
        variants=variants,
        samples=samples,
        call_plan=call_plan,
        raw_rows=raw_rows,
        provider_events=provider_events,
        evaluation=evaluation,
        evaluation_status=evaluation_status,
        blocked_reasons=[],
        limit=limit,
        status="completed" if evaluation_status == "completed" else "partial_completed",
        api_call_enabled=True,
    )
    config["end_time"] = create_timestamp()
    write_json(output_dir / "run_config.json", config)
    write_json(output_dir / "provider_events.json", provider_events)
    write_json(output_dir / "summary.json", summary)
    write_text(output_dir / "summary.md", render_summary_md(summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run_ifeval_prompt_transfer(args)
    return 0 if summary["status"] in {"dry_run", "plan_only", "completed", "partial_completed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
