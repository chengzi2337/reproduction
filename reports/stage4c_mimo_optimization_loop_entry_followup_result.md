# Stage 4C MiMo optimization-loop entry follow-up 结果

## 定位

- 本报告只记录 `MiMo thinking.enabled + streaming` 在 `GEPA Stage 4C` 下的最小 follow-up。
- 本轮配置固定为：
  - `diagnostic_val_limit = 1`
  - `max_metric_calls = 2`
  - `thinking.enabled`
  - `streaming = true`
- 本报告不是 strict path 结果。
- 本报告不是 official_budget 结果。
- 本报告不是模型排名，也不是性能结论。

## run 标识

- 分支：`codex/stage1-revalidation-official-budget`
- 执行环境：`WSL Ubuntu-22.04-Fresh`
- run_dir：`outputs/stage4c_mimo_optimization_loop_entry_followup/20260602T214115+0800`
- report_path：`reports/stage4c_mimo_optimization_loop_entry_followup_result.md`

## 输入边界

- provider：`mimo`
- model：`mimo-v2.5-pro`
- task_lm：`openai/mimo-v2.5-pro`
- reflection_lm：`openai/mimo-v2.5-pro`
- thinking：`enabled`
- mode：`streaming`
- first_token_timeout_seconds：`1800`
- sdk_timeout_seconds：`1800`
- emergency_after_first_token_seconds：`null`
- diagnostic_val_limit：`1`
- max_metric_calls：`2`
- effective_min_metric_calls：`2`
- requested_budget_reaches_loop_entry：`true`
- stage4c_scope：`optimization_loop_entry_followup`

## health check

- pre/post health check：`2/2 OK`
- avg_latency_seconds：`4.458028`
- 因此本轮不是 provider / key / endpoint 基础不可用问题。

## GEPA 结果摘要

- optimize_attempted：`true`
- optimize_succeeded：`true`
- total_metric_calls：`8`
- num_candidates：`2`
- num_val_instances：`1`
- num_full_val_evals：`2`
- best_idx：`0`
- best_score：`0.0`

## loop-entry 证据

本轮已经超过“仅做一次 seed-evaluation”的范围，证据如下：

- `total_metric_calls = 8`，明显大于 `effective_min_metric_calls = 2`。
- `num_candidates = 2`，已经出现非 seed candidate。
- `bridge_call_records.jsonl` 中出现了 `reflection_completion`：
  - 记录编号：第 `5` 条 bridge 调用
  - `time_to_complete_seconds = 61.635989`
  - `raw_response_length_chars = 2490`
- GEPA 终端日志明确出现：
  - `Iteration 1: Proposed new text for system_prompt`
  - `Iteration 1: New subsample score 3.0 is better than old score 2.0`
  - `Iteration 1: Valset score for new program: 0.0`
  - `Iteration 1: New program candidate index: 1`

因此本轮可以收窄写成：

- `MiMo streaming GEPA optimization-loop entry passed`

但仍然不能写成：

- `MiMo GEPA fully passed`
- `MiMo 适合 full-val / smoke / official_budget`

## bridge 调用分解

- bridge_call_count：`9`
- task_batch_completion：`8`
- reflection_completion：`1`
- avg_time_to_first_token_seconds：`5.030004`
- max_time_to_first_token_seconds：`6.388055`
- avg_time_to_complete_seconds：`543.506972`
- max_time_to_complete_seconds：`1804.531897`

### 调用结构解释

结合 `bridge_call_records.jsonl` 与 raw responses，可将 9 条调用粗分为：

1. 第 `1` 条：seed program 的 held-out valset 评估
2. 第 `2-4` 条：旧 prompt 在 subsample/train task 上的评估
3. 第 `5` 条：reflection / mutation 生成新 prompt
4. 第 `6-8` 条：新 prompt 在 subsample/train task 上的评估
5. 第 `9` 条：新 prompt 的 held-out valset 评估

这说明当前路径并不是“只多跑了一次 metric call”，而是已经真实进入了候选生成与再次评估闭环。

