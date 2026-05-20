from __future__ import annotations

import argparse
import concurrent.futures
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
from scripts.stage2d_audit_aime_evaluator_format_contract import (
    classify_failure_mode,
    relaxed_extract_answer,
    strict_regex_match_hash_integer,
)


DEFAULT_MODEL = "mimo-v2.5-pro"
DEFAULT_THINKING_TYPE = "disabled"
DEFAULT_MAX_COMPLETION_TOKENS = 2048
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_SAMPLE_COUNT = 5
DEFAULT_MAX_WORKERS = 3
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "stage2d_official_contract_prompt_adaptation_diagnostic"
DEFAULT_RESULT_REPORT = PROJECT_ROOT / "reports" / "stage2d_official_contract_prompt_adaptation_result.md"
PATH_TYPE = "stage2d_official_contract_prompt_adaptation_diagnostic"
TRANSPORT_PATHS = ("direct_sdk", "litellm")

PROMPT_VARIANTS: list[dict[str, str]] = [
    {
        "variant_id": "D",
        "variant_name": "exact_substring_final_answer_only",
        "prompt_type": "stage2d_exact_substring_final_answer_only",
        "system_prompt": "\n".join(
            [
                "Solve the problem internally. Do not show your reasoning.",
                "",
                "Your entire response must be exactly one line.",
                "It must match this pattern:",
                "### 123",
                "",
                "Replace 123 with the final integer answer.",
                'Do not write "<answer>".',
                "Do not write XML tags.",
                "Do not write explanations.",
                "Do not write Markdown headings.",
            ]
        ),
    },
    {
        "variant_id": "E",
        "variant_name": "final_answer_only",
        "prompt_type": "stage2d_final_answer_only",
        "system_prompt": "\n".join(
            [
                "Compute the answer internally.",
                "",
                "The first and only line of your response must be:",
                "### N",
                "",
                "where N is the final nonnegative integer answer.",
                "Do not include any other text.",
            ]
        ),
    },
    {
        "variant_id": "F",
        "variant_name": "official_evaluator_contract_explicit",
        "prompt_type": "stage2d_official_evaluator_contract_explicit",
        "system_prompt": "\n".join(
            [
                "The grader only checks whether your response contains the exact string:",
                "### N",
                "",
                "where N is the final integer answer.",
                "",
                'Your response must contain exactly one such line and no other "###" headings.',
                "",
                "Example of valid output:",
                "### 72",
            ]
        ),
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


def _preview(text: str | None, limit: int = 320) -> str | None:
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


def first_line_matches_hash_integer(text: str | None) -> bool:
    first_line = _first_nonempty_line(text)
    return bool(first_line and re.fullmatch(r"###\s*\d+", first_line))


def contains_xml_tag_placeholder(text: str | None) -> bool:
    if not text:
        return False
    return re.search(r"</?\s*answer\s*>", text, re.IGNORECASE) is not None


def contains_markdown_heading_misuse(text: str | None) -> bool:
    if not text:
        return False
    return re.search(r"(?mi)^###\s*(step|part|solution|analysis)\b", text) is not None


def expected_official_answer(sample: dict[str, Any]) -> str:
    raw_answer = str(sample.get("answer") or "").strip()
    if not raw_answer:
        raise ValueError("AIME val 样本缺少 answer。")
    if raw_answer.startswith("### "):
        return raw_answer
    return f"### {raw_answer}"


def expected_integer_from_official_answer(official_answer: str) -> str:
    normalized = official_answer.strip()
    if not normalized.startswith("### "):
        raise ValueError(f"official answer 不符合预期：{official_answer!r}")
    integer_text = normalized.removeprefix("### ").strip()
    if not re.fullmatch(r"\d+", integer_text):
        raise ValueError(f"official answer 不是整数格式：{official_answer!r}")
    return integer_text


def evaluate_response_text(response_text: str | None, expected_answer: str) -> dict[str, Any]:
    text = response_text or ""
    official_ok = expected_answer in text
    official_score = 1.0 if official_ok else 0.0
    normalized_answer = relaxed_extract_answer(text)
    expected_integer = expected_integer_from_official_answer(expected_answer)
    normalized_score = 1.0 if normalized_answer == expected_integer else 0.0
    return {
        "official_evaluator_compatible": official_ok,
        "contains_exact_official_answer_string": official_ok,
        "strict_regex_match_###_integer": strict_regex_match_hash_integer(text),
        "first_line_matches_###_integer": first_line_matches_hash_integer(text),
        "contains_xml_tag_placeholder": contains_xml_tag_placeholder(text),
        "contains_markdown_heading_misuse": contains_markdown_heading_misuse(text),
        "relaxed_human_extractable": normalized_answer is not None,
        "normalized_extracted_answer": normalized_answer,
        "official_score": official_score,
        "normalized_score": normalized_score,
        "classified_failure_mode": classify_failure_mode(text, official_score),
    }


def build_model_result(
    *,
    content: str | None,
    reasoning_content: str | None = None,
    finish_reason: str | None = None,
    elapsed_seconds: float = 0.0,
    status_code: int | None = None,
    usage: Any = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    content_nonempty = bool(content)
    return {
        "ok": content_nonempty and error_type is None,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "status_code": status_code,
        "content_nonempty": content_nonempty,
        "content": content,
        "content_preview": _preview(content),
        "reasoning_content_nonempty": bool(reasoning_content),
        "finish_reason": finish_reason,
        "usage": _usage_payload(usage),
        "error_type": error_type if error_type else (None if content_nonempty else "EmptyContent"),
        "error_message": error_message if error_message else (None if content_nonempty else "模型调用成功，但 content 为空。"),
    }


def _success_model_result(*, response: Any, elapsed_seconds: float) -> dict[str, Any]:
    choice = _get_attr_or_key(response, "choices")[0]
    message = _get_attr_or_key(choice, "message")
    content, reasoning_content = _extract_message_fields(message)
    return build_model_result(
        content=content,
        reasoning_content=reasoning_content,
        finish_reason=_get_attr_or_key(choice, "finish_reason"),
        elapsed_seconds=elapsed_seconds,
        status_code=_get_attr_or_key(response, "status_code"),
        usage=_get_attr_or_key(response, "usage"),
    )


def _error_model_result(*, exc: Exception, api_key: str, elapsed_seconds: float) -> dict[str, Any]:
    return build_model_result(
        content=None,
        finish_reason=None,
        elapsed_seconds=elapsed_seconds,
        status_code=_extract_status_code(exc),
        usage=None,
        error_type=type(exc).__name__,
        error_message=redact_secret(str(exc), api_key),
    )


def build_messages(*, system_prompt: str, question: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]


def run_direct_sdk_completion(
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
        return _error_model_result(
            exc=exc,
            api_key=api_key,
            elapsed_seconds=time.perf_counter() - started_at,
        )
    return _success_model_result(response=response, elapsed_seconds=time.perf_counter() - started_at)


def run_litellm_completion(
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
        return _error_model_result(
            exc=exc,
            api_key=api_key,
            elapsed_seconds=time.perf_counter() - started_at,
        )
    return _success_model_result(response=response, elapsed_seconds=time.perf_counter() - started_at)


def load_val_samples(sample_count: int) -> tuple[list[dict[str, Any]], str]:
    _, valset, _, dataset_source = load_dataset_via_stage2c_path()
    if sample_count <= 0:
        raise ValueError("sample_count 必须大于 0。")
    if len(valset) < sample_count:
        raise ValueError(f"valset 样本数不足，无法读取前 {sample_count} 个样本。")
    samples = [dict(valset[idx]) for idx in range(sample_count)]
    return samples, dataset_source


def _prompt_variant_public_payload(variant: dict[str, str]) -> dict[str, str]:
    return {
        "variant_id": variant["variant_id"],
        "variant_name": variant["variant_name"],
        "prompt_type": variant["prompt_type"],
        "system_prompt": variant["system_prompt"],
    }


def build_case(
    *,
    sample_index: int,
    prompt_variant: dict[str, str],
    transport_path: str,
    expected_answer: str,
    model_result: dict[str, Any],
) -> dict[str, Any]:
    evaluation = evaluate_response_text(model_result.get("content"), expected_answer)
    return {
        "sample_index": sample_index,
        "prompt_variant": _prompt_variant_public_payload(prompt_variant),
        "transport_path": transport_path,
        "expected_official_answer": expected_answer,
        "expected_integer_answer": expected_integer_from_official_answer(expected_answer),
        "model_result": model_result,
        "evaluation": evaluation,
    }


def run_single_case(
    *,
    api_key: str,
    api_base: str,
    model: str,
    sample_index: int,
    sample_input: str,
    expected_answer: str,
    prompt_variant: dict[str, str],
    thinking_type: str,
    max_completion_tokens: int,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    messages = build_messages(system_prompt=prompt_variant["system_prompt"], question=sample_input)
    direct_result = run_direct_sdk_completion(
        api_key=api_key,
        api_base=api_base,
        model=model,
        messages=messages,
        thinking_type=thinking_type,
        max_completion_tokens=max_completion_tokens,
        timeout_seconds=timeout_seconds,
    )
    litellm_result = run_litellm_completion(
        api_key=api_key,
        api_base=api_base,
        model=model,
        messages=messages,
        thinking_type=thinking_type,
        max_completion_tokens=max_completion_tokens,
        timeout_seconds=timeout_seconds,
    )
    return [
        build_case(
            sample_index=sample_index,
            prompt_variant=prompt_variant,
            transport_path="direct_sdk",
            expected_answer=expected_answer,
            model_result=direct_result,
        ),
        build_case(
            sample_index=sample_index,
            prompt_variant=prompt_variant,
            transport_path="litellm",
            expected_answer=expected_answer,
            model_result=litellm_result,
        ),
    ]


def _case_sort_key(case: dict[str, Any]) -> tuple[int, str, int]:
    transport_rank = TRANSPORT_PATHS.index(case["transport_path"])
    return (
        int(case["sample_index"]),
        str(case["prompt_variant"]["variant_id"]),
        transport_rank,
    )


def build_summary(cases: list[dict[str, Any]], sample_count: int) -> dict[str, Any]:
    summary_by_variant: list[dict[str, Any]] = []
    passing_variants: list[str] = []
    for variant in PROMPT_VARIANTS:
        variant_id = variant["variant_id"]
        variant_summary: dict[str, Any] = {
            "variant_id": variant_id,
            "variant_name": variant["variant_name"],
            "transport_paths": {},
            "both_paths_pass_gate": False,
        }
        path_passes: list[bool] = []
        for transport_path in TRANSPORT_PATHS:
            path_cases = [
                case
                for case in cases
                if case["prompt_variant"]["variant_id"] == variant_id and case["transport_path"] == transport_path
            ]

            def _count(field_name: str) -> int:
                return sum(1 for case in path_cases if bool(case["evaluation"][field_name]))

            length_finishes = sum(1 for case in path_cases if case["model_result"]["finish_reason"] == "length")
            xml_tag_hits = _count("contains_xml_tag_placeholder")
            markdown_heading_hits = _count("contains_markdown_heading_misuse")
            official_hits = _count("official_evaluator_compatible")
            pass_gate = (
                len(path_cases) == sample_count
                and official_hits == sample_count
                and length_finishes == 0
                and xml_tag_hits == 0
                and markdown_heading_hits == 0
            )
            path_passes.append(pass_gate)
            variant_summary["transport_paths"][transport_path] = {
                "total_cases": len(path_cases),
                "content_nonempty_count": sum(1 for case in path_cases if case["model_result"]["content_nonempty"]),
                "official_evaluator_compatible_count": official_hits,
                "contains_exact_official_answer_string_count": _count("contains_exact_official_answer_string"),
                "strict_regex_match_###_integer_count": _count("strict_regex_match_###_integer"),
                "first_line_matches_###_integer_count": _count("first_line_matches_###_integer"),
                "contains_xml_tag_placeholder_count": xml_tag_hits,
                "contains_markdown_heading_misuse_count": markdown_heading_hits,
                "relaxed_human_extractable_count": _count("relaxed_human_extractable"),
                "normalized_score_count": sum(
                    1 for case in path_cases if float(case["evaluation"]["normalized_score"]) == 1.0
                ),
                "finish_reason_length_count": length_finishes,
                "pass_gate": pass_gate,
            }
        variant_summary["both_paths_pass_gate"] = all(path_passes) if path_passes else False
        if variant_summary["both_paths_pass_gate"]:
            passing_variants.append(variant_id)
        summary_by_variant.append(variant_summary)

    return {
        "sample_count": sample_count,
        "summary_by_variant": summary_by_variant,
        "passing_variants": passing_variants,
        "any_variant_passed_both_paths": bool(passing_variants),
        "pass_standard": {
            "direct_sdk_official_evaluator_compatible": f"{sample_count}/{sample_count}",
            "litellm_official_evaluator_compatible": f"{sample_count}/{sample_count}",
            "finish_reason_length_count": 0,
            "contains_xml_tag_placeholder_count": 0,
            "contains_markdown_heading_misuse_count": 0,
        },
    }


def _sample_snapshot(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshot = []
    for index, sample in enumerate(samples):
        answer = expected_official_answer(sample)
        snapshot.append(
            {
                "sample_index": index,
                "expected_official_answer": answer,
                "expected_integer_answer": expected_integer_from_official_answer(answer),
                "input_preview": _preview(str(sample.get("input") or ""), limit=180),
            }
        )
    return snapshot


def _relative_to_project(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def build_payload(
    *,
    api_base: str,
    model: str,
    dataset_source: str,
    sample_count: int,
    thinking_type: str,
    max_completion_tokens: int,
    timeout_seconds: float,
    execute: bool,
    max_workers: int,
    run_dir: Path,
    samples: list[dict[str, Any]],
    cases: list[dict[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": "mimo",
        "backend_family": DEFAULT_BACKEND_FAMILY,
        "path_type": PATH_TYPE,
        "api_base": api_base,
        "model": model,
        "dataset_source": dataset_source,
        "sample_count": sample_count,
        "run_dir": _relative_to_project(run_dir),
        "prompt_variants": [_prompt_variant_public_payload(variant) for variant in PROMPT_VARIANTS],
        "generation_control": {
            "thinking_type": thinking_type,
            "max_completion_tokens": max_completion_tokens,
            "timeout_seconds": timeout_seconds,
        },
        "execution_control": {
            "max_workers": max_workers,
        },
        "proxy_env_detected": _proxy_env_detected(),
        "sample_snapshot": _sample_snapshot(samples),
        "execute_diagnostic": execute,
        "model_invocation_attempted": execute,
        "not_gepa_path": True,
        "not_strict_official_path": True,
        "not_performance_claim": True,
        "not_baseline": True,
        "not_pilot": True,
        "no_gepa_optimize_called": True,
        "normalized_score_is_diagnostic_only": True,
        "official_score_source": "official evaluator contract: expected official answer string is contained in response",
    }
    if execute:
        payload["cases"] = cases
        payload["summary"] = build_summary(cases, sample_count)
    else:
        payload["cases"] = []
        payload["summary"] = {
            "dry_run_only": True,
            "any_variant_passed_both_paths": False,
            "passing_variants": [],
        }
    return payload


def write_result_report(report_path: Path, payload: dict[str, Any]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Stage 2D Phase 2 Official-Contract Prompt Adaptation Result",
        "",
        "## 定位",
        "",
        "- `Stage 2D Phase 2: official-contract prompt adaptation diagnostic`",
        "- `not_gepa_path = true`",
        "- `not_baseline = true`",
        "- `not_pilot = true`",
        "- `not_performance_claim = true`",
        "- `normalized_score_is_diagnostic_only = true`",
        "",
        "## 运行配置",
        "",
        f"- provider：`{payload['provider']}`",
        f"- model：`{payload['model']}`",
        f"- api_base：`{payload['api_base']}`",
        f"- sample_count：`{payload['sample_count']}`",
        f"- thinking：`{payload['generation_control']['thinking_type']}`",
        f"- max_completion_tokens：`{payload['generation_control']['max_completion_tokens']}`",
        f"- timeout：`{payload['generation_control']['timeout_seconds']}`",
        f"- max_workers：`{payload['execution_control']['max_workers']}`",
        f"- execute_diagnostic：`{payload['execute_diagnostic']}`",
        f"- 输出目录：`{payload['run_dir']}`",
        "",
        "## 边界声明",
        "",
        "- 本阶段未调用 GEPA optimizer。",
        "- 本阶段未运行 GEPA smoke。",
        "- 本阶段未进入 pilot。",
        "- 本阶段未修改 official evaluator 或 optimizer。",
        "- `official_score` 与 `normalized_score` 分开记录；`normalized_score` 仅为诊断字段。",
        "",
    ]
    if not payload["execute_diagnostic"]:
        lines.extend(
            [
                "## Dry-run 结果",
                "",
                "- 本次只生成输入快照，没有调用模型。",
                "- 因未调用模型，不判断是否满足 `5/5 official_evaluator_compatible`。",
                "",
            ]
        )
        write_text(report_path, "\n".join(lines) + "\n")
        return

    summary = payload["summary"]
    lines.extend(
        [
            "## 结果摘要",
            "",
            f"- 是否存在同时通过 direct SDK 与 LiteLLM 的 prompt variant：`{summary['any_variant_passed_both_paths']}`",
            f"- 通过 variant：`{summary['passing_variants']}`",
            "",
        ]
    )
    for variant_summary in summary["summary_by_variant"]:
        lines.extend(
            [
                f"### Variant {variant_summary['variant_id']}：{variant_summary['variant_name']}",
                "",
            ]
        )
        for transport_path in TRANSPORT_PATHS:
            path_summary = variant_summary["transport_paths"][transport_path]
            lines.extend(
                [
                    f"- {transport_path}：",
                    f"  - official_evaluator_compatible：`{path_summary['official_evaluator_compatible_count']} / {path_summary['total_cases']}`",
                    f"  - strict_regex_match_###_integer：`{path_summary['strict_regex_match_###_integer_count']} / {path_summary['total_cases']}`",
                    f"  - first_line_matches_###_integer：`{path_summary['first_line_matches_###_integer_count']} / {path_summary['total_cases']}`",
                    f"  - contains_xml_tag_placeholder：`{path_summary['contains_xml_tag_placeholder_count']}`",
                    f"  - contains_markdown_heading_misuse：`{path_summary['contains_markdown_heading_misuse_count']}`",
                    f"  - finish_reason = length：`{path_summary['finish_reason_length_count']}`",
                    f"  - pass_gate：`{path_summary['pass_gate']}`",
                ]
            )
        lines.extend(
            [
                f"- both_paths_pass_gate：`{variant_summary['both_paths_pass_gate']}`",
                "",
            ]
        )

    if summary["any_variant_passed_both_paths"]:
        conclusion = "至少一个 prompt variant 达到 Stage 2D Phase 2 通过标准，可以进入 adapted GEPA smoke 的设计讨论，但仍不能直接进入 pilot。"
    else:
        conclusion = "没有 prompt variant 同时满足 direct SDK 与 LiteLLM 的 `5/5 official_evaluator_compatible` 通过标准；只能写成 partial improvement 或不稳定，不得进入 GEPA adapted smoke。"
    lines.extend(
        [
            "## 结论",
            "",
            f"- {conclusion}",
            "- 本结果不是 MiMo baseline，不是 strict official path，不是性能结论。",
            "",
        ]
    )
    write_text(report_path, "\n".join(lines) + "\n")


def run_official_contract_prompt_adaptation(
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
    max_workers: int = DEFAULT_MAX_WORKERS,
    result_report_path: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    if not api_base.strip():
        raise ValueError("Stage 2D Phase 2 必须显式提供 MIMO_API_BASE 或 --api-base。")
    if not model.strip():
        raise ValueError("缺少模型名。")
    if sample_count <= 0:
        raise ValueError("sample_count 必须大于 0。")
    if max_completion_tokens <= 0:
        raise ValueError("max_completion_tokens 必须大于 0。")
    if max_workers <= 0:
        raise ValueError("max_workers 必须大于 0。")
    if execute and not api_key.strip():
        raise ValueError("Stage 2D Phase 2 execute 模式缺少 MIMO_API_KEY。")

    run_dir = create_run_dir(output_root)
    samples, dataset_source = load_val_samples(sample_count)
    cases: list[dict[str, Any]] = []

    if execute:
        task_specs: list[tuple[int, str, str, dict[str, str]]] = []
        for sample_index, sample in enumerate(samples):
            sample_input = str(sample.get("input") or "").strip()
            if not sample_input:
                raise RuntimeError(f"第 {sample_index} 个 val 样本缺少 input。")
            answer = expected_official_answer(sample)
            for prompt_variant in PROMPT_VARIANTS:
                task_specs.append((sample_index, sample_input, answer, prompt_variant))

        total_groups = len(task_specs)
        completed_groups = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    run_single_case,
                    api_key=api_key,
                    api_base=api_base,
                    model=model,
                    sample_index=sample_index,
                    sample_input=sample_input,
                    expected_answer=answer,
                    prompt_variant=prompt_variant,
                    thinking_type=thinking_type,
                    max_completion_tokens=max_completion_tokens,
                    timeout_seconds=timeout_seconds,
                ): (sample_index, prompt_variant["variant_id"])
                for sample_index, sample_input, answer, prompt_variant in task_specs
            }
            for future in concurrent.futures.as_completed(future_map):
                sample_index, variant_id = future_map[future]
                future_cases = future.result()
                cases.extend(future_cases)
                completed_groups += 1
                print(
                    json.dumps(
                        {
                            "event": "stage2d_progress",
                            "completed_groups": completed_groups,
                            "total_groups": total_groups,
                            "sample_index": sample_index,
                            "variant_id": variant_id,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
        cases.sort(key=_case_sort_key)

    payload = build_payload(
        api_base=api_base,
        model=model,
        dataset_source=dataset_source,
        sample_count=sample_count,
        thinking_type=thinking_type,
        max_completion_tokens=max_completion_tokens,
        timeout_seconds=timeout_seconds,
        execute=execute,
        max_workers=max_workers,
        run_dir=run_dir,
        samples=samples,
        cases=cases,
    )
    write_json(run_dir / "stage2d_official_contract_prompt_adaptation_input_snapshot.json", payload)
    if execute:
        write_json(run_dir / "stage2d_official_contract_prompt_adaptation_results.json", payload)
    write_text(
        run_dir / "notes.md",
        "\n".join(
            [
                "# Stage 2D Phase 2 official-contract prompt adaptation diagnostic",
                "",
                "- 本脚本不调用 GEPA optimizer。",
                "- 本脚本默认 dry-run；只有显式 `--execute` 才会发起 direct SDK 与 LiteLLM 请求。",
                "- 本脚本只诊断 official output contract adherence，不写 baseline 或性能结论。",
                "- `normalized_score` 仅用于诊断 relaxed extraction，不是 GEPA official score。",
                "",
            ]
        ),
    )
    if result_report_path is not None:
        write_result_report(result_report_path, payload)
    return run_dir, payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="运行 Stage 2D Phase 2 MiMo official-contract prompt adaptation diagnostic。默认只做 dry-run。"
    )
    parser.add_argument("--api-base", default=_env("MIMO_API_BASE"), help="显式 MIMO API Base。")
    parser.add_argument("--model", default=_env("TASK_MODEL", DEFAULT_MODEL), help="模型名。")
    parser.add_argument("--sample-count", type=int, default=DEFAULT_SAMPLE_COUNT, help="真实 AIME val 样本数量，默认 5。")
    parser.add_argument("--thinking-type", default=DEFAULT_THINKING_TYPE, help="当前固定为 disabled。")
    parser.add_argument(
        "--max-completion-tokens",
        type=int,
        default=DEFAULT_MAX_COMPLETION_TOKENS,
        help="当前 official-contract prompt 诊断默认 2048。",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="单次 completion 请求超时秒数，默认 120。",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="并发执行的 sample-variant 任务数，默认 3。",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_DIR),
        help="输出目录，默认 outputs/stage2d_official_contract_prompt_adaptation_diagnostic。",
    )
    parser.add_argument(
        "--result-report",
        default=str(DEFAULT_RESULT_REPORT),
        help="结果报告路径，默认 reports/stage2d_official_contract_prompt_adaptation_result.md。",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="显式执行 direct SDK / LiteLLM 小样本诊断；默认只做 dry-run。",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = _env("MIMO_API_KEY")
    run_dir, payload = run_official_contract_prompt_adaptation(
        api_key=api_key,
        api_base=args.api_base,
        model=args.model,
        sample_count=args.sample_count,
        thinking_type=args.thinking_type,
        max_completion_tokens=args.max_completion_tokens,
        timeout_seconds=args.timeout_seconds,
        execute=args.execute,
        max_workers=args.max_workers,
        output_root=Path(args.output_root).resolve(),
        result_report_path=Path(args.result_report).resolve() if args.result_report else None,
    )
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "path_type": PATH_TYPE,
                "execute_diagnostic": bool(args.execute),
                "any_variant_passed_both_paths": payload["summary"].get("any_variant_passed_both_paths"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
