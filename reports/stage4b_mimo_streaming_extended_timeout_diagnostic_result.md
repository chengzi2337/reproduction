# Stage 4B MiMo streaming extended-timeout diagnostic 结果

## 定位

- 本报告只记录 MiMo 的 streaming extended-timeout diagnostic。
- 它不是 strict non-streaming path 结果。
- 它不是 strict 60s comparison。
- 它不是 GEPA 结果。
- 它不是 official_budget 结果。
- 它不是 MiMo vs GLM 排名。
- 所有真实调用都只允许解释为 diagnostic，不允许写成 performance claim。

## 边界标识

- `model_called = true`
- `api_called = true`
- `new_experiment_executed = true`
- `streaming_path_only = true`
- `extended_timeout_diagnostic = true`
- `not_strict_non_streaming_path = true`
- `not_strict_60s_comparison = true`
- `not_gepa_result = true`
- `not_official_budget = true`
- `not_model_ranking = true`
- `not_performance_claim = true`
- `diagnostic_only = true`

## 请求计划

- provider：`mimo`
- backend path：`raw_sdk`
- mode：`streaming`
- prompt variant：`l4_strong_format`
- sample ids：`test-1, test-2, test-3, test-4, test-5`
- application_wall_clock_timeout_seconds：`600.0`
- sdk_timeout_seconds：`600.0`
- sleep_between_requests：`60.0` 秒
- max_retries：`0`
- concurrency：`1`
- split：`official test split`

## 配置状态

- model：`mimo-v2.5-pro`
- api_key_env：`MIMO_API_KEY`
- api_base_present：`true`
- model_present：`true`
- missing_config_reasons：`none`

## 执行状态

- 当前状态：execute 已执行。
- health check 已在 streaming 批次前后执行。

## health check 汇总

- check_count：`2`
- ok_count：`2`
- error_count：`0`
- avg_latency_seconds：`12.824456`

## 汇总指标

- completed_count：`5`
- timeout_count：`0`
- application_wall_clock_timeout_count：`0`
- provider_error_count：`0`
- rate_limit_count：`0`
- official_score：`0.6`
- relaxed_extractable_score：`1.0`
- format_loss_count：`2`
- reasoning_error_count：`0`
- empty_or_invalid_count：`0`
- first_token_observed_count：`5`
- content_nonempty_count：`5`
- avg_time_to_first_token_seconds：`6.133168`
- max_time_to_first_token_seconds：`9.80992`
- avg_time_to_complete_seconds：`183.833975`
- max_time_to_complete_seconds：`552.700416`
- finish_reason_distribution：`{"stop": 5}`

## 单样本摘要

| sample_id | completed | timeout | app_wc_timeout | first_token | ttft | complete_time | official | relaxed | format_loss | reasoning_error | empty_or_invalid | finish_reason | error_type |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| `test-1` | 1 | 0 | 0 | 1 | 9.80992 | 64.474096 | 1.0 | 1 | 0 | 0 | 0 | `stop` | `None` |
| `test-2` | 1 | 0 | 0 | 1 | 4.208814 | 552.700416 | 1.0 | 1 | 0 | 0 | 0 | `stop` | `None` |
| `test-3` | 1 | 0 | 0 | 1 | 6.65666 | 41.141744 | 0.0 | 1 | 1 | 0 | 0 | `stop` | `None` |
| `test-4` | 1 | 0 | 0 | 1 | 5.3607 | 112.064912 | 1.0 | 1 | 0 | 0 | 0 | `stop` | `None` |
| `test-5` | 1 | 0 | 0 | 1 | 4.629745 | 148.788708 | 0.0 | 1 | 1 | 0 | 0 | `stop` | `None` |

## failure cases

| sample_id | timeout | enforced_by | first_token | partial_content | finish_reason | diagnosis_hint | preview |
|---|---|---|---|---|---|---|---|
| `test-3` | `false` | `None` | `true` | `false` | `stop` | `format_loss` | 16 |
| `test-5` | `false` | `None` | `true` | `false` | `stop` | `format_loss` | Looking at this problem, I need to count permutations of digits 1-8 that form numbers divisible by 22 (divisible by both 2 and 11). ## Setting Up the Divisibility Conditions **Divisibility by 2:** The last digit (position 8) must be even... |

