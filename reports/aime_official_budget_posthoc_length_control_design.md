# AIME official_budget post-hoc length-controlled selection 只读审计设计

## 目标

本设计定义一个只读 `Post-hoc Length-Controlled Selection Audit`，用于检查 5 个既有 `AIME official_budget` run 的 candidate-level artifacts 是否支持长度受控的候选选择分析。

本任务不调用模型、不调用 GEPA、不运行新实验、不修改 optimizer、不修改 evaluator。

## 为什么不直接改 GEPA optimizer

当前证据只能说明两点：

1. `optimized prompt` 在 `5 / 5` 个 seed 上优于 `seed prompt`。
2. `optimized prompt` 显著变长，但长度增长与 `optimized_test_score` / `score_delta` 不单调。

这足以说明 prompt length 是合理的后续控制变量，但还不足以证明应该修改 GEPA optimizer。直接改 optimizer 会引入新的算法变量，导致问题从“复现与审计”变成“新方法设计”，并且需要重新跑优化与测试评估。

更稳妥的顺序是先只读检查已有 candidate 是否存在“更短且 validation score 接近最优”的选择空间。

## 为什么先做 post-hoc selection audit

Post-hoc audit 的优势是：

- 只读已有 `raw_result.json`。
- 不产生新的模型调用或费用。
- 不改变 GEPA 的搜索过程。
- 可以先判断长度控制是否有可观察候选空间。
- 如果 artifacts 不足，可以明确写出 artifact limitation，而不是过早改 runner 或 optimizer。

## 数据来源

固定读取以下 run_dir：

| seed | run_dir |
|---:|---|
| 0 | `outputs/gepa_aime_official_budget_seed0/20260522T121001+0800` |
| 1 | `outputs/gepa_aime_official_budget_seed1/20260522T175103+0800` |
| 2 | `outputs/gepa_aime_official_budget_seed2/20260522T221654+0800` |
| 3 | `outputs/gepa_aime_official_budget_seed3/20260525T104154+0800` |
| 4 | `outputs/gepa_aime_official_budget_seed4/20260525T135207+0800` |

必需 artifact：

- `raw_result.json`
- `seed_prompt.json`
- `gepa_result_summary.json`

候选级字段：

- `raw_result.json.candidates`
- `raw_result.json.val_aggregate_scores`
- `raw_result.json.best_idx`

如果字段缺失或数量不一致，脚本必须输出 `candidate_artifacts_available = false`，并明确写：`candidate-level artifacts unavailable; post-hoc length-controlled selection cannot be performed from current saved artifacts.`

## Candidate 统计字段

每个 candidate 输出：

- `candidate_id`
- `candidate_val_score`
- `candidate_prompt_chars`
- `candidate_prompt_words`
- `candidate_prompt_lines`
- `is_best_val_candidate`
- `is_shorter_than_best_candidate`
- `score_gap_to_best_val`
- `length_reduction_ratio`

`length_reduction_ratio` 定义为：

```text
1 - candidate_prompt_chars / best_candidate_prompt_chars
```

若 best candidate 长度为 0，则显式失败。

## Post-hoc selection 规则

Rule A：

```text
选择 val_score 最高的 prompt，也就是原 GEPA best_idx 对应的选择。
```

Rule B：

```text
在 val_score 距离最高分不超过 0.02 的候选里，选最短 prompt。
```

Rule C：

```text
在 val_score 距离最高分不超过 0.05 的候选里，选最短 prompt。
```

Rule D：

```text
设置长度上限，不超过 seed prompt 的 2x / 3x / 5x；
在满足上限的候选里选 val_score 最高者。
```

Rule D 仅做 candidate-level validation artifact 审计，不产生任何新的 test score。

## 输出与边界

JSON 输出到：

```text
outputs/aime_official_budget_posthoc_length_control_audit/<timestamp>/posthoc_length_control_audit.json
```

报告输出到：

```text
reports/aime_official_budget_posthoc_length_control_result.md
```

JSON 与报告必须包含：

- `not_new_experiment = true`
- `posthoc_only = true`
- `no_model_called = true`
- `no_api_called = true`
- `no_gepa_optimize_called = true`
- `optimizer_not_modified = true`
- `evaluator_not_modified = true`
- `not_performance_claim = true`

## 结论边界

可以写：

- candidate-level artifacts are available / unavailable。
- post-hoc length-controlled selection can / cannot be performed from current saved artifacts。
- 某些规则在 validation score 容忍范围内选择到更短 candidate。
- 该结果支持或不支持下一步设计 length-controlled candidate selection。

不能写：

- Length-Controlled GEPA 已验证。
- 控制长度一定能提升 test performance。
- 这是新的性能实验。
- post-hoc validation selection 等价于重新评估后的 test 结论。
