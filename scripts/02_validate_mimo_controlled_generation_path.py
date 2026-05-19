from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from gepa.examples.aime import init_dataset
from openai import APIStatusError


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
DEFAULT_MODEL = "mimo-v2.5-pro"
DEFAULT_THINKING_TYPE = "disabled"
DEFAULT_MAX_COMPLETION_TOKENS = 512
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "mimo_controlled_generation_validation"


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


def load_first_val_sample_via_init_dataset() -> tuple[dict[str, Any], str]:
    with _patch_datasets_load_dataset_from_local_cache():
        trainset, valset, _ = init_dataset()
    if not valset:
        raise RuntimeError("官方 `init_dataset()` 返回的 valset 为空，无法执行 Stage 2B 验证。")
    sample = dict(valset[0])
    if not str(sample.get("input") or "").strip():
        raise RuntimeError("官方 `init_dataset()` 返回的第一个 val 样本缺少 input。")
    return sample, "gepa.examples.aime.init_dataset() with local cache-backed load_dataset"


def build_messages(question: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": README_QUICKSTART_SEED_PROMPT["system_prompt"]},
        {"role": "user", "content": question},
    ]


def _success_result(*, response: Any, elapsed_seconds: float) -> dict[str, Any]:
    choice = _get_attr_or_key(response, "choices")[0]
    message = _get_attr_or_key(choice, "message")
    content, reasoning_content = _extract_message_fields(message)
    content_nonempty = bool(content)
    return {
        "ok": content_nonempty,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "status_code": _get_attr_or_key(response, "status_code"),
        "content_nonempty": content_nonempty,
        "content_preview": _preview(content),
        "reasoning_content_nonempty": bool(reasoning_content),
        "finish_reason": _get_attr_or_key(choice, "finish_reason"),
        "usage": _usage_payload(_get_attr_or_key(response, "usage")),
        "error_type": None if content_nonempty else "EmptyContent",
        "error_message": None if content_nonempty else "模型返回成功，但 content 为空。",
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
        "error_type": type(exc).__name__,
        "error_message": redact_secret(str(exc), api_key),
    }


def run_direct_sdk_controlled_generation(
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
    return _success_result(
        response=response,
        elapsed_seconds=time.perf_counter() - started_at,
    )


def run_litellm_controlled_generation(
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
    return _success_result(
        response=response,
        elapsed_seconds=time.perf_counter() - started_at,
    )


def build_controlled_generation_payload(
    *,
    api_base: str,
    model: str,
    dataset_source: str,
    sample_index: int,
    direct_sdk_result: dict[str, Any],
    litellm_result: dict[str, Any],
    thinking_type: str,
    max_completion_tokens: int,
    timeout_seconds: float,
    proxy_env_detected: dict[str, bool],
) -> dict[str, Any]:
    controlled_generation_path_passed = bool(direct_sdk_result["ok"] and litellm_result["ok"])
    return {
        "provider": "mimo",
        "backend_family": DEFAULT_BACKEND_FAMILY,
        "path_type": "stage2b_mimo_controlled_generation_diagnostic_path",
        "api_base": api_base,
        "model": model,
        "dataset_source": dataset_source,
        "sample_index": sample_index,
        "prompt_type": "readme_quickstart_seed_prompt",
        "generation_control": {
            "thinking_type": thinking_type,
            "max_completion_tokens": max_completion_tokens,
            "timeout_seconds": timeout_seconds,
        },
        "direct_sdk_result": direct_sdk_result,
        "litellm_result": litellm_result,
        "proxy_env_detected": proxy_env_detected,
        "interpretation": {
            "controlled_generation_path_passed": controlled_generation_path_passed,
            "controlled_generation_path_failed": not controlled_generation_path_passed,
            "not_strict_official_path": True,
            "not_performance_claim": True,
            "no_gepa_optimize_called": True,
        },
    }


def run_controlled_generation_validation(
    *,
    api_key: str,
    api_base: str,
    model: str,
    thinking_type: str,
    max_completion_tokens: int,
    timeout_seconds: float,
    output_root: Path,
) -> Path:
    if not api_key.strip():
        raise ValueError("缺少 MIMO_API_KEY，无法执行 Stage 2B 验证。")
    if not model.strip():
        raise ValueError("缺少模型名，无法执行 Stage 2B 验证。")

    run_dir = create_run_dir(output_root)
    sample, dataset_source = load_first_val_sample_via_init_dataset()
    messages = build_messages(str(sample["input"]))
    proxy_flags = _proxy_env_detected()

    direct_sdk_result = run_direct_sdk_controlled_generation(
        api_key=api_key,
        api_base=api_base,
        model=model,
        messages=messages,
        thinking_type=thinking_type,
        max_completion_tokens=max_completion_tokens,
        timeout_seconds=timeout_seconds,
    )
    litellm_result = run_litellm_controlled_generation(
        api_key=api_key,
        api_base=api_base,
        model=model,
        messages=messages,
        thinking_type=thinking_type,
        max_completion_tokens=max_completion_tokens,
        timeout_seconds=timeout_seconds,
    )

    payload = build_controlled_generation_payload(
        api_base=api_base,
        model=model,
        dataset_source=dataset_source,
        sample_index=0,
        direct_sdk_result=direct_sdk_result,
        litellm_result=litellm_result,
        thinking_type=thinking_type,
        max_completion_tokens=max_completion_tokens,
        timeout_seconds=timeout_seconds,
        proxy_env_detected=proxy_flags,
    )
    write_json(run_dir / "controlled_generation_results.json", payload)
    write_text(
        run_dir / "notes.md",
        "\n".join(
            [
                "# Stage 2B MiMo controlled-generation diagnostic path",
                "",
                "- 本脚本不调用 `gepa.optimize()`。",
                "- 本脚本不修改 `DefaultAdapter`、evaluator 或 GEPA optimizer。",
                "- 本脚本显式使用 `thinking.disabled` 与 `max_completion_tokens` 上限，因此不是 strict official path。",
                "",
            ]
        ),
    )
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="验证 Stage 2B: MiMo controlled-generation diagnostic path，不进入 gepa.optimize。"
    )
    parser.add_argument("--model", default=_env("TASK_MODEL", DEFAULT_MODEL), help="模型名，默认 mimo-v2.5-pro。")
    parser.add_argument(
        "--api-base",
        default=_env("MIMO_API_BASE", DEFAULT_MIMO_API_BASE),
        help="OpenAI-compatible Base URL，默认 token-plan-cn.xiaomimimo.com/v1。",
    )
    parser.add_argument(
        "--thinking-type",
        default=DEFAULT_THINKING_TYPE,
        help="thinking.type，默认 disabled。",
    )
    parser.add_argument(
        "--max-completion-tokens",
        type=int,
        default=DEFAULT_MAX_COMPLETION_TOKENS,
        help="max_completion_tokens，默认 512。",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="请求超时秒数，默认 120。",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_DIR),
        help="输出目录，默认 outputs/mimo_controlled_generation_validation。",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = _env("MIMO_API_KEY")
    run_dir = run_controlled_generation_validation(
        api_key=api_key,
        api_base=args.api_base,
        model=args.model,
        thinking_type=args.thinking_type,
        max_completion_tokens=args.max_completion_tokens,
        timeout_seconds=args.timeout_seconds,
        output_root=Path(args.output_root).resolve(),
    )
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "result_file": str(run_dir / "controlled_generation_results.json"),
                "path_type": "stage2b_mimo_controlled_generation_diagnostic_path",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
