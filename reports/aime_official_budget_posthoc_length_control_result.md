# AIME official_budget post-hoc length-controlled selection 只读审计结果

## 文档定位

- 本报告只读分析既有 5 个 official_budget run 的 candidate-level artifacts。
- 本报告不调用模型、不调用 API、不调用 GEPA、不运行新实验。
- 本报告不是 `Length-Controlled GEPA` 实验，也不是新的 test performance 结论。

## 审计边界标志

- `not_new_experiment = true`
- `posthoc_only = true`
- `no_model_called = true`
- `no_api_called = true`
- `no_gepa_optimize_called = true`
- `optimizer_not_modified = true`
- `evaluator_not_modified = true`
- `not_performance_claim = true`

## artifact 可用性与总体结论

- `candidate_artifacts_available_for_all_runs = true`
- `posthoc_selection_performed = true`
- `total_candidates = 15`
- `rules_with_shorter_selection_count = 15`
- `rules_with_near_best_shorter_selection_count = 0`
- `rules_with_exact_best_and_shorter_selection_count = 0`
- `max_chars_saved_vs_rule_a = 2817`
- `min_score_gap_among_shorter_selections = 0.622222222222`
- `supports_direct_length_controlled_gepa_experiment = false`
- `supports_length_controlled_candidate_selection_design = false`
- `length_controlled_gepa_validated = false`

## candidate 与 selection 规则明细

### seed0

- `run_dir`: `outputs/gepa_aime_official_budget_seed0/20260522T121001+0800`
- `candidate_artifacts_available`: `true`

| candidate_id | val_score | chars | words | lines | is_best_val_candidate | is_shorter_than_best_candidate | score_gap_to_best_val | length_reduction_ratio |
|---:|---:|---:|---:|---:|---|---|---:|---:|
| 0 | 0.1111111111111111 | 100 | 17 | 1 | `false` | `true` | 0.733333333333 | 0.965718 |
| 1 | 0.6888888888888889 | 2340 | 346 | 22 | `false` | `true` | 0.155555555556 | 0.197806 |
| 2 | 0.8444444444444444 | 2917 | 444 | 23 | `true` | `false` | 0.0 | 0.0 |

| rule | selected_candidate_id | val_score | chars | score_gap_to_rule_a | chars_saved_vs_rule_a | length_reduction_vs_rule_a | selection_available |
|---|---:|---:|---:|---:|---:|---:|---|
| `rule_a_best_val` | 2 | 0.8444444444444444 | 2917 | 0.0 | 0 | 0.0 | `true` |
| `rule_b_gap_0_02_shortest` | 2 | 0.8444444444444444 | 2917 | 0.0 | 0 | 0.0 | `true` |
| `rule_c_gap_0_05_shortest` | 2 | 0.8444444444444444 | 2917 | 0.0 | 0 | 0.0 | `true` |
| `rule_d_seed_2x_cap_best_val` | 0 | 0.1111111111111111 | 100 | 0.733333333333 | 2817 | 0.965718 | `true` |
| `rule_d_seed_3x_cap_best_val` | 0 | 0.1111111111111111 | 100 | 0.733333333333 | 2817 | 0.965718 | `true` |
| `rule_d_seed_5x_cap_best_val` | 0 | 0.1111111111111111 | 100 | 0.733333333333 | 2817 | 0.965718 | `true` |

### seed1

- `run_dir`: `outputs/gepa_aime_official_budget_seed1/20260522T175103+0800`
- `candidate_artifacts_available`: `true`

| candidate_id | val_score | chars | words | lines | is_best_val_candidate | is_shorter_than_best_candidate | score_gap_to_best_val | length_reduction_ratio |
|---:|---:|---:|---:|---:|---|---|---:|---:|
| 0 | 0.17777777777777778 | 100 | 17 | 1 | `false` | `true` | 0.733333333333 | 0.912587 |
| 1 | 0.9111111111111111 | 1144 | 195 | 12 | `true` | `false` | 0.0 | 0.0 |
| 2 | 0.8444444444444444 | 2386 | 389 | 27 | `false` | `false` | 0.066666666667 | -1.085664 |

