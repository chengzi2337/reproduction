# AIME Length-Controlled GEPA runner implementation plan

## 当前阶段

本文件是 implementation plan，不是 runner implementation，也不是实验执行记录。

当前边界保持不变：

- 不调用模型；
- 不调用 GEPA；
- 不运行新实验；
- 不修改 optimizer；
- 不修改 evaluator；
- 不读取或修改既有 official_budget outputs；
- 不保存 API key；
- 不保存本地绝对路径；
- 不产生 performance claim。

## 目标

下一步实现应只做 `selection_variant_artifact_wiring`：

```text
GEPA 正常生成候选；
runner 捕获候选池和轨迹；
离线应用 length-control selection rules；
写出 selection comparison；
报告 validation tradeoff，不报告 test performance 提升。
```

第一版 implementation 仍不应修改 GEPA optimizer 核心。若现有 GEPA result 无法暴露完整候选池和分数映射，应停止并写 artifact limitation，而不是补跑实验或改 optimizer。

## 实现阶段

### 1. inspect_gepa_result_capabilities

目的：确认 GEPA result 是否暴露完整候选、validation score、best index、candidate id、parent id 和 trajectory 信息。

交付物：只读 capability matrix。

停机条件：如果 candidate prompt 与 validation score 无法一一对应，停止进入 artifact limitation。

### 2. define_candidate_extraction_adapter

目的：把 GEPA result 转换为统一 candidate pool 结构。

约束：

- adapter 必须是纯函数；
- 输入使用 fake result 或已内存化 result；
- 不读取 outputs；
- 不调用 GEPA；
- 不调用模型。

### 3. define_artifact_writer

目的：定义未来 runner 写出的 artifact 文件和字段。

目标文件：

```text
length_control/candidate_pool.json
length_control/trajectory_summary.json
length_control/selection_comparison.json
length_control/runner_design_manifest.json
```

writer 必须拒绝写入 secret 值和本地绝对路径。

### 4. define_offline_selection_comparison

目的：在同一 candidate pool 上离线应用：

- `best_val`
- `tolerance_shortest_0_02`
- `tolerance_shortest_0_05`
- `tolerance_shortest_0_10`
- `soft_length_penalty`
- `lexicographic_ratio_guard_0_95`
- `hard_cap_then_best_val`

该阶段应复用 `src/length_controlled_selection.py`，不重新实现选择规则。

### 5. define_report_summary_writer

目的：生成 summary，明确当前只是 selection comparison。

summary 必须包含：

- `not_new_experiment = true`
- `not_performance_claim = true`
- `no_model_called = true`
- `no_gepa_optimize_called = true`
- `optimizer_core_unchanged = true`
- `evaluator_unchanged = true`

### 6. define_dry_run_validation

目的：定义不调用模型的 dry-run 验证。

允许验证命令：

```bash
python -m compileall src scripts tests
pytest -q
```

dry-run 通过只能说明 artifact wiring 和 selection comparison 代码可运行，不能说明 Length-Controlled GEPA 有性能收益。

## 计划中的后续文件

后续 implementation 可以新增：

- `src/length_controlled_runner_artifacts.py`
- `src/length_controlled_runner_comparison.py`
- `scripts/plan_aime_length_controlled_runner.py`
- `tests/test_length_controlled_runner_artifacts.py`
- `tests/test_length_controlled_runner_comparison.py`

这些文件仍应先使用 fake results 和临时目录测试，不运行真实 GEPA。

## 准入条件

进入 implementation 前必须满足：

- runner design manifest 已存在；
- selection rules 已是纯函数；
- artifact capture contract 已存在；
- 不需要修改 optimizer 核心；
- 不需要修改 evaluator；
- 用户尚未批准新实验，因此实现只能保持 dry-run / fake-result 范围。

## 停机条件

如果出现以下任一情况，必须停止：

- candidate pool 不可用；
- candidate score alignment 不可验证；
- selected candidate 无法在 pool 中找到；
- 需要修改 optimizer 核心；
- implementation plan 阶段需要模型调用；
- artifact 会保存 secret 或本地绝对路径。

## 当前结论

可以进入 runner implementation planning，但仍不能进入实验运行。下一步如果实施，应先做 fake-result artifact wiring；若 GEPA result 字段不足，应写 artifact limitation，而不是运行 Length-Controlled GEPA。
