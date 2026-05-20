from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import APIStatusError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DEFAULT_BACKEND_FAMILY
from src.logging_utils import create_run_dir, write_json, write_text
from src.openai_compatible_utils import (
    build_litellm_model_name,
    build_openai_client,
    redact_secret,
    temporary_openai_compatible_env,
)
from scripts.stage2c_run_mimo_controlled_generation_gepa_sanity import load_dataset_via_stage2c_path


DEFAULT_MODEL = "mimo-v2.5-pro"
DEFAULT_THINKING_TYPE = "disabled"
DEFAULT_MAX_COMPLETION_TOKENS = 2048
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_SAMPLE_COUNT = 3
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "stage2c_mimo_prompt_first_format_enforcement_diagnostic"
PATH_TYPE = "stage2c_mimo_prompt_first_format_enforcement_diagnostic"

PROMPT_VARIANTS: list[dict[str, str]] = [
    {
        "variant_id": "A",
        "variant_name": "answer_only",
        "prompt_type": "stage2c_prompt_first_answer_only",
        "system_prompt": (
            "You are solving an AIME-style math problem. Solve internally. Output only the final answer "
            "in exactly this format:\n### <answer>\nDo not include steps, headings, explanations, or Markdown sections."
        ),
    },
    {
        "variant_id": "B",
        "variant_name": "first_line_final_answer",
        "prompt_type": "stage2c_prompt_first_line_final_answer",
        "system_prompt": (
            "You are solving an AIME-style math problem. The first line of your response must be exactly:\n"
            "### <answer>\nAfter that, you may provide a brief explanation."
        ),
    },
    {
        "variant_id": "C",
        "variant_name": "readme_quickstart_control",
        "prompt_type": "readme_quickstart_seed_prompt",
        "system_prompt": "You are a helpful assistant. Answer the question. Put your final answer in the format '### <answer>'",
    },
]


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _proxy_env_detected() -> dict[str, bool]:
    return {
        "http_proxy_set": bool(_env("HTTP_PROXY") or _env("http_proxy")),
        "https_proxy_set": bool(_env("HTTPS_PROXY") or _env("https_proxy")),
    }