| rule | selected_candidate_id | val_score | chars | score_gap_to_rule_a | chars_saved_vs_rule_a | length_reduction_vs_rule_a | selection_available |
|---|---:|---:|---:|---:|---:|---:|---|
| `rule_a_best_val` | 1 | 0.9111111111111111 | 1144 | 0.0 | 0 | 0.0 | `true` |
| `rule_b_gap_0_02_shortest` | 1 | 0.9111111111111111 | 1144 | 0.0 | 0 | 0.0 | `true` |
| `rule_c_gap_0_05_shortest` | 1 | 0.9111111111111111 | 1144 | 0.0 | 0 | 0.0 | `true` |
| `rule_d_seed_2x_cap_best_val` | 0 | 0.17777777777777778 | 100 | 0.733333333333 | 1044 | 0.912587 | `true` |
| `rule_d_seed_3x_cap_best_val` | 0 | 0.17777777777777778 | 100 | 0.733333333333 | 1044 | 0.912587 | `true` |
| `rule_d_seed_5x_cap_best_val` | 0 | 0.17777777777777778 | 100 | 0.733333333333 | 1044 | 0.912587 | `true` |

### seed2

- `run_dir`: `outputs/gepa_aime_official_budget_seed2/20260522T221654+0800`
- `candidate_artifacts_available`: `true`

| candidate_id | val_score | chars | words | lines | is_best_val_candidate | is_shorter_than_best_candidate | score_gap_to_best_val | length_reduction_ratio |
|---:|---:|---:|---:|---:|---|---|---:|---:|
| 0 | 0.06666666666666667 | 100 | 17 | 1 | `false` | `true` | 0.622222222222 | 0.893617 |
| 1 | 0.5333333333333333 | 868 | 149 | 17 | `false` | `true` | 0.155555555556 | 0.076596 |
| 2 | 0.6888888888888889 | 940 | 166 | 26 | `true` | `false` | 0.0 | 0.0 |

| rule | selected_candidate_id | val_score | chars | score_gap_to_rule_a | chars_saved_vs_rule_a | length_reduction_vs_rule_a | selection_available |
|---|---:|---:|---:|---:|---:|---:|---|
| `rule_a_best_val` | 2 | 0.6888888888888889 | 940 | 0.0 | 0 | 0.0 | `true` |
| `rule_b_gap_0_02_shortest` | 2 | 0.6888888888888889 | 940 | 0.0 | 0 | 0.0 | `true` |
| `rule_c_gap_0_05_shortest` | 2 | 0.6888888888888889 | 940 | 0.0 | 0 | 0.0 | `true` |
| `rule_d_seed_2x_cap_best_val` | 0 | 0.06666666666666667 | 100 | 0.622222222222 | 840 | 0.893617 | `true` |
| `rule_d_seed_3x_cap_best_val` | 0 | 0.06666666666666667 | 100 | 0.622222222222 | 840 | 0.893617 | `true` |
| `rule_d_seed_5x_cap_best_val` | 0 | 0.06666666666666667 | 100 | 0.622222222222 | 840 | 0.893617 | `true` |

### seed3

- `run_dir`: `outputs/gepa_aime_official_budget_seed3/20260525T104154+0800`
- `candidate_artifacts_available`: `true`

| candidate_id | val_score | chars | words | lines | is_best_val_candidate | is_shorter_than_best_candidate | score_gap_to_best_val | length_reduction_ratio |
|---:|---:|---:|---:|---:|---|---|---:|---:|
| 0 | 0.15555555555555556 | 100 | 17 | 1 | `false` | `true` | 0.688888888889 | 0.903939 |
| 1 | 0.8444444444444444 | 1041 | 174 | 13 | `true` | `false` | 0.0 | 0.0 |
| 2 | 0.7333333333333333 | 2330 | 361 | 23 | `false` | `false` | 0.111111111111 | -1.238232 |

