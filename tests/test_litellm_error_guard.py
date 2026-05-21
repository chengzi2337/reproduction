from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _make_fake_response(content: str = "hello") -> Any:
    """构造一个假的 ModelResponse，具备 resp.choices[0].message.content 结构。"""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, role="assistant"),
                index=0,
                finish_reason="stop",
            )
        ]
    )


# ---------------------------------------------------------------------------
# 测试 _make_empty_response 结构
# ---------------------------------------------------------------------------


def test_make_empty_response_structure() -> None:
    """_make_empty_response 构造的对象具备 DefaultAdapter 所需的完整结构。"""
    from src.litellm_error_guard import _make_empty_response

    resp = _make_empty_response()
    assert resp.choices[0].message.content == ""
    assert resp.choices[0].message.content.strip() == ""
    assert resp.choices[0].message.role == "assistant"
    assert resp.choices[0].index == 0
    assert resp.choices[0].finish_reason == "stop"


# ---------------------------------------------------------------------------
# 测试 context manager 状态恢复
# ---------------------------------------------------------------------------


def test_guard_restores_original_evaluate_on_exit() -> None:
    """退出 context manager 后，DefaultAdapter.evaluate 恢复为原始方法。"""
    from gepa.adapters.default_adapter.default_adapter import DefaultAdapter
    from src.litellm_error_guard import patch_default_adapter_batch_completion_guard

    original_evaluate = DefaultAdapter.evaluate

    with patch_default_adapter_batch_completion_guard():
        assert DefaultAdapter.evaluate is not original_evaluate

    assert DefaultAdapter.evaluate is original_evaluate


# ---------------------------------------------------------------------------
# 测试 guard 在 DefaultAdapter.evaluate 中的行为
# 使用真实的 DefaultAdapter + ContainsAnswerEvaluator，
# 通过 monkeypatch litellm.batch_completion 控制输入。
# ---------------------------------------------------------------------------


def test_guard_passes_valid_responses_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """batch_completion 返回正常响应时，guard 不改变其内容。"""
    import litellm
    from gepa.adapters.default_adapter.default_adapter import DefaultAdapter
    from src.litellm_error_guard import patch_default_adapter_batch_completion_guard

    def _fake_bc(*args: Any, **kwargs: Any) -> list[Any]:
        return [_make_fake_response("the answer is 42")]

    monkeypatch.setattr(litellm, "batch_completion", _fake_bc)

    adapter = DefaultAdapter(model="fake-model")
    batch = [{"input": "what is 6*7?", "answer": "42", "additional_context": {}}]

    with patch_default_adapter_batch_completion_guard():
        result = adapter.evaluate(batch, {"system_prompt": "test"})

    # "42" in "the answer is 42" → ContainsAnswerEvaluator → score=1.0
    assert result.outputs[0]["full_assistant_response"] == "the answer is 42"
    assert result.scores[0] == 1.0


def test_guard_replaces_exception_with_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """batch_completion 返回异常对象时，guard 将其替换为空响应 → 评分 0.0。"""
    import litellm
    from gepa.adapters.default_adapter.default_adapter import DefaultAdapter
    from src.litellm_error_guard import patch_default_adapter_batch_completion_guard

    def _fake_bc(*args: Any, **kwargs: Any) -> list[Any]:
        return [RuntimeError("simulated API failure")]

    monkeypatch.setattr(litellm, "batch_completion", _fake_bc)

    adapter = DefaultAdapter(model="fake-model")
    batch = [{"input": "q1", "answer": "42", "additional_context": {}}]

    with patch_default_adapter_batch_completion_guard():
        result = adapter.evaluate(batch, {"system_prompt": "test"})

    # 异常 → 空响应 → "" 不包含 "42" → score=0.0
    assert result.outputs[0]["full_assistant_response"] == ""
    assert result.scores[0] == 0.0


def test_guard_handles_mixed_valid_and_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """batch_completion 返回混合列表（正常+异常）时，guard 正确处理每个元素。"""
    import litellm
    from gepa.adapters.default_adapter.default_adapter import DefaultAdapter
    from src.litellm_error_guard import patch_default_adapter_batch_completion_guard

    def _fake_bc(*args: Any, **kwargs: Any) -> list[Any]:
        return [
            _make_fake_response("the answer is 42"),
            ConnectionError("timeout"),
            _make_fake_response("the answer is 99"),
        ]

    monkeypatch.setattr(litellm, "batch_completion", _fake_bc)

    adapter = DefaultAdapter(model="fake-model")
    batch = [
        {"input": "q1", "answer": "42", "additional_context": {}},
        {"input": "q2", "answer": "77", "additional_context": {}},
        {"input": "q3", "answer": "99", "additional_context": {}},
    ]

    with patch_default_adapter_batch_completion_guard():
        result = adapter.evaluate(batch, {"system_prompt": "test"})

    assert len(result.outputs) == 3
    assert result.outputs[0]["full_assistant_response"] == "the answer is 42"
    assert result.scores[0] == 1.0  # "42" in response
    assert result.outputs[1]["full_assistant_response"] == ""  # 异常 → 空
    assert result.scores[1] == 0.0  # "" 不包含 "77"
    assert result.outputs[2]["full_assistant_response"] == "the answer is 99"
    assert result.scores[2] == 1.0  # "99" in response


