from __future__ import annotations

import concurrent.futures
import json
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import litellm

from src.deepseek_utils import build_litellm_model_name, redact_secret


class MiMoStreamingGEPABridgeError(RuntimeError):
    """MiMo streaming GEPA bridge 的配置或执行失败。"""


class FirstTokenTimeout(RuntimeError):
    """首 token 等待超时。"""


class EmergencyStreamAbort(RuntimeError):
    """首 token 后的紧急保护截断。"""


def _attach_bridge_artifacts(exc: Exception, *, record: dict[str, Any], raw_payload: dict[str, Any]) -> Exception:
    setattr(exc, "bridge_record", record)
    setattr(exc, "bridge_raw_payload", raw_payload)
    return exc


@dataclass(slots=True)
class MiMoStreamingBridgeConfig:
    model: str
    api_base: str
    api_key: str
    provider: str = "mimo"
    thinking_type: str = "enabled"
    first_token_timeout_seconds: float = 1800.0
    sdk_timeout_seconds: float = 1800.0
    emergency_after_first_token_seconds: float | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "api_base": self.api_base,
            "thinking_type": self.thinking_type,
            "first_token_timeout_seconds": self.first_token_timeout_seconds,
            "sdk_timeout_seconds": self.sdk_timeout_seconds,
            "emergency_after_first_token_seconds": self.emergency_after_first_token_seconds,
        }


def _sanitize_text(value: Any, secret: str) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_text(inner, secret) for key, inner in value.items()}
    if isinstance(value, list):
        return [_sanitize_text(inner, secret) for inner in value]
    if isinstance(value, str):
        return redact_secret(value, secret)
    return value


def _to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump()
        except Exception:
            pass
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            pass
    if isinstance(value, dict):
        return {key: _to_jsonable(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(inner) for inner in value]
    if isinstance(value, tuple):
        return [_to_jsonable(inner) for inner in value]
    return value


def _extract_reasoning_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    parts: list[str] = []
    if isinstance(value, dict):
        reasoning_content = value.get("reasoning_content")
        if isinstance(reasoning_content, str):
            parts.append(reasoning_content)
        elif isinstance(reasoning_content, list):
            parts.extend(str(item) for item in reasoning_content if isinstance(item, str))
        content = value.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "").lower()
                if item_type.startswith("reason"):
                    text_value = item.get("text")
                    if isinstance(text_value, str):
                        parts.append(text_value)
    return "".join(parts)


def _extract_chunk_fields(chunk_payload: dict[str, Any]) -> tuple[str, str, str | None]:
    choices = chunk_payload.get("choices")
    if not isinstance(choices, list):
        return "", "", None
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    finish_reason: str | None = None
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        finish_reason = finish_reason or choice.get("finish_reason")
        delta = choice.get("delta")
        if delta is None:
            delta = choice.get("message")
        if isinstance(delta, dict):
            content_value = delta.get("content")
            if isinstance(content_value, str):
                content_parts.append(content_value)
            elif isinstance(content_value, list):
                for item in content_value:
                    if isinstance(item, dict):
                        text_value = item.get("text")
                        if isinstance(text_value, str):
                            content_parts.append(text_value)
                    elif isinstance(item, str):
                        content_parts.append(item)
            reasoning_parts.append(_extract_reasoning_text(delta))
    return "".join(content_parts), "".join(reasoning_parts), finish_reason


def _extract_http_status(stream: Any) -> int | None:
    response = getattr(stream, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def _attempt_close_stream(stream: Any) -> tuple[bool, bool]:
    close_fn = getattr(stream, "close", None)
    if not callable(close_fn):
        return False, False
    try:
        close_fn()
        return True, True
    except Exception:
        return True, False


_STREAM_EXHAUSTED = object()


def _next_stream_item(iterator: Any) -> Any:
    try:
        return next(iterator)
    except StopIteration:
        return _STREAM_EXHAUSTED


def _build_bridge_response(*, content: str, finish_reason: str | None, model: str) -> Any:
    return SimpleNamespace(
        id=None,
        model=model,
        usage=None,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ],
    )


