# Stage 2A MiMo Prompt Complexity Decomposition Result

## 结果定位

- 本文档封存 `Stage 2A: MiMo strict default path` 的 prompt complexity decomposition 结果。
- 本结果只用于 blocker diagnosis，不是 GEPA 实验结果。
- 本结果不构成性能结论，不构成 strict path 闭环结论。
- 本阶段没有调用 `gepa.optimize()`。
- 本阶段没有启动 smoke / pilot。

## 结果摘要

- `first_blocked_level = 3`
- Level 0-2：`passed`
- Level 3-5：`HardTimeout`
- direct SDK 与 LiteLLM 表现一致

## 各层结论

### Level 0

- `simple OK prompt`
- 默认 generation 下 direct SDK 与 LiteLLM 均返回非空 `content`

### Level 1

- 极短数学题
- 默认 generation 下 direct SDK 与 LiteLLM 均返回非空 `content`

### Level 2

- 短 AIME-like 题
- 默认 generation 下 direct SDK 与 LiteLLM 均返回非空 `content`

### Level 3

- `real AIME question only`
- direct SDK 与 LiteLLM 均进入 `HardTimeout`

### Level 4

- `README quickstart seed prompt + real AIME question`
- direct SDK 与 LiteLLM 均进入 `HardTimeout`

### Level 5

- `official AIME-style seed prompt + real AIME question`
- direct SDK 与 LiteLLM 均进入 `HardTimeout`

## 解释边界

- 当前 blocker 由真实 AIME 题面复杂度在 MiMo strict default generation 下触发。
- `README quickstart seed prompt` 不是主触发因素，因为 Level 3 已经开始阻塞。
- `official AIME-style seed prompt` 也没有消除该 blocker。
- 当前不能把结果写成“MiMo strict default path 已不可用”。
- 更准确的表述是：
  - MiMo strict default path 在当前 endpoint、当前代理可达路径、当前模型 `mimo-v2.5-pro`、当前真实 AIME prompt 下尚未闭环。

## 严格边界

- 本阶段没有使用 `thinking.disabled`
- 本阶段没有使用 `max_completion_tokens` 限制
- 本阶段没有修改 `DefaultAdapter`
- 本阶段没有修改 evaluator
- 本阶段没有修改 GEPA optimizer
- 本阶段没有把 `reasoning_content` 手工拼入 `content`

## 对 Stage 2C 的含义

- Stage 2A strict default path 当前被阻塞。
- Stage 2C 现在成为下一设计目标。
- Stage 2C 的定位是：
  - `MiMo explicitly controlled-generation GEPA path`
  - 非 strict path
  - 非性能实验
  - 目标仅是验证 controlled-generation 条件下的最小 GEPA 闭环可执行性

## 本地输出说明

- 本地输出目录位于：
  - `outputs/mimo_prompt_complexity_decomposition/<timestamp>/`
- 本文档只记录结果摘要，不提交 `outputs/*`
