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
## Stage 2C smoke failure-mode audit

- 已完成一次只读 audit，不触发新的 `gepa.optimize()`
- `45/45` 样本 `full_assistant_response` 非空
- `0/45` 样本出现精确的 `### <answer>`
- `10/45` 样本虽含 `###`，但仅为 `### Step 1` 等中间标题
- 至少 `23/45` 样本表现出明显的中途截断特征
- 当前最主要的失败模式判断为：
  - `format_missing`
  - `truncated_before_final`
- 因此，`best_score = 0.0` 当前应解释为 `smoke-run artifact / warning signal`
- 当前下一步应先做 `Stage 2C parameter-adjustment design`
- 在参数调整设计完成前，不进入 pilot

## Stage 2C parameter-adjustment diagnostic

- 已完成一次小样本参数诊断，不触发 `gepa.optimize()`
- 保持 `thinking.disabled` 不变
- `max_completion_tokens = 1024`：
  - direct SDK / LiteLLM 均返回非空内容
  - `finish_reason = length`
  - 仍未出现精确的 `### <answer>`
- `max_completion_tokens = 2048`：
  - direct SDK / LiteLLM 均返回非空内容
  - `finish_reason = stop`
  - 仍未出现精确的 `### <answer>`
- 当前结论：
  - 提高 token 上限可以缓解截断
  - 但单靠提高 token 上限，不足以解决 `format_missing`
- 当前下一步应先做 `Stage 2C prompt-first / format-enforcement design`
- 在新设计完成前，不进入 pilot

## Stage 2C prompt-first / format-enforcement

- 当前已进入 prompt-first / format-enforcement design 阶段
- 当前目标是让 MiMo 在 controlled-generation 条件下稳定输出精确的 `### <answer>`
- 当前优先比较的 prompt 变体为：
  - `Variant A: answer-only`
  - `Variant B: first-line final answer`
  - `Variant C: current README quickstart prompt`
- 当前仍未运行新的 direct SDK / LiteLLM 小样本格式诊断
- 在格式诊断完成前，不进入 format-enforced smoke，更不进入 pilot

## Stage 2C prompt-first / format-enforcement diagnostic

- 已完成一次 direct SDK + LiteLLM 的真实小样本格式诊断
- 固定参数：
  - `thinking.disabled`
  - `max_completion_tokens = 2048`
  - `timeout = 120`
  - `sample_count = 3`
- 诊断变体：
  - `Variant A: answer-only`
  - `Variant B: first-line final answer`
  - `Variant C: current README quickstart prompt`
- 当前结果：
  - 三个变体都没有达到“`3/3` 样本稳定输出首行精确 `### <integer>`”的通过标准
  - `2048` 已缓解硬截断，但没有消除 `format_missing`
  - 当前主 blocker 仍然是 `format_missing`
- 因此：
  - 当前不进入 format-enforced smoke rerun
  - 当前不进入 pilot

## Stage 2D output-protocol adaptation

- 当前已进入 `Stage 2D: MiMo output-protocol adaptation diagnostic`
- Stage 2D 不是 strict path
- Stage 2D 不是 Stage 2C pilot
- Stage 2D 不是性能实验
- Stage 2D 不修改 official evaluator
- Stage 2D 先完成了两类只读审计：
  - official evaluator format contract audit
  - existing outputs answer-extractability audit

### Stage 2D official evaluator contract audit

- 已定位到 GEPA AIME 默认 evaluator：
  - `gepa.adapters.default_adapter.default_adapter.ContainsAnswerEvaluator`
- 已定位到 AIME ground truth contract：
  - `answer = "### " + str(x["answer"])`
- official contract 实际上是：
  - `data["answer"] in response`
- 因此：
  - `### 72` 会 official pass
  - `### <answer>\n72\n</answer>` 会 official fail
- Stage 2D 已明确区分：
  - `official_score`
  - `normalized_score`

### Stage 2D existing outputs audit

- 已确认 Stage 2C smoke 全量正文里：
  - `official_evaluator_compatible = 0 / 45`
  - 主 failure mode 是 `markdown_heading_misuse + final_answer_missing`
- 已确认 Stage 2C prompt-first preview 里：
  - 存在 `semantic_answer_present = true` 但 `official_evaluator_compatible = false` 的样本
  - 代表性模式是：
    - `### <answer>\n72\n</answer>`
- 当前更准确的 blocker 写法是：
  - `output_protocol_violation`
  - `format_missing relative to official evaluator contract`