| rule | selected_candidate_id | val_score | chars | score_gap_to_rule_a | chars_saved_vs_rule_a | length_reduction_vs_rule_a | selection_available |
|---|---:|---:|---:|---:|---:|---:|---|
| `rule_a_best_val` | 1 | 0.8444444444444444 | 1041 | 0.0 | 0 | 0.0 | `true` |
| `rule_b_gap_0_02_shortest` | 1 | 0.8444444444444444 | 1041 | 0.0 | 0 | 0.0 | `true` |
| `rule_c_gap_0_05_shortest` | 1 | 0.8444444444444444 | 1041 | 0.0 | 0 | 0.0 | `true` |
| `rule_d_seed_2x_cap_best_val` | 0 | 0.15555555555555556 | 100 | 0.688888888889 | 941 | 0.903939 | `true` |
| `rule_d_seed_3x_cap_best_val` | 0 | 0.15555555555555556 | 100 | 0.688888888889 | 941 | 0.903939 | `true` |
| `rule_d_seed_5x_cap_best_val` | 0 | 0.15555555555555556 | 100 | 0.688888888889 | 941 | 0.903939 | `true` |

### seed4

- `run_dir`: `outputs/gepa_aime_official_budget_seed4/20260525T135207+0800`
- `candidate_artifacts_available`: `true`

| candidate_id | val_score | chars | words | lines | is_best_val_candidate | is_shorter_than_best_candidate | score_gap_to_best_val | length_reduction_ratio |
|---:|---:|---:|---:|---:|---|---|---:|---:|
| 0 | 0.15555555555555556 | 100 | 17 | 1 | `false` | `true` | 0.777777777778 | 0.924185 |
| 1 | 0.7333333333333333 | 820 | 142 | 17 | `false` | `true` | 0.2 | 0.378317 |
| 2 | 0.9333333333333333 | 1319 | 228 | 16 | `true` | `false` | 0.0 | 0.0 |

| rule | selected_candidate_id | val_score | chars | score_gap_to_rule_a | chars_saved_vs_rule_a | length_reduction_vs_rule_a | selection_available |
|---|---:|---:|---:|---:|---:|---:|---|
| `rule_a_best_val` | 2 | 0.9333333333333333 | 1319 | 0.0 | 0 | 0.0 | `true` |
| `rule_b_gap_0_02_shortest` | 2 | 0.9333333333333333 | 1319 | 0.0 | 0 | 0.0 | `true` |
| `rule_c_gap_0_05_shortest` | 2 | 0.9333333333333333 | 1319 | 0.0 | 0 | 0.0 | `true` |
| `rule_d_seed_2x_cap_best_val` | 0 | 0.15555555555555556 | 100 | 0.777777777778 | 1219 | 0.924185 | `true` |
| `rule_d_seed_3x_cap_best_val` | 0 | 0.15555555555555556 | 100 | 0.777777777778 | 1219 | 0.924185 | `true` |
| `rule_d_seed_5x_cap_best_val` | 0 | 0.15555555555555556 | 100 | 0.777777777778 | 1219 | 0.924185 | `true` |

## 结果解释

1. 当前 5 个 run 的 `raw_result.json` 都包含 candidate-level prompt 与 validation aggregate score，因此可以执行 post-hoc selection audit。
2. Rule B / Rule C 在当前 artifacts 中没有找到比 Rule A 更短且仍在 0.02 / 0.05 分差内的 candidate。
3. Rule D 的 seed prompt 2x / 3x / 5x 长度上限只会选到 seed prompt candidate，本质上牺牲大量 validation score，不构成可用的 length-control 策略。
4. 当前结果不支持直接进入 Length-Controlled GEPA 实验；如果继续推进，应先写 length-controlled candidate selection design，并要求未来 runner 保存更丰富的 candidate/trajectory artifacts。

## 结论边界

- 可以写：candidate-level artifacts are available。
- 可以写：post-hoc length caps this strict do not recover near-best validation candidates in the current 3-candidate runs。
- 可以写：当前更适合先设计 length-controlled candidate selection，而不是直接改 optimizer。
- 不能写：Length-Controlled GEPA 已验证。
- 不能写：控制长度一定能提升 test performance。
- 不能写：这是新的性能实验。
