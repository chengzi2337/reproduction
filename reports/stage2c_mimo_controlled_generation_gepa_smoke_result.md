# Stage 2C MiMo Controlled-Generation GEPA Smoke Result

## 结果定位

- 本文档封存 `Stage 2C: MiMo explicitly controlled-generation GEPA path` 的第一次 smoke 结果。
- 本结果只说明 controlled-generation 条件下的 GEPA smoke 闭环可执行性。
- 本结果不是 baseline。
- 本结果不是 pilot。
- 本结果不是性能结论。
- 本结果不与 Stage 1 DeepSeek 直接比较。

## 本次运行身份

- `path_type = stage2c_mimo_controlled_generation_gepa_smoke`
- `provider = mimo`
- `controlled_generation.enabled = true`
- `thinking_type = disabled`
- `max_completion_tokens = 512`
- `execute_optimize = true`
- `execution_completed = true`
- `total_metric_calls = 45`
- `num_candidates = 1`
- `num_full_val_evals = 1`
- `best_score = 0.0`

## 结果摘要

本次结果只允许写成：

`Stage 2C controlled-generation GEPA smoke passed`

同时必须保持以下解释边界：

- This result is an execution-stability smoke result only.
- It is not a baseline.
- It is not a pilot.
- It is not a performance claim.
- It is not directly comparable to Stage 1 DeepSeek.
- No saved prompt eval was run.
- No official_budget was run.
- No GEPA optimizer/evaluator code was modified.

## 0.0 的解释边界

`best_score = 0.0` 不能写成 MiMo 性能结论。

更准确的表述是：

> The zero score is recorded as a smoke-run artifact and should be treated as a warning signal for Stage 2C quality/format feasibility, not as a MiMo performance conclusion.

因此这次 smoke 的意义是：

- 执行层闭环通过
- 但质量/格式可行性仍存在明显风险

## 固定事实

- `path_type = stage2c_mimo_controlled_generation_gepa_smoke`
- `provider = mimo`
- `task_model = mimo-v2.5-pro`
- `reflection_model = mimo-v2.5-pro`
- `task_lm = openai/mimo-v2.5-pro`
- `reflection_lm = openai/mimo-v2.5-pro`
- `max_metric_calls = 10`
- `seed = 42`
- `not_performance_claim = true`
- `not_baseline = true`
- `not_pilot = true`
- `no_saved_prompt_eval = true`

## 本地输出说明

- 本地输出目录位于：
  - `outputs/stage2c_mimo_controlled_generation_gepa_smoke/20260520T160346+0800/`
- 本文档只记录结果摘要，不提交 `outputs/*`
