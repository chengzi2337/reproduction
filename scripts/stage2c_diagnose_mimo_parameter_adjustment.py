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

from src.config import DEFAULT_BACKEND_FAMILY
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
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_TOKEN_CAPS = (1024, 2048)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "stage2c_mimo_parameter_adjustment_diagnostic"
PATH_TYPE = "stage2c_mimo_parameter_adjustment_diagnostic"


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


def _contains_final_answer_format(text: str | None) -> bool:
    if not text:
        return False
    return "### <answer>" in text


def _contains_any_hash_heading(text: str | None) -> bool:
    if not text:
        return False
    return "###" in text


def _looks_truncated(text: str | None) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if not stripped:
        return False
    if _contains_final_answer_format(stripped):
        return False
    return stripped[-1] not in set(".!?0123456789}])\"'")


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
        "contains_hash_heading": _contains_any_hash_heading(content),
        "contains_final_answer_format": _contains_final_answer_format(content),
        "looks_truncated": _looks_truncated(content),
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
        "contains_hash_heading": False,
        "contains_final_answer_format": False,
        "looks_truncated": False,
        "reasoning_content_nonempty": False,
        "finish_reason": None,
        "usage": _usage_payload(None),
        "error_type": type(exc).__name__,
        "error_message": redact_secret(str(exc), api_key),
    }


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
        _, valset, _ = init_dataset()
    if not valset:
        raise RuntimeError("官方 `init_dataset()` 返回的 valset 为空，无法执行 Stage 2C 参数诊断。")
    sample = dict(valset[0])
    if not str(sample.get("input") or "").strip():
        raise RuntimeError("官方 `init_dataset()` 返回的第一个 val 样本缺少 input。")
    return sample, "gepa.examples.aime.init_dataset() with local cache-backed load_dataset"


def build_messages(question: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": README_QUICKSTART_SEED_PROMPT["system_prompt"]},
        {"role": "user", "content": question},
    ]


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


def run_single_cap_diagnostic(
    *,
    api_key: str,
    api_base: str,
    model: str,
    messages: list[dict[str, str]],
    thinking_type: str,
    max_completion_tokens: int,
    timeout_seconds: float,
) -> dict[str, Any]:
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
    return {
        "max_completion_tokens": max_completion_tokens,
        "direct_sdk_result": direct_sdk_result,
        "litellm_result": litellm_result,
    }


def build_diagnostic_payload(
    *,
    api_base: str,
    model: str,
    dataset_source: str,
    sample_index: int,
    token_caps: list[int],
    cap_results: list[dict[str, Any]],
    thinking_type: str,
    timeout_seconds: float,
    proxy_env_detected: dict[str, bool],
) -> dict[str, Any]:
    return {
        "provider": "mimo",
        "backend_family": DEFAULT_BACKEND_FAMILY,
        "path_type": PATH_TYPE,
        "api_base": api_base,
        "model": model,
        "dataset_source": dataset_source,
        "sample_index": sample_index,
        "prompt_type": "readme_quickstart_seed_prompt",
        "parameter_adjustment_scope": {
            "thinking_type": thinking_type,
            "token_caps": token_caps,
            "timeout_seconds": timeout_seconds,
        },
        "proxy_env_detected": proxy_env_detected,
        "results_by_token_cap": cap_results,
        "interpretation": {
            "not_gepa_path": True,
            "not_strict_official_path": True,
            "not_performance_claim": True,
            "no_gepa_optimize_called": True,
            "pilot_not_started": True,
        },
    }


