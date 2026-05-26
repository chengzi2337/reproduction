# AIME format-controlled seed baseline smoke 结果

## 文档定位

- 本报告记录 format-controlled seed baseline 的 guarded smoke 执行结果。
- 本任务不是 GEPA 优化，不调用 `gepa.optimize()`，不修改 optimizer，不修改 evaluator。
- `official_score` 仍是 official evaluator 下的主指标；`relaxed_extractable_score` 只用于诊断。
- 本结果不能写成 official_budget baseline、same-model reproduction 或最终性能结论。

## 边界标识

- `model_called = true`
- `api_called = true`
- `gepa_optimize_called = false`
- `format_controlled_seed_baseline = true`
- `diagnostic_only = true`
- `not_official_budget_baseline = true`
- `not_gepa_optimized = true`
- `no_optimizer_modified = true`
- `no_evaluator_modified = true`
- `not_same_model_reproduction = true`
- `not_performance_claim = true`

## 执行状态

- run_dir: `outputs/aime_format_controlled_seed_baseline_smoke/20260526T151035+0800`
- requested sample limit: `30`
- completed comparable prompts: `original_seed_prompt` 和 `strong_format_seed_prompt`
- incomplete prompt: `answer_first_format_prompt` 只完成 `13 / 30`
- API error records: `0`
- 由于 answer-first 续跑速度过慢且多次超时，本报告不把 answer-first 写成完整 30-sample 结果。

## 诊断指标

| prompt_version | examples | official_score | relaxed_extractable_score | official_correct | format_loss | reasoning_error | empty_or_invalid |
|---|---:|---:|---:|---:|---:|---:|---:|
| `original_seed_prompt` | 30 | 0.233333333333 | 0.933333333333 | 7 | 21 | 1 | 1 |
| `strong_format_seed_prompt` | 30 | 0.866666666667 | 0.866666666667 | 26 | 0 | 1 | 3 |
| `answer_first_format_prompt` | 13 | 0.692307692308 | 0.846153846154 | 9 | 2 | 2 | 0 |

## 初步解释

在这个 30-sample smoke 中，`strong_format_seed_prompt` 相对 `original_seed_prompt` 的 official score 从 `0.233333333333` 提高到 `0.866666666667`，同时 `format_loss_count` 从 `21` 降到 `0`。

这支持一个机制性解释：更强格式约束本身可以显著降低 official evaluator 下的格式损失，并解释 observed official-score gain 的相当一部分。

但该结果不能解释为 pure reasoning improvement。相反，`original_seed_prompt` 的 relaxed extractable score 已经是 `0.933333333333`，说明很多 original seed 输出在数值上可提取正确，但未遵守 strict output protocol。

同时，`strong_format_seed_prompt` 的 relaxed extractable score 为 `0.866666666667`，低于 original seed 的 relaxed extractable score；这说明强格式约束提升了 official score，但并不自动提升 relaxed extractable correctness，也不能证明数学解题能力更强。

## answer-first 限制

`answer_first_format_prompt` 只完成 `13 / 30`，因此只能作为 incomplete diagnostic。当前不能据此判断 answer-first 是否优于 strong-format，也不能把它用于是否扩到完整 150 题的决策。

## 是否建议扩到 150

当前不建议直接扩到 150。

原因：

- `original_seed_prompt` 和 `strong_format_seed_prompt` 已形成可比 30-sample smoke，显示格式约束效应很强；
- 但 `answer_first_format_prompt` 未完成 30-sample smoke；
- 多次 execute 出现长时间无写入和超时；虽然 runner 已补充 `--resume` 与 `--prompt-version`，仍需进一步增加单请求超时和更细粒度进度诊断；
- 直接扩到 150 会把执行稳定性问题放大。

## 结论边界

- 可以写：这是 format-controlled baseline diagnostic。
- 可以写：30-sample smoke 中，strong-format seed 明显降低了 format loss，并显著提高 official score。
- 可以写：该结果支持 output-protocol adherence 是 official score gain 的重要组成部分。
- 不能写：这是新的 GEPA result。
- 不能写：这是 official_budget baseline。
- 不能写：strong-format seed 已经替代 GEPA optimized prompt。
- 不能写：它证明或否定 GEPA 的数学推理收益。
