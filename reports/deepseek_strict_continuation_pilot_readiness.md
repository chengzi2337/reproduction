# DeepSeek Strict Continuation Pilot Readiness

## 文档定位

本报告用于回答一个问题：

> 在当前仓库状态下，是否已经具备进入 `DeepSeek strict-readme continuation pilot` 的前置条件？

本报告只做设计与审查：

- 不调用模型
- 不调用 `gepa.optimize()`
- 不修改 GEPA optimizer
- 不修改 evaluator
- 不运行 pilot

## 已知事实

### 1. DeepSeek strict continuation smoke 已完成

已封存结果见：

- [deepseek_strict_continuation_smoke_result.md](C:/Users/lin/Documents/New%20project%202/reports/deepseek_strict_continuation_smoke_result.md)
- [deepseek_strict_continuation_smoke_candidate_expansion_audit.md](C:/Users/lin/Documents/New%20project%202/reports/deepseek_strict_continuation_smoke_candidate_expansion_audit.md)

当前已确认：

- `path_type = deepseek_strict_continuation_smoke`
- `provider = deepseek`
- `task_lm = openai/deepseek-v4-flash`
- `reflection_lm = openai/deepseek-v4-pro`
- `dataset_source = gepa.examples.aime.init_dataset() with local cache-backed load_dataset`
- `trainset_size = 45`
- `valset_size = 45`
- `testset_size = 150`
- `best_score = 0.2222222222222222`
- `total_metric_calls = 45`
- `num_candidates = 1`
- `num_full_val_evals = 1`

### 2. `num_candidates = 1` 的原因已查明

这不是 DeepSeek 异常，也不是 strict path 失败。

只读审计已确认：

- `max_metric_calls = 10`
- `valset_size = 45`
- GEPA 初始化阶段先执行 seed candidate 的 full valset evaluation
- `total_num_evals` 在初始化后直接达到 `45`
- `MaxMetricCallsStopper` 的语义是：
  - `total_num_evals >= max_metric_calls`

因此：

- strict smoke 已完成路径闭环
- 但它没有剩余预算用于真正展开 candidate

### 3. Stage 1 已给出预算经验对照

仓库现有 Stage 1 DeepSeek 报告显示：

- `max_metric_calls = 10`
  - `total_metric_calls = 45`
  - `best_score = 0.2222222222222222`
  - `Seed prompt equals optimized prompt = yes`
- `max_metric_calls = 50`
  - `total_metric_calls = 96`
  - `best_score = 0.8444444444444444`
  - `Prompt evolution observed = yes`

这说明：

- 在当前任务规模下，`50` 至少在 Stage 1 wrapper path 中足以跨过 baseline-only 形态
- 但 strict continuation 仍然需要单独验证，不能直接继承 Stage 1 结论

## Readiness 审查维度

### A. 路径身份是否清晰

结论：**通过**

理由：

- strict continuation 已有独立计划书
- strict continuation smoke 已与 Stage 1 wrapper 分轨
- 当前术语边界清晰：
  - 不是 `Stage 1 updated baseline`
  - 不是 `same-model reproduction`
  - 不是 `official_budget`

### B. provider / 模型 / 数据集入口是否稳定

结论：**通过**

理由：

- DeepSeek provider 仍可用
- `DEEPSEEK_API_KEY / DEEPSEEK_API_BASE` 注入路径已验证过
- strict continuation smoke 已完成真实闭环
- local cache-backed `load_dataset` 已证明可以稳定读取：
  - `trainset = 45`
  - `valset = 45`
  - `testset = 150`

### C. seed prompt 身份是否稳定

结论：**通过**

理由：

- strict continuation 明确使用 README quickstart seed prompt
- 当前没有 seed prompt 身份漂移

### D. 当前是否已证明 strict continuation 出现 prompt evolution

结论：**未通过**

理由：

- 当前 strict smoke 只证明了路径闭环
- 当前还没有候选真正展开的证据
- 当前不能把 smoke 结果写成 prompt evolution 已成立

### E. 当前是否已具备进入 pilot 的最低前提

结论：**有条件通过**

理由：

- 结构性阻塞已经查明，不是模型或路径失败
- 当前 smoke 未展开 candidate 的原因是预算过小，而不是 strict continuation 不可执行
- 因此，如果后续 pilot 使用能跨过 baseline evaluation 的预算，进入 pilot 在技术上是合理的

## Pilot 建议参数

若后续单独批准 strict continuation pilot，建议保持：

- `provider = deepseek`
- `task_model = deepseek-v4-flash`
- `reflection_model = deepseek-v4-pro`
- `seed_prompt = README quickstart seed prompt`
- `seed = 42`
- `path identity = deepseek_strict_readme_continuation`

建议预算：

- `max_metric_calls = 50`

理由：

- 当前 `valset_size = 45`
- `50` 明显高于 full valset baseline evaluation 的初始化消耗
- Stage 1 也已经显示 `50` 足以摆脱 smoke 的 baseline-only 形态

## 进入 pilot 前的最小约束

若批准 strict continuation pilot，必须同时满足：

1. 不回写 Stage 1 历史结果
2. 不修改 GEPA optimizer
3. 不修改 evaluator
4. 不运行 `official_budget`
5. pilot 结果单独命名，不写成：
   - `same-model reproduction`
   - `official reproduction completed`
   - `Stage 1 updated baseline`

## 审查结论

当前结论不是“立即运行 pilot”，而是：

> `DeepSeek strict continuation pilot readiness` 当前 **有条件通过**。

更准确地说：

- 继续被阻塞的不是技术链路
- 当前 smoke 没有展开 candidate 的原因已被充分解释
- 因此下一步**可以进入“是否批准 pilot”的决策阶段**
- 但在你单独批准之前，不应自动运行 strict continuation pilot

## 当前建议

当前最稳的下一步是：

1. 先封存这份 readiness 审查报告
2. 再由你单独决定是否批准：
   - `DeepSeek strict-readme continuation pilot`
3. 若批准，再以：
   - `max_metric_calls = 50`
   - `deepseek-v4-flash / deepseek-v4-pro`
   - `README quickstart seed prompt`
   进入 strict continuation pilot