def test_guard_handles_all_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """batch_completion 全部返回异常时，guard 全部替换为空响应。"""
    import litellm
    from gepa.adapters.default_adapter.default_adapter import DefaultAdapter
    from src.litellm_error_guard import patch_default_adapter_batch_completion_guard

    def _fake_bc(*args: Any, **kwargs: Any) -> list[Any]:
        return [
            RuntimeError("error 1"),
            ConnectionError("error 2"),
            TimeoutError("error 3"),
        ]

    monkeypatch.setattr(litellm, "batch_completion", _fake_bc)

    adapter = DefaultAdapter(model="fake-model")
    batch = [
        {"input": "q1", "answer": "a1", "additional_context": {}},
        {"input": "q2", "answer": "a2", "additional_context": {}},
        {"input": "q3", "answer": "a3", "additional_context": {}},
    ]

    with patch_default_adapter_batch_completion_guard():
        result = adapter.evaluate(batch, {"system_prompt": "test"})

    assert len(result.outputs) == 3
    for output in result.outputs:
        assert output["full_assistant_response"] == ""
    for score in result.scores:
        assert score == 0.0


def test_guard_logs_warning_on_exception(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """batch_completion 返回异常对象时，guard 记录警告日志。"""
    import litellm
    from gepa.adapters.default_adapter.default_adapter import DefaultAdapter
    from src.litellm_error_guard import patch_default_adapter_batch_completion_guard

    def _fake_bc(*args: Any, **kwargs: Any) -> list[Any]:
        return [RuntimeError("simulated failure")]

    monkeypatch.setattr(litellm, "batch_completion", _fake_bc)

    adapter = DefaultAdapter(model="fake-model")
    batch = [{"input": "q1", "answer": "a1", "additional_context": {}}]

    with caplog.at_level("WARNING", logger="src.litellm_error_guard"):
        with patch_default_adapter_batch_completion_guard():
            adapter.evaluate(batch, {"system_prompt": "test"})

    assert any("batch_completion 返回异常对象" in record.message for record in caplog.records)
    assert any("RuntimeError" in record.message for record in caplog.records)


def test_guard_noop_when_all_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    """batch_completion 全部返回正常响应时，guard 不产生额外开销。"""
    import litellm
    from gepa.adapters.default_adapter.default_adapter import DefaultAdapter
    from src.litellm_error_guard import patch_default_adapter_batch_completion_guard

    bc_call_count = 0

    def _fake_bc(*args: Any, **kwargs: Any) -> list[Any]:
        nonlocal bc_call_count
        bc_call_count += 1
        return [_make_fake_response("answer is 10"), _make_fake_response("answer is 20")]

    monkeypatch.setattr(litellm, "batch_completion", _fake_bc)

    adapter = DefaultAdapter(model="fake-model")
    batch = [
        {"input": "q1", "answer": "10", "additional_context": {}},
        {"input": "q2", "answer": "20", "additional_context": {}},
    ]

    with patch_default_adapter_batch_completion_guard():
        result = adapter.evaluate(batch, {"system_prompt": "test"})

    assert bc_call_count == 1
    assert len(result.outputs) == 2
    assert result.outputs[0]["full_assistant_response"] == "answer is 10"
    assert result.outputs[1]["full_assistant_response"] == "answer is 20"
    assert result.scores == [1.0, 1.0]


def test_guard_does_not_affect_non_string_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """当 model 不是字符串（callable）时，guard 不影响 evaluate 路径。"""
    from gepa.adapters.default_adapter.default_adapter import DefaultAdapter
    from src.litellm_error_guard import patch_default_adapter_batch_completion_guard

    call_count = 0

    def _fake_model(messages: list[Any]) -> str:
        nonlocal call_count
        call_count += 1
        return "callable response"

    adapter = DefaultAdapter(model=_fake_model)
    batch = [{"input": "q1", "answer": "42", "additional_context": {}}]

    with patch_default_adapter_batch_completion_guard():
        result = adapter.evaluate(batch, {"system_prompt": "test"})

    assert call_count == 1
    assert result.outputs[0]["full_assistant_response"] == "callable response"
