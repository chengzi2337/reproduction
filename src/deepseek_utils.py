from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from openai import APIStatusError, OpenAI


DEFAULT_DEEPSEEK_API_BASE = "https://api.deepseek.com"
PROBE_TEXT = "Return exactly: OK"


@dataclass(slots=True)
class ProbeResult:
    ok: bool
    model: str
    response_text: str
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
    return OpenAI(
        api_key=api_key,
        base_url=api_base or DEFAULT_DEEPSEEK_API_BASE,
    )


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
    os.environ["OPENAI_BASE_URL"] = api_base or DEFAULT_DEEPSEEK_API_BASE
    os.environ["OPENAI_API_BASE"] = api_base or DEFAULT_DEEPSEEK_API_BASE
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


def probe_model_with_openai_client(
    *,
    api_key: str,
    api_base: str,
    model_name: str,
) -> ProbeResult:
    client = build_openai_client(api_key=api_key, api_base=api_base)
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": PROBE_TEXT}],
            temperature=0,
        )
        content = _message_content(completion)
        if "OK" not in content:
            return ProbeResult(
                ok=False,
                model=model_name,
                response_text=content,
                error_type="UnexpectedResponse",
                error_message=f"响应未包含 OK：{content!r}",
            )
        return ProbeResult(ok=True, model=model_name, response_text=content)
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