def build_streaming_completion_kwargs(
    *,
    bridge_config: MiMoStreamingBridgeConfig,
    messages: list[dict[str, Any]],
    inherited_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kwargs = dict(inherited_kwargs or {})
    kwargs.pop("stream", None)
    kwargs.pop("messages", None)
    kwargs.pop("model", None)
    kwargs.pop("max_workers", None)
    kwargs.pop("request_timeout", None)
    kwargs["model"] = build_litellm_model_name(bridge_config.model)
    kwargs["messages"] = messages
    kwargs["stream"] = True
    kwargs["timeout"] = bridge_config.sdk_timeout_seconds
    kwargs["api_base"] = bridge_config.api_base
    kwargs["base_url"] = bridge_config.api_base
    kwargs["api_key"] = bridge_config.api_key
    kwargs["extra_body"] = {"thinking": {"type": bridge_config.thinking_type}}
    return kwargs


def run_streaming_completion(
    *,
    original_completion: Any,
    bridge_config: MiMoStreamingBridgeConfig,
    messages: list[dict[str, Any]],
    inherited_kwargs: dict[str, Any] | None = None,
    call_role: str,
    batch_index: int | None = None,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    started_at = time.time()
    record: dict[str, Any] = {
        "call_role": call_role,
        "batch_index": batch_index,
        "provider": bridge_config.provider,
        "model": bridge_config.model,
        "first_token_timeout_seconds": bridge_config.first_token_timeout_seconds,
        "sdk_timeout_seconds": bridge_config.sdk_timeout_seconds,
        "emergency_after_first_token_seconds": bridge_config.emergency_after_first_token_seconds,
        "started_at_unix": started_at,
        "first_token_observed": False,
        "time_to_first_token_seconds": None,
        "time_after_first_token_seconds": None,
        "time_to_complete_seconds": None,
        "finish_reason": None,
        "content_nonempty": False,
        "partial_content_nonempty": False,
        "error_type": None,
        "error_message_sanitized": None,
        "http_status": None,
        "timeout": False,
        "first_token_timeout_triggered": False,
        "sdk_timeout_triggered": False,
        "emergency_abort_triggered": False,
        "stream_close_attempted": False,
        "stream_close_succeeded": False,
        "raw_preview": "",
        "raw_response_length_chars": 0,
        "stream_completed": False,
    }
    raw_payload: dict[str, Any] = {
        "messages": _sanitize_text(messages, bridge_config.api_key),
        "request_kwargs": _sanitize_text(
            build_streaming_completion_kwargs(
                bridge_config=bridge_config,
                messages=messages,
                inherited_kwargs=inherited_kwargs,
            ),
            bridge_config.api_key,
        ),
        "content": "",
        "reasoning_text": "",
        "finish_reason": None,
        "http_status": None,
        "chunks": [],
    }

    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    finish_reason: str | None = None
    stream: Any = None
    close_attempted = False
    close_succeeded = False

    try:
        stream = original_completion(
            **build_streaming_completion_kwargs(
                bridge_config=bridge_config,
                messages=messages,
                inherited_kwargs=inherited_kwargs,
            )
        )
        record["http_status"] = _extract_http_status(stream)
        raw_payload["http_status"] = record["http_status"]
        iterator = iter(stream)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_next_stream_item, iterator)
            try:
                first_item = future.result(timeout=bridge_config.first_token_timeout_seconds)
            except concurrent.futures.TimeoutError as exc:
                close_attempted, close_succeeded = _attempt_close_stream(stream)
                record["timeout"] = True
                record["first_token_timeout_triggered"] = True
                record["error_type"] = "FirstTokenTimeout"
                record["error_message_sanitized"] = (
                    f"first token timeout after {bridge_config.first_token_timeout_seconds}s"
                )
                timeout_exc = FirstTokenTimeout(record["error_message_sanitized"])
                raise _attach_bridge_artifacts(timeout_exc, record=record, raw_payload=raw_payload) from exc
        if first_item is _STREAM_EXHAUSTED:
            record["stream_completed"] = True
        else:
            first_payload = _to_jsonable(first_item)
            content_delta, reasoning_delta, finish_reason = _extract_chunk_fields(first_payload)
            content_parts.append(content_delta)
            reasoning_parts.append(reasoning_delta)
            raw_payload["chunks"].append(_sanitize_text(first_payload, bridge_config.api_key))
            record["first_token_observed"] = True
            record["time_to_first_token_seconds"] = round(time.monotonic() - started, 6)
            for chunk in iterator:
                chunk_payload = _to_jsonable(chunk)
                content_delta, reasoning_delta, chunk_finish_reason = _extract_chunk_fields(chunk_payload)
                content_parts.append(content_delta)
                reasoning_parts.append(reasoning_delta)
                finish_reason = finish_reason or chunk_finish_reason
                raw_payload["chunks"].append(_sanitize_text(chunk_payload, bridge_config.api_key))
                if (
                    bridge_config.emergency_after_first_token_seconds is not None
                    and time.monotonic() - started > bridge_config.emergency_after_first_token_seconds
                ):
                    close_attempted, close_succeeded = _attempt_close_stream(stream)
                    raise EmergencyStreamAbort(
                        f"stream exceeded emergency guard {bridge_config.emergency_after_first_token_seconds}s"
                    )
            record["stream_completed"] = True
    except FirstTokenTimeout as exc:
        raise _attach_bridge_artifacts(exc, record=record, raw_payload=raw_payload)
    except EmergencyStreamAbort as exc:
        record["timeout"] = True
        record["emergency_abort_triggered"] = True
        record["error_type"] = "EmergencyStreamAbort"
        record["error_message_sanitized"] = redact_secret(str(exc), bridge_config.api_key)
        raise _attach_bridge_artifacts(exc, record=record, raw_payload=raw_payload)
    except KeyboardInterrupt as exc:  # pragma: no cover - 真实执行路径
        close_attempted, close_succeeded = _attempt_close_stream(stream)
        record["error_type"] = "ManualAbort"
        record["error_message_sanitized"] = "manual interruption"
        raise _attach_bridge_artifacts(exc, record=record, raw_payload=raw_payload)
    except Exception as exc:
        close_attempted, close_succeeded = _attempt_close_stream(stream)
        message = redact_secret(str(exc), bridge_config.api_key)
        record["error_type"] = type(exc).__name__
        record["error_message_sanitized"] = message
        record["sdk_timeout_triggered"] = "timeout" in type(exc).__name__.lower() or "timeout" in message.lower()
        record["timeout"] = bool(record["sdk_timeout_triggered"])
        raise _attach_bridge_artifacts(exc, record=record, raw_payload=raw_payload)
    finally:
        content = "".join(content_parts)
        reasoning_text = "".join(reasoning_parts)
        finish_reason = finish_reason or record.get("finish_reason")
        record["finish_reason"] = finish_reason
        record["stream_close_attempted"] = close_attempted
        record["stream_close_succeeded"] = close_succeeded
        record["content_nonempty"] = bool(content.strip())
        record["partial_content_nonempty"] = bool(content.strip()) and not bool(record["stream_completed"])
        record["raw_preview"] = redact_secret(content[:240], bridge_config.api_key)
        record["raw_response_length_chars"] = len(content)
        record["time_to_complete_seconds"] = round(time.monotonic() - started, 6)
        if record["first_token_observed"]:
            ttft = float(record["time_to_first_token_seconds"] or 0.0)
            record["time_after_first_token_seconds"] = round(
                float(record["time_to_complete_seconds"]) - ttft,
                6,
            )
        raw_payload["content"] = redact_secret(content, bridge_config.api_key)
        raw_payload["reasoning_text"] = redact_secret(reasoning_text, bridge_config.api_key)
        raw_payload["finish_reason"] = finish_reason

    response = _build_bridge_response(
        content=raw_payload["content"],
        finish_reason=finish_reason,
        model=bridge_config.model,
    )
    return response, record, raw_payload


def execute_health_check(
    *,
    bridge_config: MiMoStreamingBridgeConfig,
    original_completion: Any,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    messages = [{"role": "user", "content": "Return exactly: OK"}]
    try:
        response, record, raw_payload = run_streaming_completion(
            original_completion=original_completion,
            bridge_config=bridge_config,
            messages=messages,
            inherited_kwargs={},
            call_role="health_check",
            batch_index=None,
        )
    except Exception as exc:
        return (
            {
                "provider": bridge_config.provider,
                "model": bridge_config.model,
                "content_exact_ok": False,
                "content_preview": "",
                "latency_seconds": None,
                "error_type": type(exc).__name__,
                "error_message_sanitized": redact_secret(str(exc), bridge_config.api_key),
                "http_status": None,
            },
            None,
        )

    content = str(response.choices[0].message.content or "").strip()
    return (
        {
            "provider": bridge_config.provider,
            "model": bridge_config.model,
            "content_exact_ok": content == "OK",
            "content_preview": content[:80],
            "latency_seconds": record["time_to_complete_seconds"],
            "error_type": None,
            "error_message_sanitized": None,
            "http_status": record["http_status"],
        },
        raw_payload,
    )


@contextmanager
def patch_litellm_for_mimo_streaming(
    *,
    bridge_config: MiMoStreamingBridgeConfig,
    call_records: list[dict[str, Any]],
    raw_payloads: list[dict[str, Any]] | None = None,
) -> Iterator[None]:
    original_completion = litellm.completion
    original_batch_completion = litellm.batch_completion

    def _wrapped_completion(*args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model")
        messages = kwargs.get("messages")
        if model is None and args:
            model = args[0]
        if messages is None:
            if len(args) >= 2:
                messages = args[1]
            else:
                raise MiMoStreamingGEPABridgeError("litellm.completion 缺少 messages")
        inherited = dict(kwargs)
        if model is not None:
            inherited["model"] = model
        response, record, raw_payload = run_streaming_completion(
            original_completion=original_completion,
            bridge_config=bridge_config,
            messages=list(messages),
            inherited_kwargs=inherited,
            call_role="reflection_completion",
            batch_index=None,
        )
        call_records.append(record)
        if raw_payloads is not None:
            raw_payloads.append(raw_payload)
        return response

    def _wrapped_batch_completion(*args: Any, **kwargs: Any) -> list[Any]:
        model = kwargs.get("model")
        messages_batch = kwargs.get("messages")
        if model is None and args:
            model = args[0]
        if messages_batch is None:
            if len(args) >= 2:
                messages_batch = args[1]
            else:
                raise MiMoStreamingGEPABridgeError("litellm.batch_completion 缺少 messages")
        inherited = dict(kwargs)
        inherited.pop("messages", None)
        inherited.pop("model", None)
        if model is not None:
            inherited["model"] = model

        responses: list[Any] = []
        for index, messages in enumerate(messages_batch):
            response, record, raw_payload = run_streaming_completion(
                original_completion=original_completion,
                bridge_config=bridge_config,
                messages=list(messages),
                inherited_kwargs=inherited,
                call_role="task_batch_completion",
                batch_index=index,
            )
            call_records.append(record)
            if raw_payloads is not None:
                raw_payloads.append(raw_payload)
            responses.append(response)
        return responses

    litellm.completion = _wrapped_completion
    litellm.batch_completion = _wrapped_batch_completion
    try:
        yield
    finally:
        litellm.completion = original_completion
        litellm.batch_completion = original_batch_completion


def write_raw_payloads(output_dir: Path, payloads: list[dict[str, Any]]) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for index, payload in enumerate(payloads, start=1):
        path = output_dir / f"bridge_call_{index:03d}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(str(path))
    return written
