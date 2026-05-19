from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DEFAULT_MIMO_API_BASE
from src.logging_utils import create_run_dir, write_json
from src.openai_compatible_utils import (
    PROBE_TEXT,
    build_litellm_model_name,
    probe_model_with_openai_client,
    redact_secret,
    temporary_openai_compatible_env,
)


DEFAULT_MODELS = [
    "mimo-v2-flash",
    "mimo-v2.5",
    "mimo-v2.5-pro",
]


def _get_attr_or_key(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _usage_payload(result: Any) -> dict[str, Any]:
    return {
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens,
        "completion_tokens_details": {
            "reasoning_tokens": result.reasoning_tokens,
        },
    }


def _raw_probe_result(*, api_key: str, api_base: str, model_name: str) -> dict[str, Any]:
    result = probe_model_with_openai_client(
        api_key=api_key,
        api_base=api_base,
        model_name=model_name,
        probe_text=PROBE_TEXT,
        max_completion_tokens=16,
    )
    payload = {
        "probe_kind": "openai_sdk",
        "model": result.model,
        "ok": result.ok,
        "response_text": result.response_text,
        "usage": _usage_payload(result),
        "error_type": result.error_type,
        "error_message": result.error_message,
        "status_code": result.status_code,
    }
    if result.error_body:
        payload["error_body"] = result.error_body
    return payload


def _litellm_probe_result(*, api_key: str, api_base: str, model_name: str) -> dict[str, Any]:
    try:
        from litellm import completion
    except Exception as exc:
        return {
            "probe_kind": "litellm_openai_path",
            "model": build_litellm_model_name(model_name),
            "ok": False,
            "response_text": "",
            "usage": {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "completion_tokens_details": {"reasoning_tokens": None},
            },
            "error_type": type(exc).__name__,
            "error_message": redact_secret(str(exc), api_key),
        }

    try:
        with temporary_openai_compatible_env(api_key=api_key, api_base=api_base):
            response = completion(
                model=build_litellm_model_name(model_name),
                messages=[{"role": "user", "content": PROBE_TEXT}],
                max_tokens=16,
            )
        choice = _get_attr_or_key(response, "choices")[0]
        message = _get_attr_or_key(choice, "message")
        content = str(_get_attr_or_key(message, "content") or "").strip()
        usage = _get_attr_or_key(response, "usage")
        reasoning_tokens = None
        if usage is not None:
            details = _get_attr_or_key(usage, "completion_tokens_details")
            if details is not None:
                reasoning_tokens = _get_attr_or_key(details, "reasoning_tokens")
        return {
            "probe_kind": "litellm_openai_path",
            "model": build_litellm_model_name(model_name),
            "ok": "OK" in content,
            "response_text": content,
            "usage": {
                "prompt_tokens": _get_attr_or_key(usage, "prompt_tokens") if usage is not None else None,
                "completion_tokens": _get_attr_or_key(usage, "completion_tokens")
                if usage is not None
                else None,
                "total_tokens": _get_attr_or_key(usage, "total_tokens") if usage is not None else None,
                "completion_tokens_details": {
                    "reasoning_tokens": reasoning_tokens,
                },
            },
            "error_type": None if "OK" in content else "UnexpectedResponse",
            "error_message": None if "OK" in content else f"响应未包含 OK：{content!r}",
        }
    except Exception as exc:
        return {
            "probe_kind": "litellm_openai_path",
            "model": build_litellm_model_name(model_name),
            "ok": False,
            "response_text": "",
            "usage": {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "completion_tokens_details": {"reasoning_tokens": None},
            },
            "error_type": type(exc).__name__,
            "error_message": redact_secret(str(exc), api_key),
        }


def main() -> None:
    load_dotenv()
    api_key = str(os.getenv("MIMO_API_KEY") or "").strip()
    api_base = str(os.getenv("MIMO_API_BASE") or "").strip() or DEFAULT_MIMO_API_BASE
    if not api_key:
        raise SystemExit("缺少 MIMO_API_KEY。请先导出临时或正式 MiMo key。")

    output_root = PROJECT_ROOT / "outputs" / "mimo_probe"
    run_dir = create_run_dir(output_root)

    raw_results = [
        _raw_probe_result(api_key=api_key, api_base=api_base, model_name=model_name)
        for model_name in DEFAULT_MODELS
    ]
    litellm_results = [
        _litellm_probe_result(api_key=api_key, api_base=api_base, model_name="mimo-v2-flash")
    ]

    payload = {
        "provider": "mimo",
        "backend_family": "openai_compatible",
        "api_base": api_base,
        "probe_text": PROBE_TEXT,
        "openai_sdk_probe_results": raw_results,
        "litellm_probe_results": litellm_results,
    }
    write_json(run_dir / "mimo_probe_results.json", payload)

    print(json.dumps({"run_dir": str(run_dir), "result_file": str(run_dir / "mimo_probe_results.json")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
