# DeepSeek Strict Continuation Smoke Candidate Expansion Audit

## 审计目标

本报告只回答一个问题：

> 为什么这次 `DeepSeek strict continuation smoke` 的 `num_candidates` 没有展开，最终保持为 `1`？

本报告是只读审计：

- 不调用模型
- 不调用 `gepa.optimize()`
- 不修改 GEPA optimizer
- 不修改 evaluator
- 不做新的 smoke / pilot

## 被审计的运行

- 结果目录：`outputs/deepseek_strict_continuation_smoke/20260521T193315+0800`
- `path_type = deepseek_strict_continuation_smoke`
- `max_metric_calls = 10`
- `valset_size = 45`
- 结果摘要：
  - `best_score = 0.2222222222222222`
  - `total_metric_calls = 45`
  - `num_candidates = 1`
  - `num_full_val_evals = 1`

## 已观察到的表面现象

- 控制台只出现了 base program full valset score：
  - `Iteration 0: Base program full valset score: 0.2222222222222222 over 45 / 45 examples`
- 结果摘要中：
  - `num_candidates = 1`
  - `num_full_val_evals = 1`

这说明本次 smoke 更像是：

- 完成了一次 seed candidate 的 strict-path baseline evaluation
- 但没有留下候选真正展开的证据

## 代码证据

### 1. `max_metric_calls` 的真实语义是 stopper，而不是候选预算

GEPA 安装包 `gepa.utils.stop_condition.MaxMetricCallsStopper` 的实现是：

```python
def __call__(self, gepa_state: GEPAState) -> bool:
    return gepa_state.total_num_evals >= self.max_metric_calls
```

这意味着：

- `max_metric_calls` 比较的是 `total_num_evals`
- 它不是“最多产生多少个 candidate”
- 它也不是“最多跑多少轮 iteration”

### 2. 初始化阶段就会先做 seed candidate 的 full valset eval

GEPA 安装包 `gepa.core.state.initialize_gepa_state()` 的关键逻辑是：

```python
num_evals_run += len(eval_result.scores_by_val_id)
...
gepa_state.num_full_ds_evals = 1
gepa_state.total_num_evals = num_evals_run
```

这意味着：

- 初始化阶段会先对 seed candidate 跑完整个 valset
- 然后把这次 full valset eval 的样本数直接记入 `total_num_evals`

在当前 run 中：

- `valset_size = 45`

因此初始化一结束，就已经满足：

- `total_num_evals = 45`

### 3. 主循环是在 base program full valset score 之后才开始检查 stop

GEPA 安装包 `gepa.core.engine.GEPAEngine.run()` 中：

```python
self.logger.log(
    f"Iteration {state.i + 1}: Base program full valset score: {base_val_avg} "
    f"over {base_val_coverage} / {len(valset)} examples"
)
...
while not self._should_stop(state):
```

这意味着：

- 先打印 base program full valset score
- 再进入主循环判断是否继续

如果在此时：

- `max_metric_calls = 10`
- `total_num_evals = 45`

那么 stopper 条件已经满足，后续就不会有足够预算用于真正的 candidate expansion。

## 与 Stage 1 smoke 的同构对照

仓库现有 [stage1_deepseek_method_reproduction_report.md](C:/Users/lin/Documents/New%20project%202/reports/stage1_deepseek_method_reproduction_report.md) 里，Stage 1 smoke 也出现了同样结构：

- `max_metric_calls = 10`
- `total_metric_calls = 45`
- `best_score = 0.2222222222222222`
- `Seed prompt equals optimized prompt = yes`

这说明：

- 本次 strict continuation smoke 的 `num_candidates = 1` 现象，不是新的 DeepSeek 异常
- 它和既有 Stage 1 smoke 是同构的预算语义现象

## 审计结论

当前最稳的解释是：

1. `max_metric_calls = 10` 对当前 `valset_size = 45` 来说过小。
2. GEPA 在初始化阶段先完成了 seed candidate 的 full valset evaluation。
3. 这一步已经把 `total_num_evals` 增加到 `45`。
4. `MaxMetricCallsStopper` 立即满足停止条件。
5. 因此后续没有剩余 metric budget 用于真正展开候选。
6. 所以 `num_candidates = 1` 是预算语义结果，不是 DeepSeek 模型异常。

## 对 pilot 的影响

基于当前证据，**现在不建议直接批准 strict continuation pilot**。

理由不是 DeepSeek 失败，而是：

- 当前 smoke 还没有验证“在更合理预算下 candidate expansion 是否实际发生”
- 当前 smoke 只验证了 strict continuation 路径的最小闭环与预算语义

更稳妥的下一步应该是先评估：

- strict continuation pilot readiness
- 或至少先设计一个更合理预算的 continuation 预备审计

在这一步之前，不应直接把本次 smoke 当成 prompt evolution 已成立的证据。
