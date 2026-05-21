"""运行时补丁：为 DefaultAdapter.evaluate() 的 batch_completion 结果添加异常对象防护。

问题：litellm.batch_completion() 在并发子请求失败时，会将 Exception 对象直接放入
结果列表。DefaultAdapter 的列表推导 resp.choices[0].message.content 不检查类型，
导致 AttributeError。

修复：临时包装 batch_completion，将 Exception 对象替换为空 ModelResponse，
使后续评分逻辑自然给出 0.0 分（符合 GEPAAdapter Protocol 的 per-example 失败要求）。

约束：
- 不修改已安装的 gepa 包源码（.venv 下的文件）
- 不改变 optimize/propose/evaluate 的算法语义
- 符合 GEPAAdapter Protocol（per-example 失败 → 0.0 分，不抛异常）
- 作用域限定：仅在 with 块内生效，退出后恢复原始行为
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)


def _make_empty_response() -> Any:
    """构造一个空的 ModelResponse 对象，choices[0].message.content = ''。

    DefaultAdapter 的后续路径：
        resp.choices[0].message.content.strip() → ''
        evaluator(data, '') → ContainsAnswerEvaluator → score=0.0
    """
    from litellm import ModelResponse
    from litellm.types.utils import Choices, Message

    response = ModelResponse()
    response.choices = [
        Choices(
            message=Message(content="", role="assistant"),
            index=0,
            finish_reason="stop",
        )
    ]
    return response


@contextmanager
def patch_default_adapter_batch_completion_guard() -> Iterator[None]:
    """在 gepa.optimize() 运行期间，为 DefaultAdapter.evaluate() 的
    litellm.batch_completion 结果遍历添加异常对象防护。

    使用方式：
        with patch_default_adapter_batch_completion_guard():
            result = gepa.optimize(...)

    补丁逻辑：
    1. 拦截 litellm.batch_completion() 的返回值
    2. 遍历结果列表，将 Exception 对象替换为空 ModelResponse
    3. 记录警告日志（包含异常类型和消息）
    4. 正常响应对象原样传递

    退出 context manager 后，litellm.batch_completion 恢复为原始函数。
    """
    import litellm
    from gepa.adapters.default_adapter.default_adapter import DefaultAdapter

    original_bc = litellm.batch_completion
    original_evaluate = DefaultAdapter.evaluate

    def _guarded_bc(*args: Any, **kwargs: Any) -> list[Any]:
        results = original_bc(*args, **kwargs)
        guarded: list[Any] = []
        for item in results:
            if isinstance(item, Exception):
                logger.warning(
                    "batch_completion 返回异常对象，替换为空响应: %s: %s",
                    type(item).__name__,
                    item,
                )
                guarded.append(_make_empty_response())
            else:
                guarded.append(item)
        return guarded

    def _patched_evaluate(
        self: Any,
        batch: Any,
        candidate: Any,
        capture_traces: bool = False,
    ) -> Any:
        litellm.batch_completion = _guarded_bc
        try:
            return original_evaluate(self, batch, candidate, capture_traces)
        finally:
            litellm.batch_completion = original_bc

    DefaultAdapter.evaluate = _patched_evaluate  # type: ignore[method-assign]
    try:
        yield
    finally:
        DefaultAdapter.evaluate = original_evaluate  # type: ignore[method-assign]
        litellm.batch_completion = original_bc
