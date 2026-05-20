from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.mimo_controlled_generation import ControlledGenerationConfig, controlled_litellm_generation


def test_controlled_generation_injects_completion_kwargs(monkeypatch) -> None:
    import litellm

    captured: dict[str, object] = {}

    def _fake_completion(*args, **kwargs):
        captured["kwargs"] = kwargs
        return "ok"

    monkeypatch.setattr(litellm, "completion", _fake_completion)
    original_batch = litellm.batch_completion
    config = ControlledGenerationConfig(model="mimo-v2.5-pro", api_base="https://token-plan-cn.xiaomimimo.com/v1")

    with controlled_litellm_generation(config):
        result = litellm.completion(model="openai/mimo-v2.5-pro", messages=[{"role": "user", "content": "x"}])

    assert result == "ok"
    assert captured["kwargs"]["max_completion_tokens"] == 512
    assert captured["kwargs"]["timeout"] == 120.0
    assert captured["kwargs"]["extra_body"]["thinking"]["type"] == "disabled"
    assert litellm.batch_completion is original_batch


def test_controlled_generation_injects_batch_completion_kwargs(monkeypatch) -> None:
    import litellm

    captured: dict[str, object] = {}

    def _fake_batch_completion(*args, **kwargs):
        captured["kwargs"] = kwargs
        return []

    original_completion = litellm.completion
    monkeypatch.setattr(litellm, "batch_completion", _fake_batch_completion)
    config = ControlledGenerationConfig(model="mimo-v2.5-pro", api_base="https://token-plan-cn.xiaomimimo.com/v1")

    with controlled_litellm_generation(config):
        litellm.batch_completion(
            model="openai/mimo-v2.5-pro",
            messages=[[{"role": "user", "content": "x"}]],
            max_workers=1,
        )

    assert captured["kwargs"]["max_completion_tokens"] == 512
    assert captured["kwargs"]["timeout"] == 120.0
    assert captured["kwargs"]["extra_body"]["thinking"]["type"] == "disabled"
    assert litellm.completion is original_completion


def test_controlled_generation_respects_existing_explicit_kwargs(monkeypatch) -> None:
    import litellm

    captured: dict[str, object] = {}

    def _fake_completion(*args, **kwargs):
        captured["kwargs"] = kwargs
        return "ok"

    monkeypatch.setattr(litellm, "completion", _fake_completion)
    config = ControlledGenerationConfig(model="mimo-v2.5-pro", api_base="https://token-plan-cn.xiaomimimo.com/v1")

    with controlled_litellm_generation(config):
        litellm.completion(
            model="openai/mimo-v2.5-pro",
            messages=[{"role": "user", "content": "x"}],
            max_completion_tokens=1024,
            timeout=30,
            extra_body={"thinking": {"type": "enabled"}, "foo": "bar"},
        )

    assert captured["kwargs"]["max_completion_tokens"] == 1024
    assert captured["kwargs"]["timeout"] == 30
    assert captured["kwargs"]["extra_body"]["thinking"]["type"] == "enabled"
    assert captured["kwargs"]["extra_body"]["foo"] == "bar"


def test_controlled_generation_restores_original_functions(monkeypatch) -> None:
    import litellm

    def _fake_completion(*args, **kwargs):
        return "completion"

    def _fake_batch_completion(*args, **kwargs):
        return "batch"

    monkeypatch.setattr(litellm, "completion", _fake_completion)
    monkeypatch.setattr(litellm, "batch_completion", _fake_batch_completion)
    config = ControlledGenerationConfig(model="mimo-v2.5-pro", api_base="https://token-plan-cn.xiaomimimo.com/v1")

    original_completion = litellm.completion
    original_batch_completion = litellm.batch_completion
    with controlled_litellm_generation(config):
        assert litellm.completion is not original_completion
        assert litellm.batch_completion is not original_batch_completion
    assert litellm.completion is original_completion
    assert litellm.batch_completion is original_batch_completion
