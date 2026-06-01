# Stage 4C GLM streaming GEPA sanity 结果

## 定位

- 本报告只记录 GLM streaming GEPA micro-sanity paired diagnostic。
- 它不是 official_budget。
- 它不是模型排名。
- 它不是 strict default path 对比。
- 它不是最终性能结论。

## 边界标记

- `model_called = true`
- `api_called = true`
- `new_experiment_executed = true`
- `stage4c_glm_streaming_gepa_sanity = true`
- `diagnostic_only = true`
- `not_official_budget = true`
- `not_performance_claim = true`
- `not_model_ranking = true`
- `not_strict_default_path = true`
- `streaming_path_only = true`
- `glm_backend = true`
- `paired_thinking_diagnostic = true`

## 配置

- provider：`glm`
- model：`glm-4.7`
- api_base_present：`true`
- thinking_types：`default, disabled`
- seed_prompt：`strong_format`
- max_metric_calls：`1`
- diagnostic_val_limit：`3`
- sleep_between_requests：`120.0`

## 执行状态

- 当前状态：真实 paired diagnostic 已执行。
- completed_arms：`default, disabled`
- blocked_arms：`none`

## Arm 汇总

| thinking_type | status | optimize_called | optimize_completed | health_before | health_after | total_metric_calls | request_count | timeout_count | avg_first_token | max_first_token |
|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|
| `default` | `ok` | 1 | 1 | `ok` | `ok` | 3 | 3 | 0 | 1.560432 | 1.755298 |
| `disabled` | `ok` | 1 | 1 | `ok` | `ok` | 3 | 3 | 0 | 1.442285 | 1.608004 |

## 结论边界

- 可以写：default / disabled thinking 两个 arm 是否跑通、health check 是否正常、请求级 timeout 类型与首 token 延迟特征。
- 不能写：GLM 比 MiMo 强，或 GLM 已适合 official_budget / GEPA 正式复现。