def run_parameter_adjustment_diagnostic(
    *,
    api_key: str,
    api_base: str,
    model: str,
    thinking_type: str,
    token_caps: list[int],
    timeout_seconds: float,
    execute: bool,
    output_root: Path,
) -> Path:
    if not api_base.strip():
        raise ValueError("Stage 2C 参数诊断必须显式提供 MIMO_API_BASE 或 --api-base。")
    if not model.strip():
        raise ValueError("缺少模型名。")
    if not token_caps:
        raise ValueError("token_caps 不能为空。")
    if any(cap <= 0 for cap in token_caps):
        raise ValueError("token_caps 必须全部大于 0。")
    if execute and not api_key.strip():
        raise ValueError("Stage 2C 参数诊断 execute 模式缺少 MIMO_API_KEY。")

    run_dir = create_run_dir(output_root)
    sample, dataset_source = load_first_val_sample_via_init_dataset()
    messages = build_messages(str(sample["input"]))
    proxy_flags = _proxy_env_detected()

    snapshot = {
        "path_type": PATH_TYPE,
        "provider": "mimo",
        "backend_family": DEFAULT_BACKEND_FAMILY,
        "api_base": api_base,
        "model": model,
        "dataset_source": dataset_source,
        "sample_index": 0,
        "prompt_type": "readme_quickstart_seed_prompt",
        "thinking_type": thinking_type,
        "token_caps": token_caps,
        "timeout_seconds": timeout_seconds,
        "execute_diagnostic": execute,
        "not_gepa_path": True,
        "not_strict_official_path": True,
        "not_performance_claim": True,
        "pilot_not_started": True,
    }
    write_json(run_dir / "stage2c_parameter_adjustment_input_snapshot.json", snapshot)

    if not execute:
        write_text(
            run_dir / "notes.md",
            "\n".join(
                [
                    "# Stage 2C MiMo parameter-adjustment diagnostic",
                    "",
                    "- 本脚本不调用 `gepa.optimize()`。",
                    "- 默认只做 dry-run；只有显式 `--execute` 才会做 direct SDK 与 LiteLLM 小样本诊断。",
                    "- 当前仅比较 `thinking.disabled` 下的 `max_completion_tokens` 调整。",
                    "- 本路径不是 strict official path，不构成性能结论。",
                    "",
                ]
            ),
        )
        return run_dir

    cap_results = [
        run_single_cap_diagnostic(
            api_key=api_key,
            api_base=api_base,
            model=model,
            messages=messages,
            thinking_type=thinking_type,
            max_completion_tokens=cap,
            timeout_seconds=timeout_seconds,
        )
        for cap in token_caps
    ]
    payload = build_diagnostic_payload(
        api_base=api_base,
        model=model,
        dataset_source=dataset_source,
        sample_index=0,
        token_caps=token_caps,
        cap_results=cap_results,
        thinking_type=thinking_type,
        timeout_seconds=timeout_seconds,
        proxy_env_detected=proxy_flags,
    )
    write_json(run_dir / "stage2c_parameter_adjustment_results.json", payload)
    write_text(
        run_dir / "notes.md",
        "\n".join(
            [
                "# Stage 2C MiMo parameter-adjustment diagnostic",
                "",
                "- 本脚本不调用 `gepa.optimize()`。",
                "- 本脚本只做 Stage 2C 参数调整的小样本诊断。",
                "- 当前保持 `thinking.disabled` 不变，仅比较更高的 `max_completion_tokens`。",
                "- 本路径不是 strict official path，不构成性能结论。",
                "",
            ]
        ),
    )
    return run_dir


def parse_token_caps(raw_value: str) -> list[int]:
    parts = [item.strip() for item in raw_value.split(",")]
    return [int(item) for item in parts if item]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="运行 Stage 2C MiMo 参数调整诊断。默认仅生成 dry-run snapshot，不自动发起 direct SDK / LiteLLM 请求。"
    )
    parser.add_argument("--api-base", default=_env("MIMO_API_BASE"), help="显式 MIMO API Base。")
    parser.add_argument("--model", default=_env("TASK_MODEL", DEFAULT_MODEL), help="模型名。")
    parser.add_argument("--thinking-type", default=DEFAULT_THINKING_TYPE, help="当前固定为 disabled。")
    parser.add_argument(
        "--token-caps",
        default="1024,2048",
        help="逗号分隔的 max_completion_tokens 候选值，默认 1024,2048。",
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
        help="输出目录，默认 outputs/stage2c_mimo_parameter_adjustment_diagnostic。",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="显式执行 direct SDK / LiteLLM 小样本诊断；默认只做 dry-run。",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = _env("MIMO_API_KEY")
    run_dir = run_parameter_adjustment_diagnostic(
        api_key=api_key,
        api_base=args.api_base,
        model=args.model,
        thinking_type=args.thinking_type,
        token_caps=parse_token_caps(args.token_caps),
        timeout_seconds=args.timeout_seconds,
        execute=args.execute,
        output_root=Path(args.output_root).resolve(),
    )
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "path_type": PATH_TYPE,
                "execute_diagnostic": args.execute,
                "provider": "mimo",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
