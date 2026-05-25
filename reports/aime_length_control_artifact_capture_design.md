# AIME length-control artifact capture 设计

## 设计动机

post-hoc length-control audit 已确认 5 个 official_budget run 存在 candidate-level artifacts，但每个 seed 只有 3 个候选，总候选数为 15。这个粒度足以支持 final prompt length audit 和粗粒度 post-hoc audit，但不足以分析细粒度 length-quality tradeoff。

下一步如果要评估 length-controlled candidate selection，runner 必须保存更完整的 candidate / trajectory artifacts。否则无法判断：

- 是否出现过更短且 near-best 的候选；
- 候选是在什么 mutation step 产生的；
- 原始 GEPA selection 与 length-controlled selection 的差异来自哪个阶段；
- 长度约束失败是因为规则不合适，还是因为候选池太稀疏。

## 保存边界

artifact capture 设计只定义后续 runner 应保存什么，不表示已经运行新实验：

- 不调用模型；
- 不调用 GEPA；
- 不修改已有 official_budget 结果；
- 不提交 outputs；
- 不保存 API key；
- 不保存本地绝对路径；
- 不把 capture 设计写成性能结论。

## Candidate 级字段

后续 runner 至少应对每个候选保存：

- `candidate_id`
- `parent_candidate_id`
- `mutation_step`
- `candidate_prompt`
- `candidate_prompt_chars`
- `candidate_prompt_words`
- `candidate_prompt_lines`
- `val_score`
- `train_score`
- `reflection_source`
- `selected_by_original_gepa`
- `selected_by_length_control_rule`
- `length_control_rule_name`
- `score_gap_to_best`
- `length_reduction_vs_best`

其中 `train_score` 和 `reflection_source` 如果 runner 当前无法稳定提供，可以显式写为 `null`，但不能静默省略。

## Trajectory 级字段

为了支持后续定位，应保存每个候选的生成上下文：

- `run_id`
- `seed`
- `task_name`
- `budget_name`
- `candidate_id`
- `parent_candidate_id`
- `mutation_step`
- `generation_round`
- `selection_round`
- `was_evaluated_on_validation`
- `was_eligible_for_final_selection`
- `rejection_reason`

这些字段用于回答候选是否只是被生成、是否参与 validation、是否进入最终选择池。

## 汇总字段

每个 run 应保存一个 summary：

- `candidate_pool_size`
- `num_candidates_within_0_02`
- `num_candidates_within_0_05`
- `num_shorter_near_best_candidates`
- `best_val_prompt_length`
- `shortest_near_best_prompt_length`
- `original_gepa_selected_candidate_id`
- `length_control_selected_candidate_id`
- `length_control_rule_name`
- `length_control_fallback_used`
- `not_new_experiment`
- `no_model_called_by_audit`
- `no_gepa_optimize_called_by_audit`

这些字段应与候选级 artifact 可交叉验证，避免报告层人工推断。

## 文件组织建议

后续 runner 可以按如下逻辑组织 artifact：

```text
run_dir/
  length_control/
    candidate_pool.json
    selection_comparison.json
    trajectory_summary.json
```

文件路径应使用相对 run_dir 的路径写入 summary，不要写入本地机器绝对路径。

## 质量控制

artifact capture 至少需要覆盖以下检查：

- candidate 数量必须与 summary 的 `candidate_pool_size` 一致；
- 每个 candidate 必须有唯一 `candidate_id`；
- 每个 selected candidate 必须能在 candidate pool 中找到；
- `score_gap_to_best` 必须由同一 candidate pool 内的 best validation score 计算；
- `length_reduction_vs_best` 必须由 prompt chars 计算；
- 若使用 hard cap fallback，必须记录 fallback 原因；
- 若字段不可用，必须写 `null` 或显式错误，不能编造数据。

## 当前结论

当前 artifacts 足够支持“final prompt length audit”和“粗粒度 post-hoc selection audit”，但不足以支持细粒度 length-control 机制判断。后续若推进，应先增强 runner 的 candidate / trajectory artifact capture，再考虑运行 selection-level length-control 变体。
