from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from openai import APIStatusError, OpenAI


PROBE_TEXT = "Return exactly: OK"


@dataclass(slots=True)
class ProbeResult:
    ok: bool
    model: str
    response_text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    error_body: str | None = None
    status_code: int | None = None


def redact_secret(text: str | None, secret: str) -> str:
    if not text:
        return ""
    if not secret:
        return text
    return text.replace(secret, "***REDACTED***")


def build_openai_client(*, api_key: str, api_base: str) -> OpenAI:
    normalized_api_base = str(api_base or "").strip()
    client_kwargs: dict[str, str] = {"api_key": api_key}
    if normalized_api_base:
        client_kwargs["base_url"] = normalized_api_base
    return OpenAI(**client_kwargs)


def build_litellm_model_name(model_name: str) -> str:
    normalized = model_name.strip()
    if not normalized:
        raise ValueError("模型名不能为空。")
    if normalized.startswith("openai/"):
        return normalized
    return f"openai/{normalized}"


@contextmanager
def temporary_openai_compatible_env(*, api_key: str, api_base: str) -> Iterator[None]:
    keys = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE")
    old_values = {key: os.environ.get(key) for key in keys}
    os.environ["OPENAI_API_KEY"] = api_key

    normalized_api_base = str(api_base or "").strip()
    if normalized_api_base:
        os.environ["OPENAI_BASE_URL"] = normalized_api_base
        os.environ["OPENAI_API_BASE"] = normalized_api_base
    else:
        os.environ.pop("OPENAI_BASE_URL", None)
        os.environ.pop("OPENAI_API_BASE", None)

    try:
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def _message_content(completion: object) -> str:
    choice = getattr(completion, "choices")[0]
    message = getattr(choice, "message")
    return str(getattr(message, "content") or "").strip()


def _extract_error_body(exc: Exception, api_key: str) -> tuple[int | None, str]:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    body = ""
    if response is not None:
        response_text = getattr(response, "text", None)
        if isinstance(response_text, str):
            body = response_text
        elif callable(getattr(response, "json", None)):
            try:
                body = str(response.json())
            except Exception:
                body = ""
    if isinstance(exc, APIStatusError) and getattr(exc, "body", None) is not None and not body:
        body = str(exc.body)
    return status_code, redact_secret(body or str(exc), api_key)


def _usage_value(completion: object, field_name: str) -> int | None:
    usage = getattr(completion, "usage", None)
    if usage is None:
        return None
    value = getattr(usage, field_name, None)
    return int(value) if isinstance(value, int) else None


def _reasoning_tokens(completion: object) -> int | None:
    usage = getattr(completion, "usage", None)
    if usage is None:
        return None
    details = getattr(usage, "completion_tokens_details", None)
    if details is None:
        return None
    value = getattr(details, "reasoning_tokens", None)
    return int(value) if isinstance(value, int) else None


def probe_model_with_openai_client(
    *,
    api_key: str,
    api_base: str,
    model_name: str,
    probe_text: str = PROBE_TEXT,
    max_completion_tokens: int = 16,
) -> ProbeResult:
    client = build_openai_client(api_key=api_key, api_base=api_base)
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": probe_text}],
            max_completion_tokens=max_completion_tokens,
        )
        content = _message_content(completion)
        if "OK" not in content:
            return ProbeResult(
                ok=False,
                model=model_name,
                response_text=content,
                prompt_tokens=_usage_value(completion, "prompt_tokens"),
                completion_tokens=_usage_value(completion, "completion_tokens"),
                total_tokens=_usage_value(completion, "total_tokens"),
                reasoning_tokens=_reasoning_tokens(completion),
                error_type="UnexpectedResponse",
                error_message=f"响应未包含 OK：{content!r}",
            )
        return ProbeResult(
            ok=True,
            model=model_name,
            response_text=content,
            prompt_tokens=_usage_value(completion, "prompt_tokens"),
            completion_tokens=_usage_value(completion, "completion_tokens"),
            total_tokens=_usage_value(completion, "total_tokens"),
            reasoning_tokens=_reasoning_tokens(completion),
        )
    except Exception as exc:
        status_code, error_body = _extract_error_body(exc, api_key)
        return ProbeResult(
            ok=False,
            model=model_name,
            response_text="",
            error_type=type(exc).__name__,
            error_message=redact_secret(str(exc), api_key),
            error_body=error_body,
            status_code=status_code,
        )
