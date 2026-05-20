from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Iterator


@dataclass(slots=True)
class ControlledGenerationConfig:
    model: str
    api_base: str
    provider: str = "mimo"
    thinking_type: str = "disabled"
    max_completion_tokens: int = 512
    timeout_seconds: float = 120.0

    def sanitize(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "api_base": self.api_base,
            "thinking_type": self.thinking_type,
            "max_completion_tokens": self.max_completion_tokens,
            "timeout_seconds": self.timeout_seconds,
        }

    def to_public_dict(self) -> dict[str, Any]:
        return self.sanitize()


def _merge_thinking(extra_body: Any, thinking_type: str) -> dict[str, Any]:
    payload: dict[str, Any]
    if isinstance(extra_body, dict):
        payload = dict(extra_body)
    else:
        payload = {}

    thinking_payload = payload.get("thinking")
    if isinstance(thinking_payload, dict):
        merged_thinking = dict(thinking_payload)
    else:
        merged_thinking = {}
    merged_thinking.setdefault("type", thinking_type)
    payload["thinking"] = merged_thinking
    return payload


def _inject_generation_kwargs(kwargs: dict[str, Any], config: ControlledGenerationConfig) -> dict[str, Any]:
    merged = dict(kwargs)
    merged["extra_body"] = _merge_thinking(merged.get("extra_body"), config.thinking_type)
    merged.setdefault("max_completion_tokens", config.max_completion_tokens)
    merged.setdefault("timeout", config.timeout_seconds)
    return merged


@contextmanager
def controlled_litellm_generation(config: ControlledGenerationConfig) -> Iterator[None]:
    import litellm

    original_completion = litellm.completion
    original_batch_completion = litellm.batch_completion

    def _wrapped_completion(*args: Any, **kwargs: Any) -> Any:
        return original_completion(*args, **_inject_generation_kwargs(kwargs, config))

    def _wrapped_batch_completion(*args: Any, **kwargs: Any) -> Any:
        return original_batch_completion(*args, **_inject_generation_kwargs(kwargs, config))

    litellm.completion = _wrapped_completion
    litellm.batch_completion = _wrapped_batch_completion
    try:
        yield
    finally:
        litellm.completion = original_completion
        litellm.batch_completion = original_batch_completion
