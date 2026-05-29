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
- `controlled_generation_diagnostic = true`
- `not_strict_default_path = true`

## 请求计划

- provider：`mimo`
- backend path：`raw_sdk`
- mode：`streaming`
- prompt variant：`l4_strong_format`
- thinking_type：`disabled`
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
- avg_latency_seconds：`10.561415`

## 汇总指标

- completed_count：`4`
- timeout_count：`1`
- application_wall_clock_timeout_count：`1`
- provider_error_count：`0`
- rate_limit_count：`0`
- official_score：`0.6`
- relaxed_extractable_score：`0.6`
- format_loss_count：`0`
- reasoning_error_count：`1`
- empty_or_invalid_count：`1`
- first_token_observed_count：`5`
- content_nonempty_count：`5`
- avg_time_to_first_token_seconds：`6.106435`
- max_time_to_first_token_seconds：`9.275237`
- avg_time_to_complete_seconds：`140.709667`
- max_time_to_complete_seconds：`600.226244`
- finish_reason_distribution：`{"stop": 4, "null": 1}`

## 单样本摘要

| sample_id | completed | timeout | app_wc_timeout | first_token | ttft | complete_time | official | relaxed | format_loss | reasoning_error | empty_or_invalid | finish_reason | error_type |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| `test-1` | 1 | 0 | 0 | 1 | 9.275237 | 28.276694 | 1.0 | 1 | 0 | 0 | 0 | `stop` | `None` |
| `test-2` | 0 | 1 | 1 | 1 | 4.580406 | 600.226244 | 0.0 | 0 | 0 | 0 | 1 | `None` | `ApplicationWallClockTimeout` |
| `test-3` | 1 | 0 | 0 | 1 | 6.6499 | 25.800452 | 1.0 | 1 | 0 | 0 | 0 | `stop` | `None` |
| `test-4` | 1 | 0 | 0 | 1 | 4.105329 | 4.333117 | 0.0 | 0 | 0 | 1 | 0 | `stop` | `None` |
| `test-5` | 1 | 0 | 0 | 1 | 5.921304 | 44.911826 | 1.0 | 1 | 0 | 0 | 0 | `stop` | `None` |

## failure cases

| sample_id | timeout | enforced_by | first_token | partial_content | finish_reason | diagnosis_hint | preview |
|---|---|---|---|---|---|---|---|
| `test-2` | `true` | `application_wall_clock` | `true` | `true` | `None` | `empty_or_invalid` | Let $A$ be the origin $(0,0)$. The points $A, D, E, B$ lie on side $AB$ in that order. $AD = 4$, $DE = 16$, $EB = 8$. Thus, $AB = AD + DE + EB = 4 + 16 + 8 = 28$. The points $A, F, G, C$ lie on side $AC$ in that order. $AF = 13$, $FG = 5... |
| `test-4` | `false` | `None` | `true` | `false` | `stop` | `reasoning_error` | ### 11 |

## 结论边界

- 可以写：MiMo 在 streaming extended-timeout 条件下是否能完成 fixed-prompt diagnostic。
- 可以写：L4 是否改善协议遵循、是否仍有 format_loss、reasoning_error、empty_or_invalid。
- 可以写：是否触发 application wall-clock guard，以及 SDK timeout 与 wall-clock 行为是否一致。
- 不可以写：MiMo strict path passed。
- 不可以写：MiMo 可以替代 DeepSeek。
- 不可以写：MiMo 数学能力更强。
- 不可以写：MiMo 已经适合 GEPA。
- 不可以写：MiMo 与 GLM 的性能比较。
