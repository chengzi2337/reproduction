# DeepSeek Strict Continuation Pilot Call-Chain Audit

## 审计定位

本报告是一次只读调用链审计，目标是回答：

> 为什么 `DeepSeek strict-readme continuation pilot` 在第一次 reflective proposal 阶段报出  
> `'InternalServerError' object has no attribute 'choices'`？

本审计：

- 不调用模型
- 不调用 `gepa.optimize()`
- 不修改 GEPA optimizer
- 不修改 evaluator
- 不修改 provider 调用逻辑

## 被审计的运行

- 结果目录：`outputs/deepseek_strict_continuation_pilot/20260521T204134+0800`
- 输入快照：`deepseek_strict_continuation_pilot_input_snapshot.json`
- 结果摘要：`deepseek_strict_continuation_pilot_result_summary.json`

当前已确认：

- `path_type = deepseek_strict_continuation_pilot`
- `continuation_track = deepseek_strict_readme_continuation`
- `provider = deepseek`
- `task_lm = openai/deepseek-v4-flash`
- `reflection_lm = openai/deepseek-v4-pro`
- `max_metric_calls = 50`
- `execution_completed = false`
- `error_type = AttributeError`
- `error_message = 'InternalServerError' object has no attribute 'choices'`

## 表面现象

控制台关键输出为：

- `Iteration 0: Base program full valset score: 0.17777777777777778 over 45 / 45 examples`
- `Iteration 1: Selected program 0 score: 0.17777777777777778`
- `Iteration 1: Exception during optimization: 'InternalServerError' object has no attribute 'choices'`

这说明：

1. baseline full valset evaluation 已经完成
2. 运行已进入 `Iteration 1`
3. 运行已开始第一次候选展开，而不是停在 smoke 的 baseline-only 阶段

## 调用链证据

### 1. reflective proposal 会先做 trace capture evaluation

GEPA 本地安装源码 `gepa/proposer/reflective_mutation/reflective_mutation.py` 中：

```python
eval_curr = self.adapter.evaluate(minibatch, curr_prog, capture_traces=True)
```

这一步位于：

- 先选中当前 program
- 再对 minibatch 做 `capture_traces=True` 的 evaluation
- 再基于轨迹做 reflective dataset 和 proposal

因此，本次失败点位于：

- 第一次 reflective proposal 的 trace capture evaluation 路径

### 2. DefaultAdapter 对 batch_completion 返回值有强假设

GEPA 本地安装源码 `gepa/adapters/default_adapter/default_adapter.py` 中：

```python
responses = [
    resp.choices[0].message.content.strip()
    for resp in self.litellm.batch_completion(
        model=self.model,
        messages=litellm_requests,
        max_workers=self.max_litellm_workers,
        **self.litellm_batch_completion_kwargs,
    )
]
```

这说明 `DefaultAdapter.evaluate()` 默认假定：

- `litellm.batch_completion(...)` 返回一个列表
- 列表中的每个元素都具备：
  - `resp.choices[0].message.content`

它没有对“列表中混入异常对象”的情况做保护。

### 3. LiteLLM batch_completion 会把异常对象直接放回结果列表

LiteLLM 本地安装源码 `litellm/batch_completion/main.py` 中：

```python
for future in completions:
    try:
        results.append(future.result())
    except Exception as exc:
        results.append(exc)
```

这说明：

- 当并发子请求失败时
- LiteLLM 会把异常对象 `exc` 直接追加到 `results`
- 而不是统一抛出、过滤或包装成标准 `choices` 响应

### 4. InternalServerError 是异常对象，不是 completion 响应

LiteLLM 本地安装源码 `litellm/exceptions.py` 中：

```python
class InternalServerError(openai.InternalServerError):
```

该类具备：

- `status_code`
- `message`
- `llm_provider`
- `model`

但它不是 chat completion 响应对象，也不具备：

- `.choices`

## 审计结论

当前最稳的调用链解释是：

1. 本次 pilot 已经跨过 baseline-only 阶段
2. 在 `Iteration 1` 的第一次 reflective proposal 中
3. `ReflectiveMutationProposer` 调用了：
   - `adapter.evaluate(minibatch, curr_prog, capture_traces=True)`
4. `DefaultAdapter.evaluate()` 进一步调用：
   - `litellm.batch_completion(...)`
5. 其中至少一个并发子请求失败
6. LiteLLM 把失败结果作为 `InternalServerError` 异常对象直接放回 `results`
7. `DefaultAdapter` 继续把该异常对象当成正常 response 读取：
   - `resp.choices[0].message.content`
8. 最终触发：
   - `AttributeError: 'InternalServerError' object has no attribute 'choices'`

## 当前不应得出的结论

当前不能据此写成：

- DeepSeek provider 整体不可用
- GEPA optimizer 逻辑错误
- strict continuation 路径整体失败
- pilot 已通过

更准确的写法应是：

- `DeepSeek strict continuation pilot started but failed during reflective proposal`
- 当前 blocker 位于：
  - provider / LiteLLM 并发 completion 异常对象
  - GEPA `DefaultAdapter` 对返回值的未防护访问

## 当前建议

在进入下一轮实验前，最合理的动作是：

1. 先封存本次 pilot result checkpoint
2. 先封存本次只读调用链审计
3. 在该审计基础上，再决定是否进入一个新的 provider-error handling 诊断阶段

在此之前，不应：

- 直接重跑 pilot
- 直接扩大预算
- 直接进入 `official_budget`
