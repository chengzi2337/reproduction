# DeepSeek AIME official_budget revalidation 总结报告

## 文档定位

本文档汇总 `chengzi2337/reproduction` 当前分支上已经完成的 AIME official_budget 复现与只读审计结果。

本文档覆盖：

- AIME official_budget 5-seed 稳定性结果；
- prompt length 只读 audit；
- post-hoc length-controlled selection 只读 audit；
- 后续 length-control 方向的设计状态与边界。

本文档不包含：

- 新模型调用；
- 新 GEPA 调用；
- 新实验运行；
- 新 performance claim；
- optimizer 或 evaluator 修改；
- same-model reproduction 声明；
- 论文级最终复现结论。

## 固定实验边界

- `benchmark`: `aime`
- `provider`: `deepseek`
- `task_model`: `deepseek-v4-flash`
- `reflection_model`: `deepseek-v4-pro`
- `max_metric_calls`: `150`
- `dataset source`: `gepa.examples.aime.init_dataset()`
- `eval split`: `test split`
- `eval model`: `deepseek-v4-flash`
- `temperature_task`: `0.0`
- `temperature_reflection`: `0.7`
- `single_benchmark_only = true`
- `single_backend_only = true`
- `not_same_model_reproduction = true`

## Evidence trail

| 证据层 | 对应报告 | 结论强度 |
|---|---|---|
| 5-seed official_budget | `reports/aime_official_budget_5seed_report.md` | 支持 DeepSeek backend 下的中等强度多 seed 稳定性 |
| qualitative examples | `reports/aime_official_budget_qualitative_examples.md` | 逐题展示 question / prediction / gold / score，解释格式遵循与少量退化样例 |
| prompt length audit | `reports/aime_official_budget_prompt_length_audit_result.md` | 支持“长度显著增长，但不能单调解释收益” |
| post-hoc length-control audit | `reports/aime_official_budget_posthoc_length_control_result.md` | 支持“当前 artifacts 不支持直接跑简单长度上限式 Length-Controlled GEPA” |
| candidate selection design | `reports/aime_length_controlled_candidate_selection_design.md` | 设计层，不是实验结果 |
| runner design / implementation plan | `reports/aime_length_controlled_runner_design.md`, `reports/aime_length_controlled_runner_implementation_plan.md` | 计划层，不是实验结果 |

## 5-seed official_budget 结果

5 个 seed 的核心结果如下：

| seed | best_val_score | seed_test_score | optimized_test_score | score_delta | optimized > seed |
|---:|---:|---:|---:|---:|---|
| 0 | 0.8444444444444444 | 0.2 | 0.6333333333333333 | 0.4333333333333333 | true |
| 1 | 0.9111111111111111 | 0.16666666666666666 | 0.6666666666666666 | 0.5 | true |
| 2 | 0.6888888888888889 | 0.22666666666666666 | 0.9266666666666666 | 0.7 | true |
| 3 | 0.8444444444444444 | 0.25333333333333335 | 0.7266666666666667 | 0.47333333333333333 | true |
| 4 | 0.9333333333333333 | 0.17333333333333334 | 0.66 | 0.4866666666666667 | true |

聚合统计：

- `optimized > seed`: `5 / 5`
- `mean_seed_score = 0.20400000000000001`
- `mean_optimized_score = 0.7226666666666667`
- `mean_delta = 0.5186666666666666`
- `median_delta = 0.4866666666666667`
- `min_delta = 0.4333333333333333`
- `max_delta = 0.7`

可写结论：

> 在 DeepSeek backend 下，AIME official_budget 已表现出中等强度多 seed 稳定性：5 / 5 个 seed 中，optimized prompt 的 test score 均高于 seed prompt。

仍需保留的波动说明：

- `optimized_test_score` 范围为 `0.6333333333333333 -> 0.9266666666666666`；
- `score_delta` 范围为 `0.4333333333333333 -> 0.7`；
- `best_val_score` 与 `optimized_test_score` 不是严格单调对应；
- 当前结论强于 3-seed 初步稳定性，但仍不是论文级强稳定性结论。

## Prompt length audit 结果

5 个 seed 的 prompt 长度结果如下：