## 最重要的异常：held-out val 样本两次都退化为 reasoning-only output

最关键的 blocker 不在于 health check，也不在于首 token：

- 第 `1` 条 bridge 调用：
  - `first_token_observed = true`
  - `time_to_first_token_seconds = 3.8569`
  - `time_to_complete_seconds = 1803.614217`
  - `finish_reason = stop`
  - `content_nonempty = false`
  - raw payload 中 `reasoning_text` 很长，但 `content = ""`
- 第 `9` 条 bridge 调用：
  - `first_token_observed = true`
  - `time_to_first_token_seconds = 5.066086`
  - `time_to_complete_seconds = 1804.531897`
  - `finish_reason = stop`
  - `content_nonempty = false`
  - raw payload 中 `reasoning_text` 很长，但 `content = ""`

这两个调用都不是首 token timeout，也不是 mid-stream fallback：

- 都拿到了首 token
- 都自然结束到 `finish_reason = stop`
- 但 visible `content` 为空，只有长 reasoning

因此这轮 follow-up 最准确的失效模式是：

- `held-out val sample repeatedly produced reasoning-only output, so GEPA evaluator received empty visible content`

这不能直接写成“MiMo 数学能力差”，也不能简单写成“bridge 坏了”。

## subsample / candidate 质量信号

在非 held-out 的 subsample task 上，MiMo 并不是完全失效：

- 旧 prompt 的若干 task 输出：
  - `### 585`
  - `\boxed{601}`（这是 format-loss，不是 reasoning failure）
  - `### 227`
- 新 prompt 的若干 task 输出：
  - `### 585`
  - `### 601`
  - 一个更长的 base-9/base-10 推导

GEPA 自身日志也显示：

- `New subsample score 3.0 is better than old score 2.0`

这说明：

- candidate generation 并非空转
- 新 prompt 在 subsample 上确实拿到了更高分
- 但这种改善没有传导到 held-out val 样本，因为 val 样本两次都卡在 reasoning-only output

## 为什么 best_score 仍是 0.0

`best_score = 0.0 over 1/1` 的直接原因不是“没有进入 loop”，而是：

- held-out val 样本的 seed program 评估为空内容
- held-out val 样本的新 candidate 评估也为空内容
- `generated_best_outputs_valset/task_0/iter_0_prog_0.json` 中只留下：
  - `"full_assistant_response": ""`

所以当前更准确的说法是：

- `optimization-loop entry` 已经被证明
- 但 `held-out val scoring` 仍被 reasoning-only / empty visible content 阻塞

## 统一判读

本轮最合理的结论是：

- `Stage 4C MiMo bridge feasibility`：通过
- `Stage 4C MiMo seed-evaluation sanity`：此前已通过
- `Stage 4C MiMo optimization-loop entry`：本轮通过
- `Stage 4C MiMo held-out val stability`：当前仍被 reasoning-only empty-content failure 阻塞
- `Stage 4C MiMo expansion readiness`：不通过

## 是否建议继续扩展

当前不建议继续扩到：

- `diagnostic_val_limit = 45`
- `smoke`
- `official_budget`

原因很直接：

- 两次 held-out val 调用都耗时约 `1804s`
- 且两次都以 `finish_reason = stop` + `content_nonempty = false` 结束
- 单轮 follow-up 总墙钟已超过 `80` 分钟

所以即使 loop entry 已经证明，当前路径的 latency 与 visible-output stability 仍然过差，不适合继续放大。

## 下一步建议

下一步不建议继续扩大 GEPA budget。更合理的是先做一条更小的 MiMo diagnostic，只回答：

1. 为什么 held-out val 样本会在 Stage 4C prompt 下稳定产生 reasoning-only output
2. 这种现象是否只集中在该 val 样本
3. 是否能通过更强的 final-answer protocol 约束减少 visible content 为空的问题
4. 如果只能依赖 reasoning channel 才能收束，当前 GEPA evaluator 路径是否天然不适配 MiMo strict visible-answer scoring

在这些问题澄清前，不建议继续 MiMo GEPA 扩展。
