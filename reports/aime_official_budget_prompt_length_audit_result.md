# AIME official_budget prompt length 只读审计结果

## 文档定位

- 本报告基于 5 个既有 `official_budget` run_dir 做只读 prompt length audit。
- 本报告不调用模型、不调用 GEPA、不运行新实验。
- 本报告不是 `Length-Controlled GEPA` 实验结果。
- 本报告不构成新的性能结论，也不支持“prompt 越长越好”。

## 审计边界标志

- `not_new_experiment = true`
- `no_model_called = true`
- `no_api_called = true`
- `no_gepa_optimize_called = true`
- `not_performance_claim = true`
- `token_estimate_for_audit_only = true`
- `not_exact_tokenizer_count = true`

## 主表

| seed | run_dir | seed_test_score | optimized_test_score | delta | best_val_score | seed_chars | optimized_chars | char_growth | growth_ratio | seed_lines | optimized_lines | seed_words | optimized_words | num_candidates | num_full_val_evals |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | `outputs/gepa_aime_official_budget_seed0/20260522T121001+0800` | 0.2 | 0.6333333333333333 | 0.4333333333333333 | 0.8444444444444444 | 100 | 2917 | 2817 | 29.17 | 1 | 23 | 17 | 444 | 3 | 3 |
| 1 | `outputs/gepa_aime_official_budget_seed1/20260522T175103+0800` | 0.16666666666666666 | 0.6666666666666666 | 0.5 | 0.9111111111111111 | 100 | 1144 | 1044 | 11.44 | 1 | 12 | 17 | 195 | 3 | 3 |
| 2 | `outputs/gepa_aime_official_budget_seed2/20260522T221654+0800` | 0.22666666666666666 | 0.9266666666666666 | 0.7 | 0.6888888888888889 | 100 | 940 | 840 | 9.4 | 1 | 26 | 17 | 166 | 3 | 3 |
| 3 | `outputs/gepa_aime_official_budget_seed3/20260525T104154+0800` | 0.25333333333333335 | 0.7266666666666667 | 0.47333333333333333 | 0.8444444444444444 | 100 | 1041 | 941 | 10.41 | 1 | 13 | 17 | 174 | 3 | 3 |
| 4 | `outputs/gepa_aime_official_budget_seed4/20260525T135207+0800` | 0.17333333333333334 | 0.66 | 0.4866666666666667 | 0.9333333333333333 | 100 | 1319 | 1219 | 13.19 | 1 | 16 | 17 | 228 | 3 | 3 |

## token 粗估说明

- `seed_prompt_tokens_est` 与 `optimized_prompt_tokens_est` 仅使用 `chars / 4` 粗略估算。
- 该估算只用于审计辅助观察，不是 tokenizer 精确计数，不用于严格成本结论。

## 问题回答

### 1. optimized prompt 是否显著长于 seed prompt

是。5 个 seed 全部满足 `optimized_prompt_chars > seed_prompt_chars`，字符增长范围为 `840` 到 `2817`，平均增长 `1372.2` 个字符。

### 2. prompt 长度增长是否与 optimized_test_score 单调对应

否。按 `prompt_char_growth` 从小到大排序后，`optimized_test_score`（即 artifact 中的 `optimized_prompt_score`）不单调递增：`optimized_score_monotonic_with_length_growth = false`。

### 3. prompt 长度增长是否与 score_delta 单调对应

否。按 `prompt_char_growth` 从小到大排序后，`score_delta` 不单调递增：`score_delta_monotonic_with_length_growth = false`。

### 4. 是否存在最长 prompt 不是最高分、最短 optimized prompt 反而最高分

存在。最长 optimized prompt 来自 seed0，其 optimized score 为 `0.6333333333333333`；最高 optimized score 来自 seed2，分数为 `0.9266666666666666`。

也存在最短 optimized prompt 反而最高分的现象：`shortest_optimized_prompt_is_highest_score = true`。最短 optimized prompt 来自 seed2，其 optimized score 为 `0.9266666666666666`。

### 5. 是否支持下一步设计 Length-Controlled GEPA

支持进入设计阶段。当前 audit 显示 prompt length growth substantial，但长度增长不能单调解释测试收益，因此 prompt 长度是合理的下一步审计和控制变量。

### 6. 当前是否只是只读 audit

是。当前结果只来自已有 run_dir 的 artifact 读取与统计，不是 `Length-Controlled GEPA` 实验，不包含新 optimize、模型调用或新评估。

## 结论边界

- 可以写：prompt length growth is substantial。
- 可以写：length does not monotonically explain score gains。
- 可以写：prompt length is a reasonable next audit/control variable。
- 不能写：prompt 越长越好。
- 不能写：控制长度一定能提升。
- 不能写：Length-Controlled GEPA 已验证。
- 不能写：这是新的性能实验。
