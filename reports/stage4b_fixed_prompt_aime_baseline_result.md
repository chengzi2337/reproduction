# Stage 4B MiMo Pro vs GLM-4.7 fixed-prompt AIME diagnostic 结果

## 定位

- 本报告只记录 Stage 4B 的 fixed-prompt 30-sample 机制诊断。
- 它不是 GEPA。
- 它不是 `official_budget` baseline。
- 它不是 5-seed、多模型排行榜或最终性能比较。
- `official_score` 在这里沿用当前仓库 `DefaultAdapter/ContainsAnswerEvaluator` 的口径：gold 字符串被完整包含在响应中即计分。
- `relaxed_extractable_score` 只用于诊断 output protocol 与可提取性，不替代 official evaluator。

## 边界标识

- `model_called = true`
- `api_called = true`
- `new_experiment_executed = true`
- `stage4b_fixed_prompt_baseline = true`
- `diagnostic_only = true`
- `not_gepa_result = true`
- `not_official_budget_baseline = true`
- `not_final_performance_claim = true`
- `not_performance_claim = true`
- `mechanism_diagnostic_only = true`
- `no_gepa_optimize_called = true`

## 执行状态

- 当前状态：30-sample fixed-prompt diagnostic 已执行。
- split：`official test split`
- subset：`first_30_items`
- backend path：`raw_sdk`

## 阻塞结论

- Stage 4B 已执行，但当前结果不能作为模型能力比较结论。
- MiMo 本轮结果主要受 timeout 主导。
- GLM 本轮结果主要受 provider rate limit 主导。
- 因此当前不能做模型排名，也不能给出 GEPA readiness 结论。

## 分组汇总

| provider | path | prompt | completed | official | relaxed | gap | format_loss | reasoning_error | empty_or_invalid | timeout |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `glm` | `raw_sdk` | `original_seed_prompt` | 2 | 0.066666666667 | 0.066666666667 | 0.0 | 0 | 0 | 28 | 2 |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | 0 | 0.0 | 0.0 | 0.0 | 0 | 0 | 30 | 0 |
| `mimo` | `raw_sdk` | `original_seed_prompt` | 4 | 0.1 | 0.133333333333 | -0.033333333333 | 1 | 0 | 26 | 26 |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | 6 | 0.2 | 0.2 | 0.0 | 0 | 0 | 24 | 24 |

## failure-mode table

| provider | path | prompt | sample_id | error_type | finish_reason | content_nonempty | extracted_answer | official_score | relaxed_correct | diagnosis |
|---|---|---|---|---|---|---|---|---:|---|---|
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-1` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-2` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-3` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-4` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-5` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-7` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-8` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-9` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-10` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-11` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-12` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-13` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-14` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-15` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-18` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-19` | `None` | `stop` | `true` | `106` | 0.0 | `true` | `format_loss` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-20` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-21` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-22` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-23` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-24` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-25` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-26` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-27` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-28` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-29` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-30` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-2` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-5` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-7` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-8` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-9` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-10` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-11` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-12` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-13` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-14` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-15` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-18` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-19` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-20` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-21` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-22` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-23` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-24` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-25` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-26` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-27` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-28` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-29` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-30` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-2` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-4` | `APITimeoutError` | `None` | `false` | `None` | 0.0 | `false` | `timeout` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-5` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-6` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-7` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-8` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-9` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-10` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-11` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-12` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-13` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-14` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-15` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-16` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-17` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-18` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-19` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-20` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-21` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-22` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-23` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-24` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-25` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-26` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-27` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-28` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-29` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `original_seed_prompt` | `test-30` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-1` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-2` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-3` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-4` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-5` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-6` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-7` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-8` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-9` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-10` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-11` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-12` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-13` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-14` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-15` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-16` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-17` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-18` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-19` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-20` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-21` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-22` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-23` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-24` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-25` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-26` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-27` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-28` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-29` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |
| `glm` | `raw_sdk` | `strong_format_seed_prompt` | `test-30` | `RateLimitError` | `None` | `false` | `None` | 0.0 | `false` | `provider_error` |

## 代表性输出片段

| provider | path | prompt | sample_id | finish_reason | preview |
|---|---|---|---|---|---|
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-6` | `stop` | ### 504 |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-16` | `stop` | The points \(A, B, C, D, E, F\) lie on a line in that order. Setting \(A = 0\) on the x-axis, the coordinates are \(A(0)\), \(B(18)\), \(C(26)\), \(D(40)\), \(E(57)\), \(F(73)\). The point \(G\) is off the line with distances \(CG = 40\)... |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-17` | `stop` | The sum of all positive integers \(n\) satisfying the condition is \(49\). ### 49 |
| `mimo` | `raw_sdk` | `original_seed_prompt` | `test-19` | `stop` | Looking at this problem, I need to compute a large telescoping product involving logarithms. ## Setting Up the General Term The general term for $k = 4, 5, \ldots, 63$ is: $$\frac{\log_k(5^{k^2-1})}{\log_{k+1}(5^{k^2-4})}$$ **Converting ... |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-1` | `stop` | ### 70 |
| `mimo` | `raw_sdk` | `strong_format_seed_prompt` | `test-3` | `stop` | Looking at this problem, I need to count assignments of 9 players to chocolate (C), vanilla (V), and strawberry (S) where $c > v > s \geq 1$ and $c + v + s = 9$. ## Finding Valid Triples (c, v, s) **Setting up constraints:** Since $s \ge... |

## 结论边界

- 可以写：某模型在当前 30-sample fixed-prompt diagnostic 中输出更稳定。
- 可以写：某模型的 `format_loss` 更少。
- 可以写：某模型的 `relaxed_extractable_score` 更高。
- 可以写：`strong_format_seed_prompt` 对某模型的 `official_score` 更敏感。
- 不能写：MiMo Pro 综合强于 GLM-4.7。
- 不能写：GLM-4.7 综合强于 MiMo Pro。
- 不能写：谁的数学能力更强。
- 不能写：谁更适合 `official_budget` 或已经完成 GEPA 复现。
