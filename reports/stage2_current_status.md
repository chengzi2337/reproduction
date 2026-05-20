# Stage 2 Current Status

## 当前事实

- MiMo Token Plan key 已验证有效
- `MIMO_API_BASE` 当前应使用：
  - `https://token-plan-cn.xiaomimimo.com/v1`
- Windows 直连 `token-plan-cn.xiaomimimo.com:443` 当前不视为稳定路径
- 代理可达路径当前可用

## Stage 2A strict default path 结果

- `first_blocked_level = 3`
- Level 0-2：passed
- Level 3-5：`HardTimeout`
- direct SDK 与 LiteLLM 行为一致
- blocker 由真实 AIME 题面复杂度在 MiMo strict default generation 下触发
- `README quickstart seed prompt` 不是主触发因素，因为 Level 3 已经阻塞
- `official AIME-style seed prompt` 也没有移除该 blocker
- Stage 2A 没有调用 `gepa.optimize()`
- Stage 2A 没有启动 smoke / pilot
- Stage 2A 没有使用 `thinking.disabled`
- Stage 2A 没有使用 `max_completion_tokens` 限制
- 因此 Stage 2A strict default path 当前处于 blocked 状态

## Stage 2B controlled-generation 结果

- `thinking.disabled`
- `max_completion_tokens = 512`
- direct SDK + 真实 AIME 单样本返回非空 `content`
- LiteLLM `openai/mimo-v2.5-pro` + 同条件返回非空 `content`

这些结果只属于 `Stage 2B: MiMo controlled-generation diagnostic path`，不是 strict path 闭环，不构成性能结论。

## Stage 2C 当前状态

- Stage 2C 已完成 design and scaffold
- Stage 2C 第一次 `max_metric_calls = 1` controlled-generation sanity 已通过
- Stage 2C 第一次 `max_metric_calls = 10` controlled-generation smoke 已通过
- Stage 2C 的定义是：
  - `MiMo explicitly controlled-generation GEPA path`
- Stage 2C 不是 strict official path
- Stage 2C 不是 original same-model reproduction
- Stage 2C 不是 Stage 1 DeepSeek continuation
- Stage 2C 当前仍然没有 pilot / performance result
- Stage 2C smoke 的 `best_score = 0.0` 只记录为 smoke artifact / warning signal，不构成 MiMo 性能结论

## 当前不做的事

- 不运行 `configs/mimo_pilot.yaml`
- 不运行 `official_budget`
- 不运行 saved prompt eval
- 不自动扩展到 pilot

## 下一步上限

- 当前应先做 `Stage 2C smoke failure-mode audit design`
- 在 failure-mode audit 前，不直接进入 pilot
- 后续若继续 Stage 2C，仍然必须保持：
  - non-strict controlled-generation path
  - 非性能实验解释
