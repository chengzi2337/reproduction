# Project Current State and Decision

## 当前总判断

当前项目应分成两条清晰轨道理解：

- `Stage 1 / DeepSeek`：当前主复现实验轨道
- `Stage 2 / MiMo`：当前已完成诊断收束的 backend-substitution 轨道

当前决策不是继续扩大 MiMo 实验，而是：

> 暂停 MiMo experimental expansion，并回到 DeepSeek strict-readme continuation 主线。

## 为什么暂停 MiMo

### Stage 2A

- 已证明 MiMo strict default generation 在真实 AIME prompt 下会触发 `HardTimeout`

### Stage 2B

- 已证明 MiMo controlled-generation 单样本可以返回非空 `content`

### Stage 2C

- 已证明 MiMo controlled-generation GEPA `sanity / smoke` 可以执行闭环
- 但 Stage 2C smoke 的 `best_score = 0.0`
- failure-mode audit 已确认主要问题是：
  - `format_missing`
  - `output_protocol_violation`

### Stage 2D

- 已确认 GEPA AIME official evaluator 的契约是：
  - ground truth 形如 `### 72`
  - evaluator 实际是 `data["answer"] in response`
- 已完成 prompt-only official-contract adaptation diagnostic
- 结果是：
  - 没有任何 prompt variant 同时满足 direct SDK 与 LiteLLM 的稳定 official-contract 通过门槛

因此当前最稳的结论是：

- `MiMo Stage 2D Phase 2 did not meet the entry gate for adapted GEPA smoke`
- `Prompt-only official-contract adaptation is not stable enough`

## 当前不做的事

- 不进入 MiMo pilot
- 不运行 MiMo adapted GEPA smoke
- 不继续扩大 MiMo prompt-only 实验
- 不运行 `official_budget`
- 不重跑 Stage 1 wrapper baseline

## 当前主线

当前主线应回到：

- `DeepSeek strict-readme continuation`

这条主线的边界是：

- 仍然是 `GEPA method-level reproduction with DeepSeek backend`
- 不是 `same-model reproduction`
- 不是 Stage 1 历史结论改写
- 不是 `official_budget`

## DeepSeek 当前状态

DeepSeek strict-readme continuation 已经具备：

- 独立计划书：
  - [deepseek_continuation_experiment_plan.md](C:/Users/lin/Documents/New%20project%202/reports/deepseek_continuation_experiment_plan.md)
- 独立 smoke runner：
  - [deepseek_run_strict_continuation_smoke.py](C:/Users/lin/Documents/New%20project%202/scripts/deepseek_run_strict_continuation_smoke.py)
- 已完成的 strict continuation smoke checkpoint：
  - [deepseek_strict_continuation_smoke_result.md](C:/Users/lin/Documents/New%20project%202/reports/deepseek_strict_continuation_smoke_result.md)
  - [deepseek_strict_continuation_smoke_candidate_expansion_audit.md](C:/Users/lin/Documents/New%20project%202/reports/deepseek_strict_continuation_smoke_candidate_expansion_audit.md)

## 下一步

当前最合理的下一步不是“重新启动 DeepSeek smoke”，因为这一步已经完成。

当前最合理的下一步是：

1. 保持 MiMo 暂停扩张的状态
2. 基于已完成的 DeepSeek strict continuation smoke，评估是否满足进入 pilot 的前置条件
3. 如需继续，先做 `DeepSeek strict continuation pilot readiness` 设计或审查
4. 审查通过后，再单独决定是否批准 strict continuation pilot

## DeepSeek strict continuation pilot 最新状态

`DeepSeek strict continuation pilot` 已经被单独批准并真实运行一次。

当前结果不是“pilot 未开始”，而是：

- baseline full valset evaluation 已完成
- `Iteration 1` 已开始
- 运行在第一次 reflective proposal 阶段失败

已封存的结果与审计应理解为：

- `DeepSeek strict continuation pilot started`
- 但 `execution_completed = false`
- 当前 blocker 不是 smoke 阶段的预算语义问题
- 当前 blocker 位于：
  - provider / LiteLLM 并发 completion 异常对象
  - `DefaultAdapter` 的未防护 `resp.choices` 访问

因此当前不应：

- 直接重跑 pilot
- 直接进入 `official_budget`

当前更合理的下一步是：

1. 先封存 pilot result checkpoint
2. 先封存只读调用链审计
3. 再决定是否进入新的 provider-error handling 诊断阶段
