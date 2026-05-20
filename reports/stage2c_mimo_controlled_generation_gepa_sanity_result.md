# Stage 2C MiMo Controlled-Generation GEPA Sanity Result

## 结果定位

- 本文档封存 `Stage 2C: MiMo explicitly controlled-generation GEPA path` 的第一次最小 sanity 结果。
- 本结果只说明 controlled-generation 条件下的最小 GEPA 闭环可执行性。
- 本结果不是 strict path 结果。
- 本结果不是 smoke。
- 本结果不是 pilot。
- 本结果不是性能结论。

## 本次运行身份

- `path_type = stage2c_mimo_controlled_generation_gepa_sanity`
- `provider = mimo`
- `backend_family = openai_compatible`
- `task_model = mimo-v2.5-pro`
- `reflection_model = mimo-v2.5-pro`
- `task_lm = openai/mimo-v2.5-pro`
- `reflection_lm = openai/mimo-v2.5-pro`
- `max_metric_calls = 1`
- `seed = 42`
- `execute_optimize = true`

## Controlled Generation

- `controlled_generation.enabled = true`
- `thinking_type = disabled`
- `max_completion_tokens = 512`
- `timeout_seconds = 120`

## 结果摘要

本次结果只允许写成：

`Stage 2C controlled-generation GEPA sanity passed`

本次运行记录到：

- `execution_completed = true`
- `controlled_generation_applied = true`
- `best_score = 0.044444444444444446`
- `total_metric_calls = 45`
- `num_candidates = 1`
- `num_full_val_evals = 1`

这些字段只用于说明 sanity 闭环完成，不构成 baseline、smoke、pilot 或性能判断。

## 边界确认

- 本次没有运行 smoke
- 本次没有运行 pilot
- 本次没有运行 saved prompt eval
- 本次没有运行 official_budget
- 本次没有修改 GEPA optimizer
- 本次没有修改 evaluator
- 本次没有修改 Stage 1 历史结果
- 本次没有把 `reasoning_content` 手工拼入 `content`

## 本地输出说明

- 本地输出目录位于：
  - `outputs/stage2c_mimo_controlled_generation_gepa_sanity/20260520T144342+0800/`
- 本文档只记录结果摘要，不提交 `outputs/*`

## 后续解释规则

后续只能写：

- `Stage 2C controlled-generation GEPA sanity passed`

不能写：

- `MiMo baseline`
- `MiMo smoke`
- `MiMo pilot`
- `MiMo strict path passed`
- `MiMo outperforms DeepSeek`
- `GEPA original reproduction`
