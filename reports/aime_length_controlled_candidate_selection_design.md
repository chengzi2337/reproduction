# AIME length-controlled candidate selection 设计

## 背景

当前 AIME official_budget 证据链分为三层：

1. 5-seed official_budget 结果显示 optimized prompt 在 5/5 seeds 上优于 seed prompt。
2. prompt length audit 显示 optimized prompt 显著变长，但长度增长与 optimized_test_score / score_delta 不单调。
3. post-hoc length-control audit 显示当前 5 个 run 的 candidate-level artifacts 可用，但每个 seed 只有 3 个候选；Rule B/C 没有找到更短且 0.02/0.05 分差内的 near-best candidate，简单 2x/3x/5x 长度上限会退回 seed prompt 并显著损失 validation score。

因此，当前结果不支持直接进入 Length-Controlled GEPA，也不能把 post-hoc audit 写成 length-control 方向失败的最终证明。更稳妥的下一步是先设计候选选择规则，将 length control 限定在最终 candidate selection 层，而不是修改 GEPA optimizer 的搜索过程。

## 目标

本设计只定义 length-controlled candidate selection 的第一版规则和审计边界：

- 不调用模型；
- 不调用 GEPA；
- 不运行新实验；
- 不修改 optimizer 或 evaluator；
- 不修改已有 official_budget 结果；
- 不声明新的性能结论；
- 只把候选选择规则设计为可测试的纯函数。

## 为什么不直接改 GEPA optimizer

直接修改 GEPA optimizer 会同时引入新的搜索策略、新的 objective 或新的候选生成行为。这样会让变量混杂，难以判断性能变化来自 prompt length control、候选搜索轨迹变化，还是 evaluator 噪声。

当前 post-hoc audit 还是负结果，并且 artifacts 较薄。此时直接跑 Length-Controlled GEPA 风险较高：它既不是原始 GEPA 复现，也没有足够 artifact 证明哪类长度约束值得优先实现。

## 第一版选择层设计

第一版只做 selection variant：

```text
GEPA 正常生成候选；
runner 保存完整 candidate / trajectory artifacts；
最终选择阶段在 validation score 和 prompt length 之间应用受控规则；
输出原始 best_val 选择与 length-controlled 选择的对比。
```

这不是 optimizer variant。它不改变候选生成过程，只改变候选池上的最终选择逻辑，因此更容易隔离变量。

## 规则定义

### Rule 0: best_val

选择 validation score 最高的候选。分数相同时选择更短 prompt，用作原始 GEPA selection baseline。

### Rule 1: tolerance-shortest

在 `best_val_score - candidate_val_score <= epsilon` 的候选里选择最短 prompt。建议 epsilon 初始取值为 0.02、0.05、0.10。

该规则用于回答：是否存在 validation score 接近最优但明显更短的候选。

### Rule 2: soft penalty

使用如下调整分：

```text
score_adjusted = val_score - lambda_chars * normalized_length
normalized_length = prompt_chars / max_prompt_chars_in_candidate_pool
```

选择 adjusted score 最高的候选。该规则把长度作为连续惩罚项，避免硬上限导致低质量短 prompt 被强行选中。

### Rule 3: ratio guard

候选必须满足：

```text
candidate_val_score >= best_val_score * min_score_fraction
```

满足 guard 后再按最短 prompt 或最高 validation score 做词典序选择。建议第一版 `min_score_fraction=0.95`。

### Rule 4: hard cap fallback

候选必须同时满足：

```text
candidate_prompt_chars <= max_chars
best_val_score - candidate_val_score <= max_score_gap
```

若没有满足条件的候选，必须回退原始 best_val。该规则不能无条件选择长度上限内的短 prompt，也不能无条件退回 seed prompt。

## 输出契约

每条规则必须输出：

- `rule_name`
- `selected_candidate`
- `best_candidate`
- `reason`
- `parameters`
- `fallback_used`
- `eligible_count`
- `score_gap_to_best`
- `chars_saved_vs_best`
- `length_reduction_vs_best`

这些字段用于后续 runner design 中写入 JSON artifact，也用于避免把 selection 规则的内部行为写成性能结论。

## 结论边界

本设计只说明 length control 可以作为候选选择变量继续研究。它不能支持以下结论：

- prompt 越短越好；
- prompt 越长越好；
- length control 一定能提升 AIME；
- Length-Controlled GEPA 已经验证；
- 当前 post-hoc audit 证明 length control 方向失败。

当前可写结论是：现有 5-seed artifacts 不支持直接进行简单长度上限式 Length-Controlled GEPA；若继续推进，应先实现 selection-level 规则和更完整的 candidate / trajectory artifact capture。
