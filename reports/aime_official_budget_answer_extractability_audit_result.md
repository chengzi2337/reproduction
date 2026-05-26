# AIME official_budget answer extractability 只读审计结果

## 文档定位

- 本报告只读分析既有 `per_example_eval.jsonl`。
- 本报告不调用模型、不调用 API、不调用 GEPA、不运行新实验。
- 本报告不修改 official evaluator，也不替换 official score。
- `relaxed_extractable_score` 仅用于诊断 reasoning ability 与 output-protocol adherence 的混合问题。

## 审计边界标识

- `not_new_experiment = true`
- `diagnostic_only = true`
- `relaxed_score_not_official = true`
- `official_score_not_replaced = true`
- `no_model_called = true`
- `no_api_called = true`
- `no_gepa_optimize_called = true`
- `optimizer_not_modified = true`
- `evaluator_not_modified = true`
- `not_performance_claim = true`

## 分类定义

- `official_correct`: official score 为 1。
- `format_loss`: official score 为 0，但保守提取出的最终答案与 gold 一致。
- `reasoning_error`: official score 为 0，且可提取答案与 gold 不一致。
- `empty_or_invalid`: official score 为 0，且 prediction 为空或无法提取最终答案。
- `relaxed_extractable_score = (official_correct + format_loss) / examples`。

注意：`relaxed_extractable_score` 是 diagnostic only，不是 official GEPA score。

## 总体结果

| prompt_version | examples | official_score | relaxed_extractable_score | relaxed_minus_official | official_correct | format_loss | reasoning_error | empty_or_invalid |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| seed | 750 | 0.204 | 0.922666666667 | 0.718666666667 | 153 | 539 | 6 | 52 |
| optimized | 750 | 0.722666666667 | 0.938666666667 | 0.216 | 542 | 162 | 7 | 39 |

## 按 seed 明细

| seed | prompt_version | examples | official_score | relaxed_extractable_score | format_loss | reasoning_error | empty_or_invalid |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0 | seed | 150 | 0.2 | 0.92 | 108 | 2 | 10 |
| 0 | optimized | 150 | 0.633333333333 | 0.933333333333 | 45 | 1 | 9 |
| 1 | seed | 150 | 0.166666666667 | 0.906666666667 | 111 | 1 | 13 |
| 1 | optimized | 150 | 0.666666666667 | 0.946666666667 | 42 | 2 | 6 |
| 2 | seed | 150 | 0.226666666667 | 0.94 | 107 | 1 | 8 |
| 2 | optimized | 150 | 0.926666666667 | 0.926666666667 | 0 | 1 | 10 |
| 3 | seed | 150 | 0.253333333333 | 0.906666666667 | 98 | 2 | 12 |
| 3 | optimized | 150 | 0.726666666667 | 0.946666666667 | 33 | 1 | 7 |
| 4 | seed | 150 | 0.173333333333 | 0.94 | 115 | 0 | 9 |
| 4 | optimized | 150 | 0.66 | 0.94 | 42 | 2 | 7 |

## 结果解释

- `official_score_gain = 0.518666666667`
- `relaxed_extractable_score_gain = 0.016`
- `seed_format_loss_count_minus_optimized = 377`
- `score_gain_is_not_pure_reasoning_improvement = true`
- `official_score_remains_primary = true`

这说明 official score 可以作为当前 GEPA/AIME evaluator 下的正式任务分数使用，但不能直接解释为纯数学推理能力。分数提升同时包含任务求解行为改进和输出协议遵循改进。

## 结论边界

- 可以写：official score 衡量的是当前 evaluator 下的任务表现。
- 可以写：seed prompt 的 format loss 明显多于 optimized prompt。
- 可以写：observed score gain should not be interpreted as pure reasoning improvement。
- 不能写：relaxed score 是 official GEPA score。
- 不能写：relaxed score 可以替代 official score。
- 不能写：所有提升都来自格式。
- 不能写：所有提升都来自推理能力。
- 不能写：这是新实验或新性能评估。
