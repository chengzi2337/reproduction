# Stage 4C MiMo streaming GEPA sanity 结果

## 定位

- 本报告只记录 `MiMo streaming GEPA feasibility sanity`。
- 本路径不是 strict default path。
- 本路径不是 official_budget 结果。
- 本路径不是模型排名，也不是性能结论。
- 当前结论必须收窄为：
  - 已证明 `MiMo thinking.enabled + streaming bridge` 能被 GEPA 调用链跑通至少一次 seed-evaluation。
  - 尚未证明 MiMo 已进入真正的 GEPA optimization loop。

## 远端可见性

- 本地分支：`codex/stage1-revalidation-official-budget`
- 本地提交：`c1b8616`
- 2026-06-02 本地执行 `git ls-remote --heads origin codex/stage1-revalidation-official-budget` 时，远端分支头为 `350f0a4b61d1522f6bf171ae4d8199f559686b26`。
- 因此，基于当前本地证据，`c1b8616` 还不能视为“已被远端确认可见”。

## 当前最重要的两个 checkpoint

### A. 单样本 seed-evaluation sanity 通过

- run_dir：`outputs/stage4c_mimo_streaming_gepa_sanity/20260601T153232+0800`
- 环境：`WSL Ubuntu-22.04-Fresh`
- thinking：`enabled`
- mode：`streaming`
- `diagnostic_val_limit = 1`
- `max_metric_calls = 1`
- `optimize_attempted = true`
- `optimize_succeeded = true`
- `total_metric_calls = 1`
- `num_candidates = 1`
- `num_val_instances = 1`
- `num_full_val_evals = 1`
- pre/post health check：`2/2 OK`
- bridge request count：`1`
- 该唯一 task 请求：
  - `first_token_observed = true`
  - `time_to_first_token_seconds = 5.930078`
  - `time_to_complete_seconds = 818.400078`
  - `finish_reason = stop`
  - `content_nonempty = true`
  - `timeout = false`
- 输出质量：
  - 最终输出收束到 `### 384`
  - `best_score = 0.0 over 1/1`
  - 这是 reasoning failure，不是 format loss

结论：

- 该 checkpoint 有效证明：
  - MiMo `thinking.enabled + streaming bridge` 能被 GEPA task 调用链接收。
  - evaluator 能对返回内容完成打分。
- 该 checkpoint 不能证明：
  - 已进入 optimization loop
  - 已出现 reflection / mutation / candidate generation
  - 已适合扩到 45-val、smoke 或 official_budget

### B. full-val 长任务 checkpoint 失败

- run_dir：`outputs/stage4c_mimo_streaming_gepa_sanity/20260601T150603+0800`
- thinking：`enabled`
- mode：`streaming`
- `max_metric_calls = 1`
- 当前 worktree 对应的 `input_snapshot.json` 仍显示：
  - `valset_size = 45`
  - 即这次 run 不是收窄后的单样本 sanity
- pre/post health check：`2/2 OK`
- `optimize_attempted = true`
- `optimize_succeeded = false`
- `bridge_call_count = 17`
- 最终错误：
  - `error_type = MidStreamFallbackError`
  - 归因信息：`peer closed connection without sending complete message body (incomplete chunked read)`

关键信号：

- 前 16 条请求已经多次成功返回，说明基础 provider 不等于彻底不可用。
- 第 17 条请求在 `first_token_observed = true` 后中途断流，说明这是长任务下的流式稳定性问题，不是首 token blocker。
- 多条请求耗时已达到数百秒到 `1800s` 级别。

结论：

- 该 checkpoint 不能写成 “MiMo GEPA optimize 跑通失败即模型不行”。
- 它真正说明的是：
  - 当 validation 请求数扩大时，MiMo streaming path 的 latency / connection stability 风险会迅速放大。
  - 因此当前不适合直接扩到 full-val、smoke、official_budget 或更大 budget。

## 统一判读

- 现在最稳妥的总判断是：
  - `Stage 4C MiMo bridge feasibility`：通过
  - `Stage 4C MiMo seed-evaluation sanity`：通过
  - `Stage 4C MiMo optimization-loop entry`：尚未证明
  - `Stage 4C MiMo expanded validation stability`：当前失败且成本过高

- 所以不应写：
  - `MiMo GEPA passed`
  - `MiMo optimization loop passed`
  - `MiMo 适合直接进入 GEPA 扩展实验`

- 可以写：
  - `MiMo thinking.enabled + streaming bridge can complete at least one GEPA seed-evaluation`
  - `Expanded validation under the same path shows high latency and mid-stream instability`

## 下一步建议

- 下一步只建议做：
  - `Stage 4C MiMo optimization-loop entry follow-up`
  - `diagnostic_val_limit = 1`
  - `max_metric_calls = 2`
  - `thinking.enabled`
  - `streaming = true`

- 当前不建议做：
  - `diagnostic_val_limit = 45`
  - `smoke`
  - `official_budget`
  - `MiMo vs DeepSeek 排名`
  - 任意更大预算 GEPA 扩展

- 原因很直接：
  - 单样本 seed-evaluation 已经达到 `818s`
  - full-val 尝试在第 17 条流式请求出现 `MidStreamFallbackError`
  - 在尚未证明 optimization-loop entry 之前，继续扩大预算只会制造更长、更不稳定、且更难解释的 run
