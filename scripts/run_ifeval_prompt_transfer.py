from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ifeval_prompt_transfer_preflight import DEFAULT_VARIANT_CONFIG_PATH, build_preflight_result
from src.ifeval_official_adapter import official_import_path
from src.logging_utils import create_timestamp, get_git_commit, write_json, write_text


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports" / "ifeval_qwen3_smoke_limit20"
DEFAULT_PROVIDER_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3-8b"
REQUIRED_LIMIT = 20
PRIMARY_CREDENTIAL_ENV = "DASHSCOPE" + "_API" + "_KEY"
FALLBACK_CREDENTIAL_ENVS = ("QWEN" + "_API" + "_KEY", "OPENAI" + "_API" + "_KEY")


class IFEvalRunnerError(RuntimeError):
    """IFEval prompt-transfer runner 门禁或执行失败。"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IFEval prompt-transfer limit=20 smoke runner。")
    parser.add_argument("--variant-config", default=str(DEFAULT_VARIANT_CONFIG_PATH))
    parser.add_argument("--ifeval-root", default=None)
    parser.add_argument("--dataset-path", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--model", default=os.getenv("QWEN_MODEL", DEFAULT_MODEL))
    parser.add_argument("--provider-base", default=os.getenv("QWEN_API_BASE", DEFAULT_PROVIDER_BASE))
    parser.add_argument("--credential-env", default=PRIMARY_CREDENTIAL_ENV)
    parser.add_argument("--limit", type=int, default=None)
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
    return parser.parse_args(argv)


def load_variants(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    variants = payload["variants"]
    if not isinstance(variants, list) or not variants:
        raise IFEvalRunnerError("variant 配置为空。")
    return variants


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
    first = choices[0]
    message = getattr(first, "message", None)
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


def build_run_config(args: argparse.Namespace, preflight: dict[str, Any], variants: list[dict[str, Any]]) -> dict[str, Any]:
    now = create_timestamp()
    return {
        "commit_sha": get_git_commit(PROJECT_ROOT),
        "dataset_path": preflight["dataset"].get("dataset_path"),
        "ifeval_root": preflight["ifeval_root"].get("ifeval_root"),
        "model_name": args.model,
        "provider_type": "dashscope_openai_compatible",
        "provider_base": args.provider_base,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
        "limit": args.limit,
        "num_threads": args.num_threads,
        "disable_dspy_cache": bool(args.disable_dspy_cache),
        "variants": [variant["variant_id"] for variant in variants],
        "start_time": now,
        "end_time": None,
        "api_run_enabled": bool(args.enable_api_run),
        "gepa_optimization_enabled": False,
        "mock_provider": bool(args.mock_provider),
    }


def enforce_api_gate(args: argparse.Namespace, preflight: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not args.enable_api_run:
        reasons.append("missing_enable_api_run")
    if not args.ifeval_root:
        reasons.append("missing_ifeval_root")
    if args.limit is None:
        reasons.append("missing_explicit_limit")
    elif args.limit != REQUIRED_LIMIT:
        reasons.append("limit_must_be_20")
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


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def evaluate_outputs(
    *,
    ifeval_root: Path,
    dataset_path: Path,
    raw_rows: list[dict[str, Any]],
    variants: list[dict[str, Any]],
    limit: int,
) -> dict[str, Any]:
    with official_import_path(ifeval_root):
        evaluation_lib = importlib.import_module("instruction_following_eval.evaluation_lib")
        inputs = evaluation_lib.read_prompt_list(str(dataset_path))[:limit]
        input_by_prompt = {item.prompt: item for item in inputs}
        result_by_variant: dict[str, Any] = {}
        for variant in variants:
            variant_id = str(variant["variant_id"])
            rows = [row for row in raw_rows if row["variant"] == variant_id]
            prompt_to_response = {row["prompt"]: row["response"] for row in rows}
            outputs = [
                evaluation_lib.test_instruction_following_strict(input_by_prompt[row["prompt"]], prompt_to_response)
                for row in rows
            ]
            result_by_variant[variant_id] = outputs
    return summarize_eval_outputs(result_by_variant)


def summarize_eval_outputs(result_by_variant: dict[str, list[Any]]) -> dict[str, Any]:
    per_variant: dict[str, Any] = {}
    total_prompt = 0
    total_prompt_correct = 0
    total_instruction = 0
    total_instruction_correct = 0
    per_instruction: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    for variant_id, outputs in result_by_variant.items():
        prompt_total = len(outputs)
        prompt_correct = sum(1 for item in outputs if bool(item.follow_all_instructions))
        instruction_total = sum(len(list(item.follow_instruction_list)) for item in outputs)
        instruction_correct = sum(sum(1 for value in item.follow_instruction_list if value) for item in outputs)
        per_variant[variant_id] = {
            "prompt_level_accuracy": prompt_correct / prompt_total if prompt_total else None,
            "instruction_level_accuracy": instruction_correct / instruction_total if instruction_total else None,
            "prompt_correct": prompt_correct,
            "prompt_total": prompt_total,
            "instruction_correct": instruction_correct,
            "instruction_total": instruction_total,
        }
        total_prompt += prompt_total
        total_prompt_correct += prompt_correct
        total_instruction += instruction_total
        total_instruction_correct += instruction_correct
        for item in outputs:
            for instruction_id, followed in zip(item.instruction_id_list, item.follow_instruction_list):
                family = str(instruction_id).split(":")[0]
                per_instruction[family]["total"] += 1
                if followed:
                    per_instruction[family]["correct"] += 1
    return {
        "prompt_level_accuracy": total_prompt_correct / total_prompt if total_prompt else None,
        "instruction_level_accuracy": total_instruction_correct / total_instruction if total_instruction else None,
        "per_variant": per_variant,
        "per_instruction_type_accuracy": {
            key: {
                "accuracy": value["correct"] / value["total"] if value["total"] else None,
                **value,
            }
            for key, value in sorted(per_instruction.items())
        },
        "pairwise_delta": build_pairwise_delta(per_variant),
    }


def build_pairwise_delta(per_variant: dict[str, Any]) -> dict[str, Any]:
    pairs = [
        ("baseline_mhc", "baseline"),
        ("verbose_helpfulness", "baseline"),
        ("mhc_concise", "baseline_mhc"),
        ("gepa_p2_transfer", "ifbench_gepa_prompt_transfer"),
    ]
    deltas: dict[str, Any] = {}
    for left, right in pairs:
        left_payload = per_variant.get(left) or {}
        right_payload = per_variant.get(right) or {}
        key = f"{left} - {right}"
        deltas[key] = {
            "prompt_level_accuracy_delta": none_safe_delta(
                left_payload.get("prompt_level_accuracy"), right_payload.get("prompt_level_accuracy")
            ),
            "instruction_level_accuracy_delta": none_safe_delta(
                left_payload.get("instruction_level_accuracy"), right_payload.get("instruction_level_accuracy")
            ),
        }
    return deltas


def none_safe_delta(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def summarize_provider_events(raw_rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in raw_rows:
        status = str(row["provider_status"])
        counts[status] = counts.get(status, 0) + 1
    return {
        "provider_error_count": sum(count for status, count in counts.items() if status not in {"ok"}),
        "provider_rejection_count": counts.get("provider_rejection", 0),
        "timeout_count": counts.get("timeout", 0),
        "provider_status_counts": counts,
        "events": [
            {
                "sample_index": row["sample_index"],
                "variant": row["variant"],
                "provider_status": row["provider_status"],
                "provider_error": row["provider_error"],
            }
            for row in raw_rows
            if row["provider_status"] != "ok"
        ],
    }


def render_summary_md(summary: dict[str, Any]) -> str:
    lines = [
        "# IFEval prompt-transfer limit=20 smoke test",
        "",
        "## 边界",
        "",
        "- 这是 `limit=20 smoke test`，不是全量 IFEval 实验。",
        "- 这是 prompt-transfer，不是 GEPA optimization。",
        "- 结果只能作为链路验证和初步信号，不能作为论文主结论。",
        "- 使用 official IFEval rule checker，不使用 LLM judge。",
        "- 如果 MHC/P2 有提升，只能写 preliminary signal，不能写 proved。",
        "- 如果结果不稳定或不提升，不改 prompt、不删样本，原样报告。",
        "",
        "## 总览",
        "",
        f"- status：`{summary['status']}`",
        f"- limit：`{summary['limit']}`",
        f"- variant_count：`{summary['variant_count']}`",
        f"- model_calls_planned：`{summary['model_calls_planned']}`",
        f"- model_calls_completed：`{summary['model_calls_completed']}`",
        f"- prompt_level_accuracy：`{summary['evaluation']['prompt_level_accuracy']}`",
        f"- instruction_level_accuracy：`{summary['evaluation']['instruction_level_accuracy']}`",
        f"- provider_error_count：`{summary['provider_events']['provider_error_count']}`",
        f"- provider_rejection_count：`{summary['provider_events']['provider_rejection_count']}`",
        f"- timeout_count：`{summary['provider_events']['timeout_count']}`",
        "",
        "## Per-variant",
        "",
        "| variant | prompt_level_accuracy | instruction_level_accuracy |",
        "|---|---:|---:|",
    ]
    for variant, payload in summary["evaluation"]["per_variant"].items():
        lines.append(
            f"| `{variant}` | `{payload['prompt_level_accuracy']}` | `{payload['instruction_level_accuracy']}` |"
        )
    lines.extend(["", "## Pairwise delta", "", "| pair | prompt delta | instruction delta |", "|---|---:|---:|"])
    for pair, payload in summary["evaluation"]["pairwise_delta"].items():
        lines.append(
            f"| `{pair}` | `{payload['prompt_level_accuracy_delta']}` | `{payload['instruction_level_accuracy_delta']}` |"
        )
    return "\n".join(lines) + "\n"


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    variants = load_variants(Path(args.variant_config))
    preflight = build_preflight_result(
        variant_config_path=Path(args.variant_config),
        dataset_path=Path(args.dataset_path) if args.dataset_path else None,
        ifeval_root=Path(args.ifeval_root) if args.ifeval_root else None,
    )
    config = build_run_config(args, preflight, variants)
    write_json(output_dir / "run_config.json", config)
    gate_reasons = enforce_api_gate(args, preflight)
    if args.dry_run or not args.enable_api_run:
        status = {
            "status": "dry_run" if not gate_reasons or not args.enable_api_run else "blocked",
            "api_call_enabled": False,
            "preflight_status": preflight["status"],
            "blocked_reasons": gate_reasons,
            "model_calls_planned": (args.limit or 0) * len(variants),
        }
        write_json(output_dir / "summary.json", status)
        write_text(output_dir / "summary.md", render_dry_run_md(status))
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return status
    if gate_reasons:
        status = {
            "status": "blocked",
            "api_call_enabled": False,
            "preflight_status": preflight["status"],
            "blocked_reasons": gate_reasons,
        }
        write_json(output_dir / "summary.json", status)
        write_text(output_dir / "summary.md", render_dry_run_md(status))
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return status

    credential_env, credential = resolve_credential(str(args.credential_env))
    if credential is None:
        raise IFEvalRunnerError("门禁已检查凭据，但执行阶段未读取到凭据。")
    dataset_path = Path(preflight["dataset"]["dataset_path"])
    ifeval_root = Path(preflight["ifeval_root"]["ifeval_root"])
    from src.ifeval_official_adapter import read_ifeval_samples

    samples = read_ifeval_samples(dataset_path, limit=int(args.limit))
    raw_rows: list[dict[str, Any]] = []
    for sample_index, sample in enumerate(samples):
        prompt = str(sample["prompt"])
        for variant in variants:
            variant_id = str(variant["variant_id"])
            row = run_one_call(
                prompt=prompt,
                sample_index=sample_index,
                variant_id=variant_id,
                variant=variant,
                args=args,
                credential=credential,
            )
            raw_rows.append(row)
            write_jsonl(output_dir / "raw_outputs.jsonl", raw_rows)

    provider_events = summarize_provider_events(raw_rows)
    evaluation = evaluate_outputs(
        ifeval_root=ifeval_root,
        dataset_path=dataset_path,
        raw_rows=raw_rows,
        variants=variants,
        limit=int(args.limit),
    )
    summary = {
        "status": "completed",
        "api_call_enabled": True,
        "credential_env_present": bool(credential_env),
        "limit": args.limit,
        "variant_count": len(variants),
        "model_calls_planned": int(args.limit) * len(variants),
        "model_calls_completed": len(raw_rows),
        "evaluation": evaluation,
        "provider_events": provider_events,
        "parse_checker_error_count": 0,
    }
    config["end_time"] = create_timestamp()
    write_json(output_dir / "run_config.json", config)
    write_json(output_dir / "provider_events.json", provider_events)
    write_json(output_dir / "eval_results.json", evaluation)
    write_json(output_dir / "summary.json", summary)
    write_text(output_dir / "summary.md", render_summary_md(summary))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


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


def render_dry_run_md(status: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# IFEval prompt-transfer runner dry-run",
            "",
            "- 当前没有调用真实 API。",
            "- 当前没有运行 GEPA optimization。",
            f"- status：`{status['status']}`",
            f"- preflight_status：`{status.get('preflight_status')}`",
            f"- blocked_reasons：`{status.get('blocked_reasons')}`",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run_smoke(args)
    return 0 if summary["status"] in {"dry_run", "completed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
