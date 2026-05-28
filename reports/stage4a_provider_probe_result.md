# Stage 4A MiMo Pro vs GLM-4.7 provider probe 结果

## 定位

- 本报告只记录 Stage 4A provider probe 的连通性与最小生成诊断。
- 它不是 GEPA 实验。
- 它不是 official_budget continuation。
- 它不是 5-seed、多样本性能对比或模型排行榜。
- 结论只允许停留在 reachable / content returned / timeout / path consistency 这些层级。

## 边界标识

- `model_called = true`
- `api_called = true`
- `new_experiment_executed = true`
- `stage4a_provider_probe = true`
- `diagnostic_only = true`
- `not_gepa_result = true`
- `not_performance_claim = true`
- `no_gepa_optimize_called = true`
- `not_official_budget_baseline = true`
- `mechanism_diagnostic_only = true`

## 执行状态

- 当前状态：execute 已执行。
- 本报告只汇总最小 probe，不做数学能力结论。

## provider / path 汇总

| provider | path | reachable | key | model | content | timeout |
|---|---|---|---|---|---|---|
| `glm` | `litellm` | `reachable` | `valid` | `supported` | `returned` | `no timeout` |
| `glm` | `raw_sdk` | `reachable` | `valid` | `supported` | `returned` | `no timeout` |
| `mimo` | `litellm` | `reachable` | `valid` | `supported` | `returned` | `no timeout` |
| `mimo` | `raw_sdk` | `reachable` | `valid` | `supported` | `returned` | `no timeout` |

## 逐条 probe 摘要

| provider | path | probe | status | finish_reason | content_preview |
|---|---|---|---|---|---|
| `mimo` | `raw_sdk` | `simple_ok` | `ok` | `stop` | OK |
| `mimo` | `raw_sdk` | `short_math` | `ok` | `stop` | 42 |
| `mimo` | `raw_sdk` | `strong_format_micro` | `ok` | `stop` | ### 42 |
| `mimo` | `litellm` | `simple_ok` | `ok` | `stop` | OK |
| `mimo` | `litellm` | `short_math` | `ok` | `stop` | 42 |
| `mimo` | `litellm` | `strong_format_micro` | `ok` | `stop` | ### 42 |
| `glm` | `raw_sdk` | `simple_ok` | `ok` | `stop` | OK |
| `glm` | `raw_sdk` | `short_math` | `ok` | `stop` | 42 |
| `glm` | `raw_sdk` | `strong_format_micro` | `ok` | `stop` | ### 42 |
| `glm` | `litellm` | `simple_ok` | `ok` | `stop` | OK |
| `glm` | `litellm` | `short_math` | `ok` | `stop` | 42 |
| `glm` | `litellm` | `strong_format_micro` | `ok` | `stop` | ### 42 |

## raw SDK vs LiteLLM 一致性

- `glm`：一致（all_checked）
- `mimo`：一致（all_checked）

## 结论边界

- 可以写：provider reachable / not reachable。
- 可以写：key valid / invalid / unknown。
- 可以写：model supported / unsupported / unknown。
- 可以写：content returned / empty。
- 可以写：timeout / no timeout。
- 可以写：raw SDK 与 LiteLLM 是否一致。
- 不能写：MiMo 比 GLM 强。
- 不能写：GLM 比 MiMo 强。
- 不能写：可以直接进入 GEPA official_budget。
- 不能写：数学能力已经得到结论。
