from __future__ import annotations

from typing import Iterator

from src.openai_compatible_utils import (
    PROBE_TEXT,
    ProbeResult,
    build_litellm_model_name,
    build_openai_client as _build_openai_client,
    probe_model_with_openai_client as _probe_model_with_openai_client,
    redact_secret,
    temporary_openai_compatible_env as _temporary_openai_compatible_env,
)


DEFAULT_DEEPSEEK_API_BASE = "https://api.deepseek.com"


def build_openai_client(*, api_key: str, api_base: str):
    return _build_openai_client(
        api_key=api_key,
        api_base=api_base or DEFAULT_DEEPSEEK_API_BASE,
    )


def temporary_openai_compatible_env(*, api_key: str, api_base: str) -> Iterator[None]:
    return _temporary_openai_compatible_env(
        api_key=api_key,
        api_base=api_base or DEFAULT_DEEPSEEK_API_BASE,
    )


def probe_model_with_openai_client(
    *,
    api_key: str,
    api_base: str,
    model_name: str,
    probe_text: str = PROBE_TEXT,
    max_completion_tokens: int = 16,
) -> ProbeResult:
    return _probe_model_with_openai_client(
        api_key=api_key,
        api_base=api_base or DEFAULT_DEEPSEEK_API_BASE,
        model_name=model_name,
        probe_text=probe_text,
        max_completion_tokens=max_completion_tokens,
    )
