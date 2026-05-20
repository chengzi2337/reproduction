# Stage 2C MiMo Parameter-Adjustment Design

## 定位

本文档定义 `Stage 2C: MiMo explicitly controlled-generation GEPA path` 的参数调整设计。

- 它不是新的 smoke 执行。
- 它不是 pilot。
- 它不是性能实验。
- 它不改 `GEPA optimizer`、`DefaultAdapter`、evaluator。
- 它不直接触发新的 `gepa.optimize()`。

本文档的目标仅是回答：

在当前 `thinking.disabled + max_completion_tokens = 512` 已经证明可执行但存在 `format_missing + truncated_before_final` 风险的前提下，下一步应如何设计更稳妥的参数调整诊断。

## 背景

当前已知：

- Stage 2A strict default path 在真实 AIME 题面上 blocked。
- Stage 2B 已证明：在 `thinking.disabled` 与 `max_completion_tokens = 512` 条件下，MiMo 能返回真实 AIME 单样本非空 `content`。
- Stage 2C sanity 与 smoke 都已通过 execution-stability 闭环。
- Stage 2C smoke failure-mode audit 已确认：
  - `45/45` 样本存在非空正文
  - `0/45` 样本出现精确的 `### <answer>`
  - 至少 `23/45` 样本存在明显截断

因此，当前最主要的问题不是“能不能跑完”，而是：

- 如何让输出长度覆盖完整解题过程与最终 `### <answer>`。
- 如何在不恢复 strict default generation 的情况下，提高 Stage 2C 的格式可达性。

## 设计边界

当前参数调整设计只允许讨论两条主线：

### A. 保持 `thinking.disabled`，提高 `max_completion_tokens`

建议的候选值：

- `1024`
- `2048`

这是当前最稳妥的优先方向，因为：

- Stage 2A 已证明 strict default generation 会在真实 AIME 上 HardTimeout。
- 当前 smoke 的主问题更像“长度不足”，而不是“完全无内容”。
- 提高 completion token 上限，风险低于重新启用 `thinking.enabled`。

### B. 强化 prompt，让模型更早输出最终答案

可讨论的方向包括：

- 在 README quickstart seed prompt 的基础上增加“先给最终答案，再给解释”的受控变体
- 明确要求第一行或前若干行出现 `### <answer>`

但该方向必须单独标注为：

- 非 strict
- prompt-adjusted controlled-generation path

因为它已经偏离原始 Stage 2C 当前使用的 README quickstart seed prompt。

## 当前不建议的方向

当前不建议优先尝试：

### 1. 恢复 `thinking.enabled`

原因：

- Stage 2A 已经表明默认 generation 在真实 AIME 题面会触发 HardTimeout。
- 重新启用 thinking，很可能把当前问题从“截断/格式”重新推回“长时间挂起”。

### 2. 直接进入 pilot

原因：

- 当前 smoke 只证明执行闭环可达。
- `best_score = 0.0` 的 failure mode 尚未通过参数调整被缓解。

### 3. 直接重跑 Stage 2C smoke

原因：

- 在参数不变的情况下，重复 smoke 只会重复当前 failure mode。
- 先做小规模参数诊断更有信息量。

## 推荐下一步

当前最稳妥的下一步是：

### 第一步：非 GEPA 参数诊断

只做真实 AIME 单样本或极少量样本诊断：

- 保持 `thinking.disabled`
- 分别测试：
  - `max_completion_tokens = 1024`
  - `max_completion_tokens = 2048`
- 检查：
  - 是否出现精确的 `### <answer>`
  - 是否仍然明显截断
  - 是否出现新的无界挂起

这一步不进入 GEPA，只是 Stage 2C 的参数可达性诊断。

### 第二步：如有必要，再讨论 prompt 约束增强设计

如果仅提高 token 上限仍无法稳定出现 `### <answer>`，再讨论：

- 是否要设计“先给最终答案、后给解释”的 controlled prompt 变体

但该变体必须保持单独命名，不能混写成 strict path 或原始 Stage 2C 当前 prompt。

## 成功标准

参数调整诊断的最小成功标准应为：

- 在 `thinking.disabled` 保持不变时
- 更高 token 上限下
- 真实 AIME 单样本能够稳定出现精确的 `### <answer>`
- 且不重新触发 Stage 2A 式的无界挂起

只有满足这一点，才值得讨论：

- 是否重跑 Stage 2C smoke
- 是否进一步讨论 pilot 前的条件

## 当前结论

在本轮设计结束时，当前只允许写：

- Stage 2C smoke 已通过 execution-stability
- Stage 2C smoke 的 `0.0` 主要怀疑由 `format_missing + truncated_before_final` 引起
- 下一步应先做参数调整诊断设计
- 当前不进入 pilot

当前不允许写：

- 已找到最终可用的 MiMo Stage 2C 参数
- MiMo 已具备 pilot 条件
- MiMo 已具备性能结论