| seed | seed_prompt_chars | optimized_prompt_chars | prompt_char_growth | length_growth_ratio | optimized_test_score | score_delta |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 100 | 2917 | 2817 | 29.17 | 0.6333333333333333 | 0.4333333333333333 |
| 1 | 100 | 1144 | 1044 | 11.44 | 0.6666666666666666 | 0.5 |
| 2 | 100 | 940 | 840 | 9.4 | 0.9266666666666666 | 0.7 |
| 3 | 100 | 1041 | 941 | 10.41 | 0.7266666666666667 | 0.47333333333333333 |
| 4 | 100 | 1319 | 1219 | 13.19 | 0.66 | 0.4866666666666667 |

审计结论：

- optimized prompt 显著长于 seed prompt；
- prompt 长度增长与 optimized_test_score 不单调对应；
- prompt 长度增长与 score_delta 不单调对应；
- 最长 optimized prompt 不是最高分；
- 最短 optimized prompt 反而对应最高 optimized_test_score；
- token 数仅做 `chars / 4` 粗略估算，`token_estimate_for_audit_only = true`，`not_exact_tokenizer_count = true`。

可写结论：

> prompt length growth is substantial, but length does not monotonically explain score gains.

不可写结论：

- prompt 越长越好；
- 控制长度一定能提升；
- Length-Controlled GEPA 已验证；
- 这是新的性能实验。

## Post-hoc length-control audit 结果

post-hoc audit 基于已有 5 个 official_budget run 的 candidate-level artifacts，只读分析已有候选。

核心结果：

- `candidate_artifacts_available_for_all_runs = true`
- `posthoc_selection_performed = true`
- `total_candidates = 15`
- 每个 seed 只有 3 个候选；
- Rule B / Rule C 没有找到更短且在 `0.02` / `0.05` 分差内的 near-best candidate；
- Rule D 的 seed prompt `2x` / `3x` / `5x` 长度上限只会选到 seed prompt candidate，并显著损失 validation score；
- `supports_direct_length_controlled_gepa_experiment = false`
- `length_controlled_gepa_validated = false`

可写结论：

> 当前 5-seed artifacts 支持 post-hoc selection audit，但不支持直接进入简单长度上限式 Length-Controlled GEPA。

不可写结论：

- Length-Controlled GEPA 已失败；
- Length-Controlled GEPA 已验证；
- 简单长度上限能保留 test performance；
- 当前 post-hoc 负结果足以否定 length-control 方向。

## Length-control 方向当前状态

当前已完成的是设计和计划层工作：

- length-controlled candidate selection 纯函数规则；
- artifact capture 设计；
- runner design manifest；
- runner implementation plan。

这些工作只定义后续如何做，不属于实验结果。

当前合理后续顺序是：

1. 若继续推进，先做 fake-result artifact wiring implementation；
2. 先确认 GEPA result 能否提供完整 candidate pool、validation score alignment 和 trajectory 信息；
3. 如果 artifacts 不足，写 artifact limitation；
4. 只有在 artifact wiring 可验证后，才请求批准小规模 selection variant；
5. 仍不应直接进入 optimizer variant。

## 总体结论

当前结果符合路线 A 的保守收束目标：

> DeepSeek backend 下，AIME official_budget 具备中等强度多 seed 稳定性；optimized prompt 在 5 / 5 个 seed 上优于 seed prompt。与此同时，optimized prompt 明显变长，但长度增长不能单调解释 test score 或 score delta。post-hoc length-control audit 没有发现当前 3-candidate runs 中存在更短且 near-best 的候选，因此当前不支持直接运行简单长度上限式 Length-Controlled GEPA。

最终报告应使用的边界措辞：

- 可以说：`GEPA method-level reproduction with DeepSeek backend`
- 可以说：`AIME official_budget shows moderate multi-seed stability under DeepSeek backend`
- 可以说：`prompt length is a reasonable next audit/control variable`
- 不能说：`same-model reproduction`
- 不能说：`paper-level final reproduction`
- 不能说：`prompt 越长越好`
- 不能说：`Length-Controlled GEPA 已验证`
- 不能说：`控制长度一定能提升`

## 推荐下一步

如果目标是稳定交付，建议以本文档作为 Stage 1 revalidation 的最终汇总报告，不再继续扩展新 seed 或直接运行 Length-Controlled GEPA。

如果后续继续 length-control 方向，建议只进入 fake-result artifact wiring implementation，并把它明确标为 runner engineering preparation，而不是新实验。
