from __future__ import annotations

import argparse
import inspect
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv
from gepa.examples.aime import init_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DEFAULT_BACKEND_FAMILY, DEFAULT_MIMO_API_BASE
from src.logging_utils import create_run_dir, write_json, write_text
from src.openai_compatible_utils import (
    build_litellm_model_name,
    build_openai_client,
    redact_secret,
    temporary_openai_compatible_env,
)


README_QUICKSTART_SEED_PROMPT = {
    "system_prompt": "You are a helpful assistant. Answer the question. Put your final answer in the format '### <answer>'"
}
DEFAULT_MODELS = ["mimo-v2.5-pro", "mimo-v2-pro", "mimo-v2.5"]
DEFAULT_THINKING_TYPES = ["disabled", "enabled"]
DEFAULT_MAX_COMPLETION_TOKENS = [128, 256, 512, 1024]
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "mimo_aime_completion_diagnosis"


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


def _preview(text: str | None, limit: int = 240) -> str | None:
    if not text:
        return None
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _is_timeout_error(exc: Exception) -> bool:
    error_name = type(exc).__name__.lower()
    message = str(exc).lower()
    return "timeout" in error_name or "timed out" in message or "readtimeout" in error_name


def build_diagnosis_cases(
    *,
    models: Iterable[str],
    thinking_types: Iterable[str],
    max_completion_tokens_values: Iterable[int],
    runners: Iterable[str] = ("openai_sdk", "litellm"),
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for runner in runners:
        for model_name in models:
            for thinking_type in thinking_types:
                for max_completion_tokens in max_completion_tokens_values:
                    cases.append(
                        {
                            "runner": runner,
                            "model": model_name,
                            "thinking_type": thinking_type,
                            "max_completion_tokens": max_completion_tokens,
                        }
                    )
    return cases

def _resolve_cached_aime_train_arrow() -> Path:
    cache_root = (
        Path.home()
        / ".cache"
        / "huggingface"
        / "datasets"
        / "AI-MO___aimo-validation-aime"
        / "default"
        / "0.0.0"
    )
    if not cache_root.exists():
        raise RuntimeError(f"未找到 AIME 训练集缓存目录：{cache_root}")
    candidates = sorted(cache_root.glob("*/aimo-validation-aime-train.arrow"))
    if not candidates:
        raise RuntimeError(f"未找到 AIME 训练集缓存文件：{cache_root}")
    return candidates[-1]


def load_first_val_sample() -> tuple[dict[str, Any], str]:
    dataset_source = f"{inspect.getsourcefile(init_dataset)}:{inspect.getsourcelines(init_dataset)[1]}"
    from datasets import Dataset

    train_arrow_path = _resolve_cached_aime_train_arrow()
    train_rows = Dataset.from_file(str(train_arrow_path))
    train_split = [
        {
            "input": row["problem"],
            "additional_context": {"solution": row["solution"]},
            "answer": "### " + str(row["answer"]),
        }
        for row in train_rows
    ]
    random.Random(0).shuffle(train_split)
    valset = train_split[len(train_split) // 2 :]
    if not valset:
        raise RuntimeError("AIME valset 为空，无法执行 MiMo 单样本诊断。")
    sample = dict(valset[0])
    if not str(sample.get("input") or "").strip():
        raise RuntimeError("AIME 第一个 val 样本缺少 input，无法执行诊断。")
    return sample, f"{dataset_source} | cache_arrow={train_arrow_path}"


def build_messages(question: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": README_QUICKSTART_SEED_PROMPT["system_prompt"]},
        {"role": "user", "content": question},
    ]


def _success_result(
    *,
    runner: str,
    model_name: str,
    thinking_type: str,
    max_completion_tokens: int,
    timeout_seconds: float,
    elapsed_seconds: float,
    response: Any,
) -> dict[str, Any]:
    choice = _get_attr_or_key(response, "choices")[0]
    message = _get_attr_or_key(choice, "message")
    content, reasoning_content = _extract_message_fields(message)
    usage = _usage_payload(_get_attr_or_key(response, "usage"))
    return {
        "runner": runner,
        "model": model_name,
        "litellm_model": build_litellm_model_name(model_name),
        "thinking_type": thinking_type,
        "max_completion_tokens": max_completion_tokens,
        "timeout_seconds": timeout_seconds,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "ok": True,
        "finish_reason": _get_attr_or_key(choice, "finish_reason"),
        "content_empty": not bool(content),
        "reasoning_content_empty": not bool(reasoning_content),
        "content_preview": _preview(content),
        "reasoning_content_preview": _preview(reasoning_content),
        "usage": usage,
        "error_type": None,
        "error_message": None,
        "timed_out": False,
    }


def _error_result(
    *,
    runner: str,
    model_name: str,
    thinking_type: str,
    max_completion_tokens: int,
    timeout_seconds: float,
    elapsed_seconds: float,
    exc: Exception,
    api_key: str,
) -> dict[str, Any]:
    return {
        "runner": runner,
        "model": model_name,
        "litellm_model": build_litellm_model_name(model_name),
        "thinking_type": thinking_type,
        "max_completion_tokens": max_completion_tokens,
        "timeout_seconds": timeout_seconds,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "ok": False,
        "finish_reason": None,
        "content_empty": True,
        "reasoning_content_empty": True,
        "content_preview": None,
        "reasoning_content_preview": None,
        "usage": _usage_payload(None),
        "error_type": type(exc).__name__,
        "error_message": redact_secret(str(exc), api_key),
        "timed_out": _is_timeout_error(exc),
    }


def run_openai_sdk_case(
    *,
    api_key: str,
    api_base: str,
    model_name: str,
    messages: list[dict[str, str]],
    thinking_type: str,
    max_completion_tokens: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    client = build_openai_client(api_key=api_key, api_base=api_base)
    started_at = time.perf_counter()
    try:
        response = client.with_options(timeout=timeout_seconds).chat.completions.create(
            model=model_name,
            messages=messages,
            max_completion_tokens=max_completion_tokens,
            extra_body={"thinking": {"type": thinking_type}},
        )
    except Exception as exc:
        return _error_result(
            runner="openai_sdk",
            model_name=model_name,
            thinking_type=thinking_type,
            max_completion_tokens=max_completion_tokens,
            timeout_seconds=timeout_seconds,
            elapsed_seconds=time.perf_counter() - started_at,
            exc=exc,
            api_key=api_key,
        )
    return _success_result(
        runner="openai_sdk",
        model_name=model_name,
        thinking_type=thinking_type,
        max_completion_tokens=max_completion_tokens,
        timeout_seconds=timeout_seconds,
        elapsed_seconds=time.perf_counter() - started_at,
        response=response,
    )


def run_litellm_case(
    *,
    api_key: str,
    api_base: str,
    model_name: str,
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
                model=build_litellm_model_name(model_name),
                messages=messages,
                max_completion_tokens=max_completion_tokens,
                timeout=timeout_seconds,
                extra_body={"thinking": {"type": thinking_type}},
            )
    except Exception as exc:
        return _error_result(
            runner="litellm",
            model_name=model_name,
            thinking_type=thinking_type,
            max_completion_tokens=max_completion_tokens,
            timeout_seconds=timeout_seconds,
            elapsed_seconds=time.perf_counter() - started_at,
            exc=exc,
            api_key=api_key,
        )
    return _success_result(
        runner="litellm",
        model_name=model_name,
        thinking_type=thinking_type,
        max_completion_tokens=max_completion_tokens,
        timeout_seconds=timeout_seconds,
        elapsed_seconds=time.perf_counter() - started_at,
        response=response,
    )


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    ok_count = sum(1 for item in results if item["ok"])
    timeout_count = sum(1 for item in results if item["timed_out"])
    content_non_empty_count = sum(1 for item in results if item["ok"] and not item["content_empty"])
    reasoning_non_empty_count = sum(1 for item in results if item["ok"] and not item["reasoning_content_empty"])
    return {
        "total_cases": total,
        "ok_count": ok_count,
        "error_count": total - ok_count,
        "timeout_count": timeout_count,
        "content_non_empty_count": content_non_empty_count,
        "reasoning_content_non_empty_count": reasoning_non_empty_count,
    }


def _build_payload(
    *,
    api_base: str,
    dataset_source: str,
    sample: dict[str, Any],
    models: list[str],
    thinking_types: list[str],
    max_completion_tokens_values: list[int],
    timeout_seconds: float,
    results: list[dict[str, Any]],
    status: str,
    completed_cases: int,
    total_cases: int,
) -> dict[str, Any]:
    question = str(sample["input"])
    return {
        "provider": "mimo",
        "backend_family": DEFAULT_BACKEND_FAMILY,
        "api_base": api_base,
        "path_type": "stage2_mimo_controlled_generation_diagnosis",
        "status": status,
        "completed_cases": completed_cases,
        "total_cases": total_cases,
        "dataset_source": dataset_source,
        "sample_index": 0,
        "sample_answer": sample.get("answer"),
        "question_preview": _preview(question, limit=400),
        "seed_prompt": README_QUICKSTART_SEED_PROMPT,
        "models": models,
        "thinking_types": thinking_types,
        "max_completion_tokens_values": max_completion_tokens_values,
        "timeout_seconds": timeout_seconds,
        "summary": summarize_results(results),
        "results": results,
    }


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="执行 MiMo 单样本 AIME completion 诊断矩阵，只测 direct OpenAI SDK 与 LiteLLM，不进入 gepa.optimize。"
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
        help="待诊断模型列表。默认 mimo-v2.5-pro / mimo-v2-pro / mimo-v2.5。",
    )
    parser.add_argument(
        "--thinking-types",
        nargs="+",
        default=DEFAULT_THINKING_TYPES,
        help="thinking.type 取值列表。默认 disabled enabled。",
    )
    parser.add_argument(
        "--max-completion-tokens",
        nargs="+",
        type=int,
        default=DEFAULT_MAX_COMPLETION_TOKENS,
        help="max_completion_tokens 列表。默认 128 256 512 1024。",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="单请求 timeout 秒数。默认 60。",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_DIR),
        help="输出根目录。默认 outputs/mimo_aime_completion_diagnosis。",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = _env("MIMO_API_KEY")
    api_base = _env("MIMO_API_BASE", DEFAULT_MIMO_API_BASE)
    if not api_key:
        raise SystemExit("缺少 MIMO_API_KEY，无法执行 MiMo completion 诊断。")

    run_dir = create_run_dir(Path(args.output_root).resolve())
    sample, dataset_source = load_first_val_sample()
    question = str(sample["input"])
    messages = build_messages(question)

    cases = build_diagnosis_cases(
        models=args.models,
        thinking_types=args.thinking_types,
        max_completion_tokens_values=args.max_completion_tokens,
    )
    results: list[dict[str, Any]] = []
    total_cases = len(cases)
    write_json(
        run_dir / "diagnosis_results.json",
        _build_payload(
            api_base=api_base,
            dataset_source=dataset_source,
            sample=sample,
            models=list(args.models),
            thinking_types=list(args.thinking_types),
            max_completion_tokens_values=list(args.max_completion_tokens),
            timeout_seconds=args.timeout_seconds,
            results=results,
            status="running",
            completed_cases=0,
            total_cases=total_cases,
        ),
    )
    for case in cases:
        if case["runner"] == "openai_sdk":
            result = run_openai_sdk_case(
                api_key=api_key,
                api_base=api_base,
                model_name=case["model"],
                messages=messages,
                thinking_type=case["thinking_type"],
                max_completion_tokens=case["max_completion_tokens"],
                timeout_seconds=args.timeout_seconds,
            )
        else:
            result = run_litellm_case(
                api_key=api_key,
                api_base=api_base,
                model_name=case["model"],
                messages=messages,
                thinking_type=case["thinking_type"],
                max_completion_tokens=case["max_completion_tokens"],
                timeout_seconds=args.timeout_seconds,
            )
        results.append(result)
        write_json(
            run_dir / "diagnosis_results.json",
            _build_payload(
                api_base=api_base,
                dataset_source=dataset_source,
                sample=sample,
                models=list(args.models),
                thinking_types=list(args.thinking_types),
                max_completion_tokens_values=list(args.max_completion_tokens),
                timeout_seconds=args.timeout_seconds,
                results=results,
                status="running",
                completed_cases=len(results),
                total_cases=total_cases,
            ),
        )
    payload = _build_payload(
        api_base=api_base,
        dataset_source=dataset_source,
        sample=sample,
        models=list(args.models),
        thinking_types=list(args.thinking_types),
        max_completion_tokens_values=list(args.max_completion_tokens),
        timeout_seconds=args.timeout_seconds,
        results=results,
        status="completed",
        completed_cases=len(results),
        total_cases=total_cases,
    )
    write_json(run_dir / "diagnosis_results.json", payload)
    write_text(
        run_dir / "notes.md",
        "\n".join(
            [
                "# MiMo AIME completion diagnosis",
                "",
                "- 本目录记录的是 direct OpenAI SDK 与 LiteLLM 的单样本 AIME completion 诊断。",
                "- 该脚本不调用 `gepa.optimize()`，不修改 `DefaultAdapter`，不修改 evaluator。",
                "- 若需显式 `thinking.disabled` 或 token cap 才能稳定返回，只能解释为诊断路径，不是 strict default path。",
                "",
            ]
        ),
    )
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "result_file": str(run_dir / "diagnosis_results.json"),
                "summary": payload["summary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
