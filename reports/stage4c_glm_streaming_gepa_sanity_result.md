# Stage 4C GLM streaming GEPA sanity 结果

## 定位

- 本报告只记录 GLM streaming GEPA sanity。
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
- `paired_thinking_diagnostic = false`
- `single_thinking_diagnostic = true`

## 配置

- provider：`glm`
- model：`glm-4.7`
- api_base_present：`true`
- execution_mode：`single`
- thinking_types：`disabled`
- seed_prompt：`strong_format`
- max_metric_calls：`6`
- diagnostic_val_limit：`3`
- seed_full_eval_metric_calls：`3`
- effective_min_metric_calls：`4`
- requested_scope_label：`optimization-entry sanity`
- sleep_between_requests：`120.0`

## 语义说明

- 任何 `max_metric_calls < 4` 的 Stage 4C run，都只能解释为 `seed-evaluation sanity`。
- 当前配置下，seed full evaluation 本身会先消耗 `valset_size_used = 3` 个 metric calls。
- 当前 `max_metric_calls` 是循环边界 stop condition，不是单 iteration 内部的严格硬上限；因此本次虽然请求的是 `6`，实际 `total_metric_calls` 仍到达了 `9`。
- 因此，先前 `max_metric_calls = 1` 的 paired run 只能降格解释为 seed-evaluation sanity，不能当作 optimization-loop 结果。

## 执行状态

- 当前状态：真实 `single` sanity 已执行。
- completed_arms：`disabled`
- blocked_arms：`none`

## Arm 汇总

| thinking_type | status | optimize_called | optimize_completed | optimization_loop_entered | iterations_started | effective_min_metric_calls | total_metric_calls | health_before | health_after | request_count | timeout_count | avg_first_token | max_first_token |
|---|---|---:|---:|---|---:|---:|---:|---|---|---:|---:|---:|---:|
| `disabled` | `ok` | 1 | 1 | `true` | 1 | 4 | 9 | `ok` | `ok` | 10 | 0 | 12.075197 | 73.852058 |

## 结论边界

- 可以写：当前预算下是否进入 optimization loop、health check 是否正常、请求级 timeout 类型与首 token 延迟特征。
- 可以写：如果 `optimization_loop_entered = false`，该 run 只构成 seed-evaluation sanity。
- 不能写：GLM 比 MiMo 强，或 GLM 已适合 official_budget / GEPA 正式复现。
