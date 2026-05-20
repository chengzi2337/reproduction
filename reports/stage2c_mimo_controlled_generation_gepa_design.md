# Stage 2C MiMo Controlled-Generation GEPA Design

## 1. Motivation

Stage 2A 已经定位到以下事实：

- MiMo strict default generation 对 simple `OK` prompt、极短数学题、短 AIME-like 题可返回非空 `content`
- 但从真实 AIME question 开始触发 `HardTimeout`
- `README quickstart seed prompt` 不是主触发因素，因为 Level 3 已经阻塞
- `official AIME-style seed prompt` 也不能消除 blocker

Stage 2B 已经进一步证明：

- 在 `thinking.disabled`
- 且 `max_completion_tokens = 512`
- 且 provider / LiteLLM 路径可达

的 controlled-generation 条件下，MiMo 可以对真实 AIME 单样本返回非空 `content`。

因此 Stage 2C 的目标不是恢复 strict default path，而是验证：

> 在显式 controlled-generation 条件下，MiMo 是否能够完成 GEPA optimize 的最小闭环。

## 2. Scope

Stage 2C 当前阶段只验证 execution feasibility，不验证性能。

固定范围：

- 只允许 `max_metric_calls = 1` 的 sanity
- 不做 smoke
- 不做 pilot
- 不做 saved prompt eval
- 不做 official_budget
- 不和 DeepSeek Stage 1 直接比较
- 不写任何性能优劣结论

## 3. Non-strict Declaration

必须明确声明：

- Stage 2C is not `strict_readme_quickstart_path`.
- Stage 2C is not original same-model reproduction.
- Stage 2C is a controlled-generation engineering adaptation path.

因此：

- 它不是 strict official path
- 它不是 GEPA 原论文复现
- 它不能和 Stage 1 DeepSeek baseline 直接横向比较

## 4. Generation Control

Stage 2C 固定生成控制参数如下：

- `thinking.type = disabled`
- `max_completion_tokens = 512`
- `timeout_seconds = 120`
- `model = mimo-v2.5-pro`
- `provider = mimo`
- `api_base = explicit MIMO_API_BASE`
- `backend_family = openai_compatible`

这些参数是 Stage 2C 的定义组成部分，不得写成“provider 默认行为”。

## 5. Implementation Options

### 调用链确认

本地检查 `gepa.adapters.default_adapter.default_adapter.DefaultAdapter.evaluate()` 后可确认：

- 默认字符串模型路径走 `self.litellm.batch_completion(...)`
- 调用参数中存在 `**self.litellm_batch_completion_kwargs`
- 但 `gepa.optimize(task_lm="openai/<model>")` 的默认路径不会自动为我们注入 `thinking.disabled` 与 `max_completion_tokens`

因此本轮实现优先级如下：

### A. 官方支持优先

如果未来确认 GEPA 或 LiteLLM 的官方字符串模型路径能够无侵入透传 generation kwargs，则优先使用官方支持方式。

### B. Stage 2C 专用注入层

在当前项目状态下，采用最小侵入方案：

- 建立 `Stage 2C` 专用的 context-managed LiteLLM injection layer
- 只在 Stage 2C 脚本的作用域内启用
- 自动为 `litellm.completion` 与 `litellm.batch_completion` 注入：
  - `extra_body={"thinking": {"type": "disabled"}}`
  - `max_completion_tokens=512`
  - `timeout=120`

### C. 作用域隔离

- 注入层只在 Stage 2C 脚本上下文中生效
- 退出 context manager 后恢复原始 LiteLLM 函数
- 不污染 Stage 1 / Stage 2A / Stage 2B

### D. 明确禁止

- 不修改 site-packages 中的 GEPA 包
- 不修改 GEPA optimizer 源码
- 不修改 evaluator

## 6. Success Criteria

Stage 2C minimal sanity 成功标准如下：

- `execute_optimize = true`
- `provider = mimo`
- `path_type = stage2c_mimo_controlled_generation_gepa_sanity`
- `controlled_generation.enabled = true`
- `thinking_type = disabled`
- `max_completion_tokens = 512`
- 生成 `stage2c_result_summary.json`
- 没有无界挂起
- `total_metric_calls` 有记录
- `best_score` 有记录，或明确记录实际返回结构
- `no_saved_prompt_eval = true`
- `not_performance_claim = true`

## 7. Failure Criteria

Stage 2C 失败标准如下：

- 即使在 controlled-generation 参数下仍然 `HardTimeout`
- GEPA 调用链无法注入 controlled-generation 参数
- 注入方案需要修改 GEPA optimizer 或 evaluator
- 输出 `content` 仍为空
- LiteLLM / provider 返回不可恢复错误

## 8. Reporting Rules

Stage 2C 结果只允许写成：

- `Stage 2C controlled-generation GEPA sanity passed`
- `Stage 2C controlled-generation GEPA sanity failed`

明确禁止写成：

- `MiMo baseline`
- `MiMo smoke`
- `MiMo strict path passed`
- `MiMo outperforms DeepSeek`
- `GEPA original reproduction`

## 当前阶段结论

- Stage 2C 现在只进入 design and scaffold 阶段
- 本轮只实现 guarded dry-run / guarded execute 入口
- 本轮不会自动运行 `--execute`
- 本轮不会产生 smoke / pilot / performance result