## 结果判读

### 1. streaming extended-timeout 路径可以完成真实 AIME 样本

- `5/5` 样本全部完成。
- `timeout_count = 0`。
- `application_wall_clock_timeout_count = 0`。
- `provider_error_count = 0`。
- `rate_limit_count = 0`。
- `first_token_observed_count = 5`。

这说明在本轮 `L4 + streaming + 600s wall-clock + 600s sdk timeout` 条件下，MiMo 可以稳定拿到首 token，并最终完成 5 个真实 AIME 样本。

### 2. 但输出协议还不够稳定

- `official_score = 0.6`
- `relaxed_extractable_score = 1.0`
- `format_loss_count = 2`
- `reasoning_error_count = 0`
- `empty_or_invalid_count = 0`

这说明本轮主要剩余问题不是 reasoning failure，而是 output protocol adherence 仍不稳定。

具体表现：

- `test-3` 返回 `16`，relaxed 可抽取正确答案，但没有满足 strict `### 16`。
- `test-5` 返回了可抽取为 `279` 的长文本，但最终没有满足 strict `### 279`。

因此当前可以写成：

- streaming extended-timeout 路径在 5-sample 上没有出现 reasoning_error。
- 但 `L4 strong_format_seed_prompt` 仍未把协议稳定性拉到 `format_loss = 0`。

不能写成：

- official score 低就代表 reasoning 失败。

### 3. 墙钟延迟仍然很高

- `avg_time_to_first_token_seconds = 6.133168`
- `max_time_to_first_token_seconds = 9.80992`
- `avg_time_to_complete_seconds = 183.833975`
- `max_time_to_complete_seconds = 552.700416`

最关键的 latency 风险是：

- `test-2` 虽然完成，但单样本真实墙钟达到 `552.700416s`，已经非常接近本轮 `600s` application wall-clock guard。

这说明：

- MiMo streaming 路径可以完成；
- 但成本和时延都很高；
- 即使本轮没有触发 wall-clock guard，也不能把它视为低风险路径。

### 4. 本轮未观察到 SDK timeout 与 wall-clock guard 冲突

- 本轮 `finish_reason_distribution = {"stop": 5}`。
- 没有样本触发 `ApplicationWallClockTimeout`。
- 也没有样本触发 SDK/provider timeout。

因此本轮没有观察到 SDK timeout 与 application wall-clock guard 的冲突行为；但 guard 仍然是必要的，因为最长样本已经接近上限。

## 当前判断

1. MiMo 的 streaming extended-timeout 路径在 5-sample 上具备“可完成”证据。
2. 这条证据只适用于 `streaming_path_only`，不能外推到 strict non-streaming path。
3. 当前主要剩余问题是 `format_loss` 和高 latency，不是 provider 基础故障，也不是显式 reasoning_error。
4. 当前状态仍然不适合进入 `GEPA`。

## 是否建议扩到 30-sample

- 当前**不建议直接扩到 30-sample official-style diagnostic**。

理由有两个：

1. `format_loss_count = 2 / 5`，说明 L4 协议稳定性还不够。
2. `max_time_to_complete_seconds = 552.700416`，说明单样本时延已经接近 `600s` guard，扩到 30-sample 的时间和成本风险过高。

如果后续还要继续 MiMo，更稳的下一步不是直接扩到 `30-sample`，而是先做一条单独的：

- `MiMo controlled-generation streaming diagnostic`

例如再比较：

- `thinking.disabled`
- `max_completion_tokens`

但这必须继续明确标记为：

- `controlled_generation_diagnostic = true`
- `not_strict_default_path = true`
- `not_gepa_result = true`

## 结论边界

- 可以写：MiMo 在 streaming extended-timeout 条件下是否能完成 fixed-prompt diagnostic。
- 可以写：L4 是否改善协议遵循、是否仍有 format_loss、reasoning_error、empty_or_invalid。
- 可以写：是否触发 application wall-clock guard，以及 SDK timeout 与 wall-clock 行为是否一致。
- 不可以写：MiMo strict path passed。
- 不可以写：MiMo 可以替代 DeepSeek。
- 不可以写：MiMo 数学能力更强。
- 不可以写：MiMo 已经适合 GEPA。
- 不可以写：MiMo 与 GLM 的性能比较。
