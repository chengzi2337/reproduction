# Stage 2C MiMo Smoke Failure-Mode Audit Result

## 审计定位

本报告是对既有 `Stage 2C controlled-generation GEPA smoke` 输出的只读审计结果。

- 本报告不触发新的 `gepa.optimize()`
- 本报告不重跑 smoke
- 本报告不进入 pilot
- 本报告不做性能结论

本报告的目标仅是解释：为什么在 smoke 执行闭环通过的前提下，`best_score = 0.0`。

## 被审计运行

- `path_type = stage2c_mimo_controlled_generation_gepa_smoke`
- `provider = mimo`
- `thinking_type = disabled`
- `max_completion_tokens = 512`
- `execution_completed = true`
- `best_score = 0.0`
- `total_metric_calls = 45`
- `num_candidates = 1`
- `num_full_val_evals = 1`

本次审计对应的本地输出目录为：

- `outputs/stage2c_mimo_controlled_generation_gepa_smoke/20260520T160346+0800/`

本报告只记录审计摘要，不提交 `outputs/*`。

## 运行级结论

从 `stage2c_smoke_result_summary.json` 可以直接确认：

- 这次 run 完整执行结束，没有无界挂起。
- 这次 run 只记录到 `1` 个 candidate。
- 这次 run 只记录到 `1` 次 full val eval。
- 因此，这次 smoke 的意义仍然是 execution-stability 验证，而不是有效 prompt 优化证明。

更准确地说，这次 run 只证明：

`Stage 2C controlled-generation GEPA smoke passed`

它不证明：

- MiMo baseline
- MiMo pilot readiness
- MiMo performance quality
- MiMo 优于或弱于 Stage 1 DeepSeek

## 样本级统计

本次对 `generated_best_outputs_valset/task_*/iter_0_prog_0.json` 做了只读统计。

统计范围：

- 总样本数：`45`

统计结果：

- `45/45` 样本的 `full_assistant_response` 为非空
- `10/45` 样本包含 `###`
- `0/45` 样本包含精确的 `### <answer>`
- `0/45` 样本能被直接确认写出了 README quickstart 期望的最终答案格式
- `23/45` 样本表现出明显的截断特征：
  - 在中间公式、句子或推导未结束处停止
  - 且没有最终答案格式

补充观察：

- 那 `10/45` 个包含 `###` 的样本，内容是诸如 `### Step 1`、`### Step 2` 这样的中间小标题，不是最终答案行。
- 至少部分样本虽然出现了类似结论句或数值结论，但仍然没有输出 `### <answer>`。

## 代表性样本现象

审计中观察到三种代表性模式：

### 模式 A：长推导后在中间公式处截断

例如部分样本在以下位置停止：

- 以 `$h(t) =` 结束
- 以 `$P(0) + Q(0) =` 结束
- 以未闭合表达式或未完成单词结束

这类样本最符合：

- `truncated_before_final`
- `format_missing`

### 模式 B：存在中间结构化标题，但没有最终答案格式

例如部分样本出现：

- `### Step 1: Understand the setup`
- `### Step 2: ...`

但没有出现：

- `### <answer>`

这说明：

- 即使模型会使用 `###`，当前也主要把它用于中间解释结构，而不是 evaluator 期望的最终答案标记。

### 模式 C：可能已有结论，但仍未转成 evaluator 友好的最终格式

例如个别样本尾部出现了类似：

- `Sum = 528 + 561 + 595 = 1684.`

但依然没有：

- `### <answer>`

这说明：

- 某些样本不一定完全缺少结论内容；
- 但至少在当前 smoke 输出中，它们仍没有转成 README quickstart seed prompt 要求的最终答案格式。

## 主结论

当前最稳妥的主结论是：

`best_score = 0.0` 的主要风险来源不是“输出为空”，而是“最终答案格式缺失”与“部分样本在最终答案前被截断”的组合。`

更细地说：

1. 非空 content 不是当前主问题，因为 `45/45` 样本都有正文。
2. README quickstart 期望的 `### <answer>` 没有在样本中落实，因为 `0/45` 命中精确最终格式。
3. 截断现象是高概率辅助因素，因为大量样本在中间推导位置停止。
4. `num_candidates = 1` 与 `num_full_val_evals = 1` 也说明这次 smoke 更像一次可执行性闭环，而不是有效优化闭环。

因此，本次 smoke 的 `0.0` 更应该被解释为：

- `format feasibility warning`
- `possible truncation warning`

而不是：

- MiMo 数学能力结论
- MiMo backend 最终性能结论

## 当前不能下的结论

基于现有证据，当前仍然不能严格断言：

- 所有样本的数值答案都错误
- `thinking.disabled` 一定是唯一主因
- `max_completion_tokens = 512` 一定是唯一主因
- 只要把 token 上限调大就一定能通过 smoke 质量门槛

因为当前证据更强地支持的是：

- 格式缺失是确定现象
- 截断是高频现象
- 但“数值答案是否本来正确”仍缺少逐样本 evaluator 级证据

## 对下一步的影响

基于本次 audit，当前正确顺序应为：

1. 保持 Stage 2C smoke 已通过的 execution-stability 结论。
2. 暂停进入 pilot。
3. 先讨论参数调整或格式可达性审计设计。
4. 在形成新的受控参数设计前，不把当前 smoke 解释成质量通过。

## 最终口径

本次 audit 后，关于 Stage 2C smoke，当前只允许写：

- `Stage 2C controlled-generation GEPA smoke passed`
- `best_score = 0.0` is a smoke-run artifact / warning signal
- 当前主要怀疑的失败模式是 `format_missing` 与 `truncated_before_final`
- 当前还不应进入 pilot

当前不允许写：

- `MiMo baseline established`
- `MiMo pilot ready`
- `MiMo performance validated`
- `MiMo outperforms DeepSeek`
