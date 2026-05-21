# Stage 2 Current Status

## 当前事实

- MiMo Token Plan key 已验证有效
- `MIMO_API_BASE` 当前应使用：
  - `https://token-plan-cn.xiaomimimo.com/v1`
- Windows 直连 `token-plan-cn.xiaomimimo.com:443` 当前不视为稳定路径
- 代理可达路径当前可用

## Stage 2A strict default path

- `first_blocked_level = 3`
- Level 0-2：passed
- Level 3-5：`HardTimeout`
- direct SDK 与 LiteLLM 行为一致
- blocker 由真实 AIME 题面复杂度在 MiMo strict default generation 下触发
- `README quickstart seed prompt` 不是主触发因素，因为 Level 3 已经阻塞
- `official AIME-style seed prompt` 也不能移除 blocker
- Stage 2A 没有调用 `gepa.optimize()`
- Stage 2A 没有使用 `thinking.disabled`
- Stage 2A 没有使用 `max_completion_tokens`

## Stage 2B controlled-generation diagnostic

- `thinking.disabled`
- `max_completion_tokens = 512`
- direct SDK + 真实 AIME 单样本返回非空 `content`
- LiteLLM `openai/mimo-v2.5-pro` + 同条件返回非空 `content`

这些结果只属于 `Stage 2B: MiMo controlled-generation diagnostic path`，不构成 strict path 成功，也不构成性能结论。

## Stage 2C controlled-generation GEPA path

- Stage 2C 是 `MiMo explicitly controlled-generation GEPA path`
- Stage 2C 不是 strict official path
- Stage 2C 不是 original same-model reproduction
- Stage 2C 不是 Stage 1 DeepSeek continuation
- Stage 2C 已完成：
  - 一次 `max_metric_calls = 1` sanity
  - 一次 `max_metric_calls = 10` smoke
- Stage 2C smoke 的 `best_score = 0.0` 只记录为 smoke artifact / warning signal，不构成 MiMo 性能结论

### Stage 2C smoke failure-mode audit

- `45/45` 样本 `full_assistant_response` 非空
- `0/45` 样本出现精确的 `### <answer>`
- `10/45` 样本虽含 `###`，但只是 `### Step 1` 一类中间标题
- 至少 `23/45` 样本表现出明显中途截断
- 当前主要 failure mode 是：
  - `format_missing`
  - `truncated_before_final`

### Stage 2C parameter-adjustment diagnostic

- `max_completion_tokens = 1024`
  - direct SDK / LiteLLM 均返回非空内容
  - `finish_reason = length`
  - 仍未出现精确 `### <answer>`
- `max_completion_tokens = 2048`
  - direct SDK / LiteLLM 均返回非空内容
  - `finish_reason = stop`
  - 硬截断已明显缓解
  - 仍未稳定出现精确 `### <answer>`

结论：

- token 上限过低是部分原因
- 但当前主 blocker 已从 `truncated_before_final` 进一步收敛到 `format_missing`

### Stage 2C prompt-first / format-enforcement diagnostic

- 已比较三种 prompt 变体：
  - `Variant A: answer-only`
  - `Variant B: first-line final answer`
  - `Variant C: current README quickstart prompt`
- 固定参数：
  - `thinking.disabled`
  - `max_completion_tokens = 2048`
  - `timeout = 120`
  - `sample_count = 3`
- 结果：
  - 没有任何变体达到稳定输出精确 `### <integer>` 的通过标准
  - `2048` 已缓解硬截断，但没有消除 `format_missing`

## Stage 2D output-protocol adaptation

- Stage 2D 是 `MiMo output-protocol adaptation diagnostic`
- Stage 2D 不是 strict path
- Stage 2D 不是 Stage 2C pilot
- Stage 2D 不是性能实验
- Stage 2D 不修改 official evaluator

### Stage 2D official evaluator contract audit

- 已定位 GEPA AIME 默认 evaluator：
  - `ContainsAnswerEvaluator`
- 已定位 AIME ground truth contract：
  - `answer = "### " + str(x["answer"])`
- official contract 实际上是：
  - `data["answer"] in response`
- 因此：
  - `### 72` 会 official pass
  - `### <answer>\n72\n</answer>` 会 official fail

### Stage 2D existing outputs audit

- Stage 2C smoke 全量输出中：
  - `official_evaluator_compatible = 0 / 45`
- prompt-first 样本中已出现：
  - `semantic_answer_present = true`
  - 但 `official_evaluator_compatible = false`
- 当前更准确的 blocker 写法是：
  - `output_protocol_violation`
  - `format_missing relative to official evaluator contract`

### Stage 2D Phase 2 official-contract prompt adaptation

- 已完成 `official-contract prompt adaptation diagnostic`
- 没有任何 prompt variant 同时满足 direct SDK 与 LiteLLM 的稳定 `official_evaluator_compatible`
- 因此：
  - `MiMo Stage 2D Phase 2 did not meet the entry gate for adapted GEPA smoke`
  - `Prompt-only official-contract adaptation is not stable enough`

## 当前决策

- 不进入 MiMo pilot
- 不运行 adapted GEPA smoke
- 不继续扩大 MiMo prompt-only 实验
- 当前应暂停 MiMo experimental expansion
- 当前应回到 `DeepSeek strict-readme continuation` 主线
