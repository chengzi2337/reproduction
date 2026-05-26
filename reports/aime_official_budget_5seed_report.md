# AIME official_budget 5-seed 稳定性报告

## 文档定位

- 本文档汇总 `AIME official_budget` 在 `DeepSeek` 后端下的 `5-seed` 结果。
- 本文档关注的问题是：`optimized prompt` 是否在五个 seed 下稳定优于 `seed prompt`。
- 本文档不是 `Stage 1` 历史结论改写。
- 本文档不是 `same-model reproduction` 声明。
- 本文档不是论文级最终复现结论。

## 固定实验边界

- `benchmark`: `aime`
- `provider`: `deepseek`
- `task_model`: `deepseek-v4-flash`
- `reflection_model`: `deepseek-v4-pro`
- `max_metric_calls`: `150`
- `dataset source`: `gepa.examples.aime.init_dataset()`
- `eval split`: `test split`
- `eval model`: `deepseek-v4-flash`
- `temperature_fields_present_in_config`: `true`
- `temperature_task`: `0.0`
- `temperature_reflection`: `0.7`
- `runner_temperature_application_not_revalidated_in_this_report`: `true`
- `not_same_model_reproduction = true`
- `single_benchmark_only = true`
- `single_backend_only = true`

## 运行清单

- `seed0`
  - `run_dir`: `outputs/gepa_aime_official_budget_seed0/20260522T121001+0800`
- `seed1`
  - `run_dir`: `outputs/gepa_aime_official_budget_seed1/20260522T175103+0800`
- `seed2`
  - `run_dir`: `outputs/gepa_aime_official_budget_seed2/20260522T221654+0800`
- `seed3`
  - `run_dir`: `outputs/gepa_aime_official_budget_seed3/20260525T104154+0800`
- `seed4`
  - `run_dir`: `outputs/gepa_aime_official_budget_seed4/20260525T135207+0800`

## 主结果表

| seed | run_dir | total_metric_calls | num_candidates | num_full_val_evals | best_val_score | seed_test_score | optimized_test_score | score_delta | seed_num_errors | optimized_num_errors | valid_for_performance_claim |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | `outputs/gepa_aime_official_budget_seed0/20260522T121001+0800` | 150 | 3 | 3 | 0.8444444444444444 | 0.2 | 0.6333333333333333 | 0.4333333333333333 | 0 | 0 | `true` |
| 1 | `outputs/gepa_aime_official_budget_seed1/20260522T175103+0800` | 162 | 3 | 3 | 0.9111111111111111 | 0.16666666666666666 | 0.6666666666666666 | 0.5 | 0 | 0 | `true` |
| 2 | `outputs/gepa_aime_official_budget_seed2/20260522T221654+0800` | 150 | 3 | 3 | 0.6888888888888889 | 0.22666666666666666 | 0.9266666666666666 | 0.7 | 0 | 0 | `true` |
| 3 | `outputs/gepa_aime_official_budget_seed3/20260525T104154+0800` | 159 | 3 | 3 | 0.8444444444444444 | 0.25333333333333335 | 0.7266666666666667 | 0.47333333333333333 | 0 | 0 | `true` |
| 4 | `outputs/gepa_aime_official_budget_seed4/20260525T135207+0800` | 150 | 3 | 3 | 0.9333333333333333 | 0.17333333333333334 | 0.66 | 0.4866666666666667 | 0 | 0 | `true` |

补充说明：

- `total_metric_calls` 可能超过 `max_metric_calls`，因为 GEPA 可能会在预算边界附近完成一个评估单元；因此 `max_metric_calls` 应理解为控制预算，而不是最终调用计数必须严格相等的字段。

## Prompt 长度表

说明：
- 这里先用 `system_prompt` 字符数作为长度近似指标。
- `token_est` 仅用 `chars / 4` 做粗略估算，不作为严格成本结论。

| seed | seed_prompt_chars | optimized_prompt_chars | prompt_char_growth | seed_prompt_tokens_est | optimized_prompt_tokens_est | token_growth_est |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 100 | 2917 | 2817 | 25 | 729 | 704 |
| 1 | 100 | 1144 | 1044 | 25 | 286 | 261 |
| 2 | 100 | 940 | 840 | 25 | 235 | 210 |
| 3 | 100 | 1041 | 941 | 25 | 260 | 235 |
| 4 | 100 | 1319 | 1219 | 25 | 330 | 305 |

## 聚合统计

- `optimized > seed` 的 seed 数：`5 / 5`
- `mean_seed_score = 0.20400000000000001`
- `mean_optimized_score = 0.7226666666666667`
- `mean_delta = 0.5186666666666666`
- `median_delta = 0.4866666666666667`
- `min_delta = 0.4333333333333333`
- `max_delta = 0.7`
- `delta_range = 0.26666666666666666`
- `optimized_score_range = 0.29333333333333333`
- `seed_score_range = 0.0866666666666667`
- `best_val_score_range = 0.24444444444444446`
- `mean_prompt_growth_chars = 1372.2`
- `min_prompt_growth_chars = 840`
- `max_prompt_growth_chars = 2817`

