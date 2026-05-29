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

- `model_called = false`
- `api_called = false`
- `new_experiment_executed = false`
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

- model：`<missing>`
- api_key_env：`MIMO_API_KEY`
- api_base_present：`false`
- model_present：`false`
- missing_config_reasons：`missing api_base, missing credential env: MIMO_API_KEY, missing model`

## 执行状态

- 当前状态：dry-run，未调用模型，未调用 API，未运行新实验。
- 本次报告只验证脚手架、streaming-only 边界、wall-clock guard schema 和结果报告骨架。
- health check：未执行；脚本已预留 pre / post streaming health check 路径。

## 计划覆盖

- planned_request_count：`5`
- planned_health_check_count：`2`
- 真实执行时必须先比较 pre/post health check，再解释 AIME 失败归因。

## 待执行判读框架

1. 如果 health check 失败，而 AIME 也失败，应优先归因为 provider / endpoint / key / 网络问题。
2. 如果 health check 正常，但 AIME streaming 超时，应继续区分首 token 前超时、生成中途超时、partial content、finish_reason、reasoning_only_output。
3. 如果 5/5 completed 且 format_loss=0，可以建议扩到 streaming extended-timeout 30-sample diagnostic。
4. 即使全部完成，也不能写成 strict non-streaming path 已成功。
