# GEPA `max_metric_calls` 计数语义审计

生成时间：2026-06-01

## 目标

澄清当前本地安装版 GEPA 中：

- `max_metric_calls` 的真实停止语义是什么；
- `total_metric_calls` 的真实计数口径是什么；
- 为什么 Stage 4C 传入 `--max-metric-calls 1`，结果仍出现 `total_metric_calls = 3`。

## 审计范围

- `scripts/stage4c_run_glm_streaming_gepa_sanity.py`
- `outputs/stage4c_glm_streaming_gepa_sanity/20260601T135355+0800/paired_results.json`
- 已安装 GEPA 源码：
  - `gepa/api.py`
  - `gepa/utils/stop_condition.py`
  - `gepa/core/state.py`
  - `gepa/core/engine.py`
  - `gepa/core/result.py`

## 已证实事实

### 1. Stage 4C 真实传参

Stage 4C runner 的默认设置是：

- `DEFAULT_MAX_METRIC_CALLS = 1`
- `DEFAULT_DIAGNOSTIC_VAL_LIMIT = 3`

这说明该 run 的预算设置确实是：

- 预算参数：`max_metric_calls = 1`
- 验证集大小：`diagnostic_val_limit = 3`

### 2. Stage 4C 真实结果

在 `paired_results.json` 中，两个 thinking arm 都出现了同一组关键字段：

- `total_metric_calls = 3`
- `num_val_instances = 3`
- `num_full_val_evals = 1`

这说明：

- GEPA 至少做了一次完整 validation evaluation；
- 结果中的 `total_metric_calls` 与 `num_val_instances` 数量一致。

### 3. `max_metric_calls` 的停止器语义

`gepa.api.optimize()` 并不直接在入口处裁剪执行，而是把 `max_metric_calls` 包装成 `MaxMetricCallsStopper`。

`MaxMetricCallsStopper` 的停止条件是：

```python
return gepa_state.total_num_evals >= self.max_metric_calls
```

因此，当前实现比较的不是：

- optimize 被调用了几次；
- 候选被接受了几个；
- 主循环跑了几轮。

当前实现比较的是：

- `gepa_state.total_num_evals`

## 关键语义：`total_num_evals` 按样本级评估数记账

`gepa/core/engine.py` 的 `_evaluate_on_valset()` 会在完成一次 validation batch 评估后执行：

```python
state.increment_evals(num_actual_evals)
```

而 `increment_evals()` 做的事情是：

```python
self.total_num_evals += count
```

这里的 `count` 是本次实际评估的样本数，不是“1 次外层评估调用”。

因此可以直接得出：

- `total_metric_calls` 的计数粒度是样本级；
- 如果一次 full validation 评估了 3 个样本，就会累加 3。

## 关键语义：seed 初始化 full eval 也计入预算

最关键的实现点在 `gepa/core/state.py` 的 `initialize_gepa_state()`。

当 GEPA 初始化 seed candidate 时，它会先对 seed candidate 做一次完整 valset 评估，然后立刻执行：

```python
num_evals_run += len(eval_result.scores_by_val_id)
gepa_state.num_full_ds_evals = 1
gepa_state.total_num_evals = num_evals_run
```

这意味着：

- seed candidate 的初始 full validation evaluation 会先消耗预算；
- 主循环开始前，`total_num_evals` 可能已经大于 `max_metric_calls`。

随后 `GEPAEngine.run()` 的主循环入口才检查：

```python
while not self._should_stop(state):
```

所以当前语义下，**预算检查发生在 seed full eval 之后，而不是之前。**

## 为什么 `max_metric_calls = 1` 却得到 `total_metric_calls = 3`

把上面的事实合在一起，原因就非常直接了：

1. Stage 4C 设置了 `diagnostic_val_limit = 3`
2. GEPA 初始化时先对 seed candidate 做一次完整 valset 评估
3. 这次 full eval 实际评估了 3 个样本
4. 因此初始化阶段就把 `total_num_evals` 写成了 3
5. 之后 `MaxMetricCallsStopper` 才看到 `3 >= 1`，于是停止

所以：

- `max_metric_calls = 1`
- `total_metric_calls = 3`

在当前实现里完全一致，不是 runner 漏传参数，也不是结果字段写错。

## 最小本地复现

本轮还做了一个不依赖真实 provider 的最小复现实验：

- `valset_size = 3`
- `max_metric_calls = 1`
- seed candidate 直接输出正确答案

结果是：

- `num_candidates = 1`
- `num_full_val_evals = 1`
- `total_metric_calls = 3`

这说明即使主循环完全不继续，seed 初始化 full eval 也足以把 `total_metric_calls` 推到 3。

## 审计结论

当前本地安装版 GEPA 的 `max_metric_calls` 语义应解释为：

> 允许的累计样本级 metric evaluation 数量上限。

并且：

> 这个累计值包含 seed candidate 初始化阶段的 full validation evaluation。

因此：

- `max_metric_calls = 1` 不是“只允许 1 次 optimize 外层调用”
- `max_metric_calls = 1` 也不是“结果中的 total_metric_calls 必须显示 1”

在 `diagnostic_val_limit = 3` 的配置下，更准确的解释是：

- GEPA 先对 3 个 validation 样本做了 seed full eval
- 所以结果自然记录为 `total_metric_calls = 3`

## 对 Stage 4C 的直接影响

如果后续还想保留“`max_metric_calls = 1`”这个配置，就必须接受它当前的真实含义是：

- 最多允许一次非常小的样本级预算；
- 但只要 `valset_size > 1`，seed 初始化本身就可能先超预算。

如果目标是让这个参数更接近“整个 sanity run 只做 1 个样本级评估”，只有两条路：

1. 把 `diagnostic_val_limit` 一起降到 `1`
2. 修改上游 GEPA 实现，把 seed 初始化 full eval 排除在预算之外

本轮只做语义审计，不对 GEPA 上游实现做价值判断，也不修改其当前行为。
