# Stage 2A MiMo Prompt Complexity Decomposition Design

## 定位

- 本文档定义 `Stage 2A` 的下一轮最小诊断设计
- 它只服务于路线 A 的前半段
- 它不是 GEPA 实验
- 它不是 GEPA smoke
- 它不是 `Stage 2C`
- 它不形成性能结论

## 设计目标

当前已知事实是：

- simple `OK` prompt 在默认 generation 下可用
- 真实 AIME prompt 在默认 generation 下未闭环

因此本轮设计的目标是：

> 在不传 `thinking.disabled`、不传 `max_completion_tokens`、不改 `DefaultAdapter`、不引入 callable 的条件下，用分层 prompt 复杂度诊断去定位，是哪一层 prompt 结构开始触发 MiMo strict default path 的 completion 挂起。

## 固定边界

本轮设计必须同时满足以下边界：

- 不调用 `gepa.optimize()`
- 不修改 `DefaultAdapter`
- 不修改 evaluator
- 不引入 callable
- 不读取 `reasoning_content` 作为最终 `content`
- 不传 `thinking.disabled`
- 不传 `max_completion_tokens`
- 不扩大成 smoke / pilot

## 分层设计

### Level 0：simple OK prompt

- 形式：
  - `Return exactly: OK`
- 目的：
  - 确认默认 completion path 基础可用
- 预期：
  - direct SDK 与 LiteLLM 都应快速返回非空 `content`

### Level 1：极短数学题

- 形式示例：
  - `What is 2+3? Put your final answer in the format ### <answer>`
- 目的：
  - 确认数学类 prompt 本身不会天然触发挂起
- 预期：
  - direct SDK 与 LiteLLM 都应返回非空 `content`

### Level 2：短 AIME-like 题

- 形式：
  - 人工构造一个 2 到 3 句、答案为整数的短数学题
- 目的：
  - 测试稍复杂的数学推理是否开始触发挂起
- 预期：
  - 如果此层开始挂起，则 blocker 已经不依赖真实 AIME 题面

### Level 3：真实 AIME question only

- 形式：
  - 只给 user 真实 AIME 题面
  - 不加 README quickstart seed prompt
- 目的：
  - 判断真实题面本身是否足以触发挂起
- 预期：
  - 如果此层挂起，则 blocker 更偏向真实题面复杂度

### Level 4：README seed prompt + 真实 AIME question

- 形式：
  - system 使用 README quickstart seed prompt
  - user 使用真实 AIME 题面
- 目的：
  - 复现当前 strict default 单样本结构
- 预期：
  - 这是当前最可能复现 blocker 的层级

### Level 5：official AIME-style seed prompt + 真实 AIME question

- 形式：
  - system 使用 official AIME-style seed prompt
  - user 使用真实 AIME 题面
- 目的：
  - 判断 prompt 格式差异是否影响挂起
- 预期：
  - 如果 Level 4 挂起而 Level 5 行为不同，则 prompt 格式本身是可疑因素

## 每层的执行约束

每个 Level 都只允许：

1. direct SDK 执行一次
2. LiteLLM `openai/<model>` 执行一次
3. 使用统一外层硬超时
4. 使用统一请求级 timeout
5. 不做重试放大

## 记录字段

每个 Level 至少记录：

- `level_id`
- `prompt_type`
- `messages_shape`
- `direct_sdk_result`
- `litellm_result`
- `elapsed_seconds`
- `content_nonempty`
- `finish_reason`
- `error_type`
- `error_message`
- `blocked = true/false`

## 判读逻辑

本轮不追求分数，只追求 blocker 收敛。

### 情况 A：Level 0-2 全通，Level 3-5 挂起

- 说明：
  - blocker 更偏向真实 AIME 题面复杂度

### 情况 B：Level 0-3 全通，Level 4-5 挂起

- 说明：
  - blocker 更偏向 seed prompt + 真实题面组合

### 情况 C：Level 4 挂起，Level 5 不同

- 说明：
  - prompt 模板差异可能是重要变量

### 情况 D：Level 1 或 Level 2 就挂起

- 说明：
  - blocker 可能早于真实 AIME 题面复杂度，偏向一般性数学推理默认 generation 行为

## 成功标准

如果本轮设计执行后能够明确回答以下问题，则视为成功：

1. 挂起首次出现在哪个 Level
2. 挂起是否依赖真实 AIME 题面
3. 挂起是否依赖 README seed prompt
4. 挂起在 direct SDK 与 LiteLLM 两层是否一致

## 失败标准

如果执行后仍然只能得到“所有层都挂起”或“所有层都不稳定”而无法区分层级，则视为本轮分层设计未收敛。

## 下一步顺序

1. 先实现一个新的分层诊断脚本，或在现有 Stage 2A 诊断脚本上增加 Level 化输入
2. 仍然不进入 `gepa.optimize()`
3. 仍然不进入 `Stage 2C`
4. 只有在分层结果仍无法收敛时，才重新讨论是否需要转向 `Stage 2C`