## 结果判断

### 稳定性结论

按照此前 `5-seed` 计划里预先约定的判断口径：

- 如果 `5 / 5` 个 seed 都满足 `optimized > seed`
  - 可表述为：具备中等强度多 seed 稳定性

当前结果满足这一条件，因此可以写出如下结论：

> `AIME official_budget` 在 `DeepSeek` 后端下，已经表现出中等强度的多 seed 稳定性：`5 / 5` 个 seed 上，`optimized prompt` 都优于 `seed prompt`。

更严格的口径是：该结论成立于当前 `GEPA/AIME official evaluator` 下。answer extractability audit 显示，`official_score_gain = 0.518666666667`，但 `relaxed_extractable_score_gain = 0.016`；seed prompt 的 `format_loss_count = 539`，optimized prompt 的 `format_loss_count = 162`。因此，这个 observed official-score gain 不能解释为 pure reasoning improvement，相当大比例来自 output-protocol adherence improvement。

换言之，当前结果可以支持“official evaluator 下的稳定提升”，但不应写成“数学推理能力被纯粹提升了 0.5187”。

这比此前的 `3-seed` 结论更强，因为当前结果已经不只是“初步稳定”，而是经过五个不同 seed 的重复验证后仍保持方向一致。

### 仍然存在的波动

虽然方向上一致，但幅度上仍有明显波动：

1. `optimized_test_score` 范围仍然较大：`0.6333333333333333 -> 0.9266666666666666`
2. `score_delta` 范围仍然较大：`0.4333333333333333 -> 0.7`
3. `best_val_score` 与 `optimized_test_score` 之间仍然不是严格单调对应：
   - `seed4` 的 `best_val_score` 最高，为 `0.9333333333333333`
   - 但 `seed2` 的 `optimized_test_score` 最高，为 `0.9266666666666666`

因此，当前最准确的说法是：

> 五个 seed 的方向性已经稳定，但性能幅度仍有中等波动。

这足以支持 baseline 已经较稳，但还不足以写成“几乎无方差”或“论文级强稳定”的结论。

### 长度与性能关系

五个 seed 的 `optimized prompt` 都显著长于 `seed prompt`，但长度增长与测试分数仍不单调对应：

- `seed0` 的 prompt 增长最大：`+2817 chars`
- `seed2` 的 prompt 增长最小：`+840 chars`
- 但 `seed2` 的 `optimized_test_score` 最高：`0.9266666666666666`

这说明：

- 当前收益仍不能简单解释为“prompt 越长越好”
- prompt 长度和 token 成本仍然是后续最值得独立审计的变量
- `Length-Controlled GEPA` 依然是自然的下一步研究切口

## 关于恢复运行的说明

### seed2

- `seed2` 首次 `saved prompt eval` 曾出现：
  - `AttributeError after 4 attempts: 'BadRequestError' object has no attribute 'choices'`
- 随后确认账户余额此前不足，充值后在原 `run_dir` 上通过 `--resume --retry-failed` 完成恢复。
- 最终以恢复后的 `saved_prompt_eval_summary.json` 为准。

### seed4

- `seed4` 的 `official_budget` optimize 阶段是完成的。
- `saved prompt eval` 首次在命令层超时，随后检查发现：
  - `seed 150/150` 已完成
  - `optimized 50/150` 已完成
- 后续在原 `run_dir` 上进行了最小补充恢复：
  - `--resume`
  - `--resume --retry-failed`
  - `--resume --retry-failed --batch-size 5`
- 在用户补充充值后，最后一次 `--resume --retry-failed --batch-size 5` 成功补齐剩余 `50` 条失败样本。
- 最终以 `20260525T190204+0800` 的 `saved_prompt_eval_summary.json` 为权威结果：
  - `optimized_prompt_score = 0.66`
  - `valid_for_performance_claim = true`

因此，`seed4` 应视为**最小补充恢复后形成的有效结果**。

## 结论边界

当前结果可以支持：

- `GEPA method-level reproduction with DeepSeek backend` 在 `AIME official_budget` official evaluator 下具备中等强度多 seed 稳定性
- `optimized prompt` 在 `5 / 5` 个 seed 上都优于 `seed prompt`
- observed official-score gain 同时包含任务求解行为改进和 output-protocol adherence improvement

当前结果仍然不能支持：

- `same-model reproduction`
- 原论文全部结论已被严格复现
- 多 benchmark / 多 backend 的泛化稳定性
- “prompt 越长越好”
- observed official-score gain 是 pure reasoning improvement

## 下一步建议

既然 `5-seed`、prompt length audit、post-hoc length-control audit 和 answer extractability audit 已经完成，下一步不应继续机械增加 seed，也不应直接跑 `Length-Controlled GEPA`。

更稳妥的下一步是先设计 format-controlled seed baseline：

> 在不使用 GEPA 优化的情况下，仅加强 seed prompt 的最终答案格式约束，观察 official score 是否显著上升。

如果后续要做小创新，我建议把问题收束成一句话：

> 在已经具备 `5 / 5` 正向提升的前提下，是否可以控制 prompt 长度增长，同时保持大部分测试收益？
