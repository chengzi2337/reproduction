# Stage 2C MiMo Parameter-Adjustment Diagnostic Result

## 结果定位

本文档封存 `Stage 2C: MiMo explicitly controlled-generation GEPA path` 的一次参数调整小样本诊断结果。

- 它不是 GEPA 实验。
- 它不是 smoke rerun。
- 它不是 pilot。
- 它不是性能结论。
- 它不直接和 Stage 1 DeepSeek 对比。

本次诊断只回答一个问题：

在保持 `thinking.disabled` 不变的前提下，把 `max_completion_tokens` 从 `512` 提高到 `1024 / 2048` 后，真实 AIME 单样本是否能稳定出现 `### <answer>`。

## 诊断身份

- `path_type = stage2c_mimo_parameter_adjustment_diagnostic`
- `provider = mimo`
- `backend_family = openai_compatible`
- `api_base = https://token-plan-cn.xiaomimimo.com/v1`
- `model = mimo-v2.5-pro`
- `prompt_type = readme_quickstart_seed_prompt`
- `thinking_type = disabled`
- `token_caps = [1024, 2048]`
- `timeout_seconds = 120`
- `not_gepa_path = true`
- `not_strict_official_path = true`
- `not_performance_claim = true`
- `pilot_not_started = true`

## 本地输出说明

- 本地输出目录位于：
  - `outputs/stage2c_mimo_parameter_adjustment_diagnostic/20260520T182622+0800/`
- 本文档只记录摘要，不提交 `outputs/*`

## 结果摘要

### `max_completion_tokens = 1024`

- direct SDK：非空 `content`
- LiteLLM：非空 `content`
- direct SDK `finish_reason = length`
- LiteLLM `finish_reason = length`
- 两条路径都没有出现精确的 `### <answer>`

这说明：

- `1024` 仍然会触发长度上限；
- 截断问题仍未解除；
- 最终答案格式仍未出现。

### `max_completion_tokens = 2048`

- direct SDK：非空 `content`
- LiteLLM：非空 `content`
- direct SDK `finish_reason = stop`
- LiteLLM `finish_reason = stop`
- 两条路径都没有出现精确的 `### <answer>`
- 两条路径都出现了 `###`，但不是最终 `### <answer>`

这说明：

- 把上限提高到 `2048` 之后，硬截断问题明显缓解；
- 但格式问题仍然存在；
- 模型仍未稳定输出 evaluator 需要的最终答案格式。

## 主结论

本次参数调整诊断把问题进一步收敛为：

1. `512` 的确过低，是截断的重要来源。
2. `1024` 仍不足以稳定避免截断。
3. `2048` 已基本缓解“长度不足”问题，但仍然没有产出精确的 `### <answer>`。

因此，当前最稳妥的结论是：

`提高 token 上限可以缓解 truncated_before_final，但单靠提高 token 上限，不足以解决 format_missing。`

## 当前不能下的结论

基于这次诊断，当前仍然不能写：

- MiMo 已具备 pilot 条件
- Stage 2C 已形成有效 baseline
- 只要把 token 提高到 2048 就一定能跑通 GEPA 质量闭环
- MiMo 数学能力已经被验证

## 对下一步的影响

当前下一步不应是：

- 直接 pilot
- 直接重跑 smoke
- 直接恢复 `thinking.enabled`

当前更合理的下一步应是：

- 新增 `Stage 2C prompt-first / format-enforcement design`
- 重点讨论如何让模型优先输出精确的 `### <answer>`
- 在形成新设计前，不进入 pilot

## 最终口径

关于这次参数调整诊断，当前只允许写：

- `Stage 2C parameter-adjustment diagnostic completed`
- `2048` 缓解了长度截断，但没有解决最终答案格式问题
- 当前主要 blocker 已从“长度不足”进一步收敛到“格式可达性不足”
