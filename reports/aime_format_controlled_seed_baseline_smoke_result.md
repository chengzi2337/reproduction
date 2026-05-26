# AIME format-controlled seed baseline smoke 结果

## 文档定位

- 本报告记录 format-controlled seed baseline 的 guarded smoke 状态。
- 本任务不是 GEPA 优化，不修改 optimizer，不修改 evaluator。
- `official_score` 仍是 official evaluator 下的主指标；`relaxed_extractable_score` 只用于诊断。
- 本结果不能写成 official_budget baseline、same-model reproduction 或新 GEPA result。

## 边界标识

- `model_called = false`
- `api_called = false`
- `gepa_optimize_called = false`
- `new_experiment_executed = false`
- `format_controlled_seed_baseline = true`
- `diagnostic_only = true`
- `not_official_budget_baseline = true`
- `not_gepa_optimized = true`
- `no_optimizer_modified = true`
- `no_evaluator_modified = true`
- `not_same_model_reproduction = true`
- `not_performance_claim = true`

## 执行状态

- 当前状态：dry-run manifest 已生成，smoke 尚未执行。
- 计划样本数：`30`
- batch size：`10`
- prompt versions：`original_seed_prompt, strong_format_seed_prompt, answer_first_format_prompt`
- 本次未调用模型、未调用 API、未运行新实验。

## Prompt 版本

| prompt_version | chars | words | lines |
|---|---:|---:|---:|
| original_seed_prompt | 100 | 17 | 1 |
| strong_format_seed_prompt | 178 | 36 | 5 |
| answer_first_format_prompt | 101 | 17 | 3 |

## 结论边界

- 可以写：这是 format-controlled baseline diagnostic。
- 可以写：该 smoke 用于估计更强格式约束本身对 official score 的影响。
- 不能写：这是新的 GEPA result。
- 不能写：这是 official_budget baseline。
- 不能写：它已经证明或否定 GEPA 的数学推理收益。
