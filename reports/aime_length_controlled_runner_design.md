# AIME Length-Controlled GEPA runner design

## 当前阶段

本阶段进入 runner design，但仍不是 Length-Controlled GEPA 实验。

当前边界：

- 不调用模型；
- 不调用 GEPA；
- 不运行新实验；
- 不修改 optimizer；
- 不修改 evaluator；
- 不修改已有 official_budget 结果；
- 不提交 outputs；
- 不保存 API key 或本地绝对路径。

## 为什么现在只做 runner design

已有结论显示，AIME official_budget 5-seed 下 optimized prompt 稳定优于 seed prompt；prompt length audit 显示长度增长显著但不能单调解释 test score 或 score delta；post-hoc length-control audit 显示当前每个 seed 只有 3 个候选，简单长度上限不可用。

因此，当前合理路线不是直接运行 Length-Controlled GEPA，而是先设计 runner 如何保存更完整 artifacts，并在候选生成后应用 length-controlled selection。这样能把新变量限定在最终选择层，避免把搜索过程变化、artifact 缺失和长度控制混在一起。

## Runner 分层

第一版 runner 应拆成四层：

1. `candidate generation`：仍使用原 GEPA 生成候选，不改 optimizer 核心。
2. `candidate capture`：保存完整 candidate pool 和 trajectory。
3. `selection comparison`：离线应用原始 best_val 与 length-control rules。
4. `report summary`：只报告选择差异、长度差异和 validation tradeoff，不写性能提升结论。

本轮新增的 `src/length_controlled_runner_manifest.py` 只描述第 2-4 层的设计契约，不执行第 1 层。

## Integration mode

第一版必须是：

```text
selection_variant_after_candidate_generation
```

含义：

- GEPA 候选生成过程保持不变；
- 原始 best_val 选择仍保留；
- length-control 只在同一 candidate pool 上做替代选择；
- 每条规则都必须输出 selected candidate、best candidate、fallback 状态和选择理由；
- hard cap 规则必须带质量阈值和 best_val fallback。

这不是 optimizer variant。任何需要修改 GEPA 搜索 objective、mutation 策略或 reflection 策略的方案，都必须另写 optimizer design。

## Rule sequence

runner 应按固定顺序执行以下规则，便于跨 seed 对比：

1. `best_val`
2. `tolerance_shortest_0_02`
3. `tolerance_shortest_0_05`
4. `tolerance_shortest_0_10`
5. `soft_length_penalty`
6. `lexicographic_ratio_guard_0_95`
7. `hard_cap_then_best_val`

固定顺序不是为了证明这些超参最优，而是为了让第一版 selection variant 可审计、可重复。

## Artifact 输出设计

未来 runner 每个 run 至少应输出：

```text
length_control/
  candidate_pool.json
  trajectory_summary.json
  selection_comparison.json
  runner_design_manifest.json
```

`candidate_pool.json` 保存每个候选的 prompt、长度、分数、父候选、mutation step 和选择标记。

`trajectory_summary.json` 保存候选生成和进入最终选择池的路径，区分“生成过”“验证过”和“可最终选择”。

`selection_comparison.json` 保存每条 rule 的选择结果、score gap、长度节省、fallback 状态和 reason。

`runner_design_manifest.json` 保存本阶段 manifest，必须包含：

- `not_new_experiment = true`
- `runner_design_only = true`
- `no_model_called = true`
- `no_gepa_optimize_called = true`
- `optimizer_core_unchanged = true`
- `evaluator_unchanged = true`

## 停机条件

进入真实 runner 实现前，如果出现以下情况，应暂停：

- GEPA result 无法提供完整 candidate pool；
- candidate prompt 与 validation score 无法一一对应；
- selected candidate 无法追溯到 candidate pool；
- runner 需要修改 optimizer 核心才能拿到候选；
- hard cap 规则会选择低质量短 prompt 且没有 fallback；
- artifact 需要保存 key、请求体原文或本地绝对路径。

## 验收标准

runner design 阶段只接受以下验证：

- manifest builder 单元测试通过；
- 静态检查确认不导入 GEPA、OpenAI、LiteLLM 或现有执行 runner；
- manifest 包含必需 flags 和 artifact 字段；
- 文档明确它不是新实验，也不产生 performance claim。

## 当前建议

本阶段完成后，下一步可以设计 `Length-Controlled GEPA runner implementation plan`，但仍应先做 dry-run 级别的 artifact wiring plan。只有当 runner 能保存足够 candidate / trajectory artifacts 后，才考虑运行小规模 selection variant。