def _get_attr_or_key(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _stringify_optional(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, list):
        parts = [_stringify_optional(item) for item in value]
        filtered = [item for item in parts if item]
        return "\n".join(filtered) if filtered else None
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    normalized = str(value).strip()
    return normalized or None


def _extract_message_fields(message: Any) -> tuple[str | None, str | None]:
    return (
        _stringify_optional(_get_attr_or_key(message, "content")),
        _stringify_optional(_get_attr_or_key(message, "reasoning_content")),
    )


def _preview(text: str | None, limit: int = 240) -> str | None:
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _usage_payload(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "completion_tokens_details": {"reasoning_tokens": None},
        }
    details = _get_attr_or_key(usage, "completion_tokens_details")
    return {
        "prompt_tokens": _get_attr_or_key(usage, "prompt_tokens"),
        "completion_tokens": _get_attr_or_key(usage, "completion_tokens"),
        "total_tokens": _get_attr_or_key(usage, "total_tokens"),
        "completion_tokens_details": {
            "reasoning_tokens": _get_attr_or_key(details, "reasoning_tokens") if details is not None else None,
        },
    }


def _extract_status_code(exc: Exception) -> int | None:
    if isinstance(exc, APIStatusError):
        return getattr(exc, "status_code", None)
    return getattr(exc, "status_code", None)


def _first_nonempty_line(text: str | None) -> str | None:
    if not text:
        return None
    for line in text.splitlines():
        normalized = line.strip()
        if normalized:
            return normalized
    return None


def _exact_final_answer_match(text: str | None) -> re.Match[str] | None:
    if not text:
        return None
    return re.search(r"(?m)^###\s*(\d+)\s*$", text)


def exact_final_answer_format_present(text: str | None) -> bool:
    return _exact_final_answer_match(text) is not None


def first_line_matches_final_answer(text: str | None) -> bool:
    first_line = _first_nonempty_line(text)
    return bool(first_line and re.fullmatch(r"###\s*\d+", first_line))


def contains_markdown_step_heading(text: str | None) -> bool:
    if not text:
        return False
    return re.search(r"(?mi)^###\s*(step|part|solution|analysis)\b", text) is not None


def looks_truncated(text: str | None, finish_reason: str | None = None) -> bool:
    if finish_reason == "length":
        return True
    if not text:
        return False
    stripped = text.strip()
    if not stripped or exact_final_answer_format_present(stripped):
        return False
    return stripped[-1] not in set(".!?0123456789}])\"'")


def build_messages(*, system_prompt: str, question: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]


def _success_result(*, response: Any, elapsed_seconds: float) -> dict[str, Any]:
    choice = _get_attr_or_key(response, "choices")[0]
    message = _get_attr_or_key(choice, "message")
    content, reasoning_content = _extract_message_fields(message)
    finish_reason = _get_attr_or_key(choice, "finish_reason")
    content_nonempty = bool(content)
    return {
        "ok": content_nonempty,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "status_code": _get_attr_or_key(response, "status_code"),
        "content_nonempty": content_nonempty,
        "content_preview": _preview(content),
        "reasoning_content_nonempty": bool(reasoning_content),
        "finish_reason": finish_reason,
        "usage": _usage_payload(_get_attr_or_key(response, "usage")),
        "exact_final_answer_format_present": exact_final_answer_format_present(content),
        "first_line_matches_###_integer": first_line_matches_final_answer(content),
        "contains_markdown_step_heading": contains_markdown_step_heading(content),
        "truncated_before_final": looks_truncated(content, finish_reason),
        "error_type": None if content_nonempty else "EmptyContent",
        "error_message": None if content_nonempty else "模型调用成功，但 content 为空。",
    }


def _error_result(*, exc: Exception, api_key: str, elapsed_seconds: float) -> dict[str, Any]:
    return {
        "ok": False,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "status_code": _extract_status_code(exc),
        "content_nonempty": False,
        "content_preview": None,
        "reasoning_content_nonempty": False,
        "finish_reason": None,
        "usage": _usage_payload(None),
        "exact_final_answer_format_present": False,
        "first_line_matches_###_integer": False,
        "contains_markdown_step_heading": False,
        "truncated_before_final": False,
        "error_type": type(exc).__name__,
        "error_message": redact_secret(str(exc), api_key),
    }


def run_direct_sdk_format_check(
    *,
    api_key: str,
    api_base: str,
    model: str,
    messages: list[dict[str, str]],
    thinking_type: str,
    max_completion_tokens: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    client = build_openai_client(api_key=api_key, api_base=api_base)
    started_at = time.perf_counter()
    try:
        response = client.with_options(timeout=timeout_seconds).chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            extra_body={"thinking": {"type": thinking_type}},
        )
    except Exception as exc:
        return _error_result(
            exc=exc,
            api_key=api_key,
            elapsed_seconds=time.perf_counter() - started_at,
        )
    return _success_result(response=response, elapsed_seconds=time.perf_counter() - started_at)


def run_litellm_format_check(
    *,
    api_key: str,
    api_base: str,
    model: str,
    messages: list[dict[str, str]],
    thinking_type: str,
    max_completion_tokens: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    from litellm import completion

    started_at = time.perf_counter()
    try:
        with temporary_openai_compatible_env(api_key=api_key, api_base=api_base):
            response = completion(
                model=build_litellm_model_name(model),
                messages=messages,
                max_completion_tokens=max_completion_tokens,
                timeout=timeout_seconds,
                extra_body={"thinking": {"type": thinking_type}},
            )
    except Exception as exc:
        return _error_result(
            exc=exc,
            api_key=api_key,
            elapsed_seconds=time.perf_counter() - started_at,
        )
    return _success_result(response=response, elapsed_seconds=time.perf_counter() - started_at)


def load_val_samples(sample_count: int) -> tuple[list[dict[str, Any]], str]:
    _, valset, _, dataset_source = load_dataset_via_stage2c_path()
    if sample_count <= 0:
        raise ValueError("sample_count 必须大于 0。")
    if len(valset) < sample_count:
        raise ValueError(f"valset 样本数不足，无法读取前 {sample_count} 个样本。")
    samples = [dict(valset[idx]) for idx in range(sample_count)]
    return samples, dataset_source


def run_single_case(
    *,
    api_key: str,
    api_base: str,
    model: str,
    sample_index: int,
    sample_input: str,
    prompt_variant: dict[str, str],
    thinking_type: str,
    max_completion_tokens: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    messages = build_messages(system_prompt=prompt_variant["system_prompt"], question=sample_input)
    return {
        "sample_index": sample_index,
        "prompt_variant": {
            "variant_id": prompt_variant["variant_id"],
            "variant_name": prompt_variant["variant_name"],
            "prompt_type": prompt_variant["prompt_type"],
            "system_prompt": prompt_variant["system_prompt"],
        },
        "direct_sdk_result": run_direct_sdk_format_check(
            api_key=api_key,
            api_base=api_base,
            model=model,
            messages=messages,
            thinking_type=thinking_type,
            max_completion_tokens=max_completion_tokens,
            timeout_seconds=timeout_seconds,
        ),
        "litellm_result": run_litellm_format_check(
            api_key=api_key,
            api_base=api_base,
            model=model,
            messages=messages,
            thinking_type=thinking_type,
            max_completion_tokens=max_completion_tokens,
            timeout_seconds=timeout_seconds,
        ),
    }


def build_summary_by_variant(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for variant in PROMPT_VARIANTS:
        variant_results = [item for item in results if item["prompt_variant"]["variant_id"] == variant["variant_id"]]
        summary = {
            "variant_id": variant["variant_id"],
            "variant_name": variant["variant_name"],
            "direct_sdk_exact_format_hits": 0,
            "litellm_exact_format_hits": 0,
            "direct_sdk_first_line_hits": 0,
            "litellm_first_line_hits": 0,
            "direct_sdk_step_heading_hits": 0,
            "litellm_step_heading_hits": 0,
            "direct_sdk_length_finishes": 0,
            "litellm_length_finishes": 0,
        }
        for item in variant_results:
            direct = item["direct_sdk_result"]
            litellm = item["litellm_result"]
            summary["direct_sdk_exact_format_hits"] += int(direct["exact_final_answer_format_present"])
            summary["litellm_exact_format_hits"] += int(litellm["exact_final_answer_format_present"])
            summary["direct_sdk_first_line_hits"] += int(direct["first_line_matches_###_integer"])
            summary["litellm_first_line_hits"] += int(litellm["first_line_matches_###_integer"])
            summary["direct_sdk_step_heading_hits"] += int(direct["contains_markdown_step_heading"])
            summary["litellm_step_heading_hits"] += int(litellm["contains_markdown_step_heading"])
            summary["direct_sdk_length_finishes"] += int(direct["finish_reason"] == "length")
            summary["litellm_length_finishes"] += int(litellm["finish_reason"] == "length")
        summaries.append(summary)
    return summaries


def build_payload(
    *,
    api_base: str,
    model: str,
    dataset_source: str,
    sample_count: int,
    thinking_type: str,
    max_completion_tokens: int,
    timeout_seconds: float,
    proxy_env_detected: dict[str, bool],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": "mimo",
        "backend_family": DEFAULT_BACKEND_FAMILY,
        "path_type": PATH_TYPE,
        "api_base": api_base,
        "model": model,
        "dataset_source": dataset_source,
        "sample_count": sample_count,
        "prompt_variants": [
            {
                "variant_id": variant["variant_id"],
                "variant_name": variant["variant_name"],
                "prompt_type": variant["prompt_type"],
            }
            for variant in PROMPT_VARIANTS
        ],
        "generation_control": {
            "thinking_type": thinking_type,
            "max_completion_tokens": max_completion_tokens,
            "timeout_seconds": timeout_seconds,
        },
        "proxy_env_detected": proxy_env_detected,
        "results": results,
        "summary_by_variant": build_summary_by_variant(results),
        "interpretation": {
            "not_gepa_path": True,
            "not_strict_official_path": True,
            "not_performance_claim": True,
            "not_baseline": True,
            "no_gepa_optimize_called": True,
            "pilot_not_started": True,
        },
    }


def run_prompt_first_format_diagnostic(
    *,
    api_key: str,
    api_base: str,
    model: str,
    sample_count: int,
    thinking_type: str,
    max_completion_tokens: int,
    timeout_seconds: float,
    execute: bool,
    output_root: Path,
) -> Path:
    if not api_base.strip():
        raise ValueError("Stage 2C format-enforcement diagnostic 必须显式提供 MIMO_API_BASE 或 --api-base。")
    if not model.strip():
        raise ValueError("缺少模型名。")
    if sample_count <= 0:
        raise ValueError("sample_count 必须大于 0。")
    if max_completion_tokens <= 0:
        raise ValueError("max_completion_tokens 必须大于 0。")
    if execute and not api_key.strip():
        raise ValueError("Stage 2C format-enforcement execute 模式缺少 MIMO_API_KEY。")

    run_dir = create_run_dir(output_root)
    samples, dataset_source = load_val_samples(sample_count)
    proxy_flags = _proxy_env_detected()

    snapshot = {
        "path_type": PATH_TYPE,
        "provider": "mimo",
        "backend_family": DEFAULT_BACKEND_FAMILY,
        "api_base": api_base,
        "model": model,
        "dataset_source": dataset_source,
        "sample_count": sample_count,
        "prompt_variants": [
            {
                "variant_id": variant["variant_id"],
                "variant_name": variant["variant_name"],
                "prompt_type": variant["prompt_type"],
            }
            for variant in PROMPT_VARIANTS
        ],
        "thinking_type": thinking_type,
        "max_completion_tokens": max_completion_tokens,
        "timeout_seconds": timeout_seconds,
        "execute_diagnostic": execute,
        "not_gepa_path": True,
        "not_strict_official_path": True,
        "not_performance_claim": True,
        "not_baseline": True,
        "pilot_not_started": True,
    }
    write_json(run_dir / "stage2c_prompt_first_input_snapshot.json", snapshot)

    if not execute:
        write_text(
            run_dir / "notes.md",
            "\n".join(
                [
                    "# Stage 2C MiMo prompt-first / format-enforcement diagnostic",
                    "",
                    "- 本脚本不调用 `gepa.optimize()`。",
                    "- 默认只做 dry-run；只有显式 `--execute` 才会发起 direct SDK 与 LiteLLM 小样本请求。",
                    "- 当前只验证格式可达性，不做性能结论，不构成 baseline。",
                    "- 当前固定 `thinking.disabled`、`max_completion_tokens=2048`、`timeout=120`。",
                    "",
                ]
            ),
        )
        return run_dir

    results: list[dict[str, Any]] = []
    for sample_index, sample in enumerate(samples):
        sample_input = str(sample.get("input") or "").strip()
        if not sample_input:
            raise RuntimeError(f"第 {sample_index} 个 val 样本缺少 input。")
        for prompt_variant in PROMPT_VARIANTS:
            results.append(
                run_single_case(
                    api_key=api_key,
                    api_base=api_base,
                    model=model,
                    sample_index=sample_index,
                    sample_input=sample_input,
                    prompt_variant=prompt_variant,
                    thinking_type=thinking_type,
                    max_completion_tokens=max_completion_tokens,
                    timeout_seconds=timeout_seconds,
                )
            )

    payload = build_payload(
        api_base=api_base,
        model=model,
        dataset_source=dataset_source,
        sample_count=sample_count,
        thinking_type=thinking_type,
        max_completion_tokens=max_completion_tokens,
        timeout_seconds=timeout_seconds,
        proxy_env_detected=proxy_flags,
        results=results,
    )
    write_json(run_dir / "stage2c_prompt_first_results.json", payload)
    write_text(
        run_dir / "notes.md",
        "\n".join(
            [
                "# Stage 2C MiMo prompt-first / format-enforcement diagnostic",
                "",
                "- 本脚本不调用 `gepa.optimize()`。",
                "- 本脚本只做 direct SDK 与 LiteLLM 的小样本格式诊断。",
                "- 当前固定 `thinking.disabled`、`max_completion_tokens=2048`、`timeout=120`。",
                "- 重点是验证精确 `### <integer>` 是否可达，而不是模型分数。",
                "",
            ]
        ),
    )
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="运行 Stage 2C MiMo prompt-first / format-enforcement diagnostic。默认仅生成 dry-run snapshot。"
    )
    parser.add_argument("--api-base", default=_env("MIMO_API_BASE"), help="显式 MIMO API Base。")
    parser.add_argument("--model", default=_env("TASK_MODEL", DEFAULT_MODEL), help="模型名。")
    parser.add_argument("--sample-count", type=int, default=DEFAULT_SAMPLE_COUNT, help="真实 AIME val 样本数量，默认 3。")
    parser.add_argument("--thinking-type", default=DEFAULT_THINKING_TYPE, help="当前固定为 disabled。")
    parser.add_argument(
        "--max-completion-tokens",
        type=int,
        default=DEFAULT_MAX_COMPLETION_TOKENS,
        help="当前格式诊断默认 2048。",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="单次 completion 请求超时秒数，默认 120。",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_DIR),
        help="输出目录，默认 outputs/stage2c_mimo_prompt_first_format_enforcement_diagnostic。",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="显式执行 direct SDK / LiteLLM 小样本诊断；默认只做 dry-run。",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = _env("MIMO_API_KEY")
    run_dir = run_prompt_first_format_diagnostic(
        api_key=api_key,
        api_base=args.api_base,
        model=args.model,
        sample_count=args.sample_count,
        thinking_type=args.thinking_type,
        max_completion_tokens=args.max_completion_tokens,
        timeout_seconds=args.timeout_seconds,
        execute=args.execute,
        output_root=Path(args.output_root).resolve(),
    )
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "path_type": PATH_TYPE,
                "execute_diagnostic": bool(args.execute),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
