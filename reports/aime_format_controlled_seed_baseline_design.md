# AIME format-controlled seed baseline 设计

## 设计目标

answer extractability audit 显示，AIME official_budget 的 observed official-score gain 不能解释为 pure reasoning improvement：`relaxed_extractable_score_gain = 0.016`，而 `official_score_gain = 0.518666666667`。这说明 output-protocol adherence 是当前 official score 差异的重要组成部分。

因此，下一步应先设计一个 format-controlled seed baseline，用来评估：

> 在不使用 GEPA 优化的情况下，仅通过更强的格式约束 seed prompt，能否显著提高 official score。

本设计只定义实验方案，不执行实验。

## 当前边界

- 不调用模型；
- 不调用 API；
- 不调用 GEPA；
- 不运行新实验；
- 不修改 optimizer；
- 不修改 evaluator；
- 不替换 official score；
- 不提交 outputs；
- 不把 relaxed score 写成 official score。

## Prompt 方案

### Original seed prompt

```text
You are a helpful assistant. Answer the question. Put your final answer in the format '### <answer>'
```

用途：作为当前 official_budget 的原始 seed baseline。

### Strong format seed

```text
Solve the problem. Your final answer must be a single line in the exact format:
### N
Do not use \boxed{}.
Do not use XML tags.
Do not write the final answer in any other format.
```

用途：只加强最终答案格式约束，不引入 GEPA 优化。

### Answer-first format seed

```text
First output the final answer in the exact format:
### N
Then optionally provide a short explanation.
```

用途：测试 answer-first 是否能进一步减少 final-answer extraction failure。

## 评估指标

如果后续执行，应同时报告：

- `official_score`
- `relaxed_extractable_score`
- `format_loss_count`
- `reasoning_error_count`
- `empty_or_invalid_count`
- `not_gepa_optimized = true`
- `format_controlled_seed_baseline = true`

其中 `official_score` 仍是主指标；`relaxed_extractable_score` 只用于诊断，不替代 official score。

## 第一版执行边界

如果后续进行试验，先做小范围 smoke 级别实验：

- 使用少量样本；
- 只验证 format-controlled seed prompt 是否能被 evaluator 正常评分；
- 不作为最终 performance claim；
- 不与 GEPA optimized prompt 做正式优劣结论；
- smoke 通过后再决定是否做完整 test split。

## 预期可回答的问题

该 baseline 可以回答：

- 单纯加强格式约束是否显著减少 format loss；
- official score gain 中有多少可能由 output-protocol adherence 单独解释；
- 是否需要在后续 GEPA 实验前先固定更强 seed prompt；
- 是否应在最终复现报告中把 official score 与 relaxed diagnostic score 并列解释。

该 baseline 不能回答：

- GEPA 是否真正提升数学推理能力；
- Length-Controlled GEPA 是否有效；
- prompt 越长是否越好；
- format-controlled seed 是否一定能达到 optimized prompt 的 official score。

## 建议结论边界

如果将来 smoke 实验显示 strong format seed 分数明显上升，只能写：

> format-controlled seed baseline suggests output-protocol adherence contributes materially to official score.

不能写：

> GEPA 的全部收益都只是格式收益。

也不能写：

> format-controlled seed 已替代 official GEPA result。
