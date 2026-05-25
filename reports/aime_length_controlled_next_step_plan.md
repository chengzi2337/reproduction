# AIME length-controlled 下一步计划

## 当前状态

当前证据链支持以下判断：

- AIME official_budget 5-seed 已完成，optimized prompt 在 5/5 seeds 上优于 seed prompt；
- prompt length audit 显示 optimized prompt 显著变长，但长度增长与 optimized_test_score / score_delta 不单调；
- post-hoc length-control audit 显示当前 15 个候选不足以支持简单长度上限式选择；
- 现阶段不应直接运行 Length-Controlled GEPA。

## 本阶段交付

本阶段只完成设计与脚手架：

- `reports/aime_length_controlled_candidate_selection_design.md`
- `reports/aime_length_control_artifact_capture_design.md`
- `src/length_controlled_selection.py`
- `tests/test_length_controlled_selection.py`
- `reports/aime_length_controlled_next_step_plan.md`

本阶段不是新实验，不产生 performance claim。

## 后续顺序

1. 固定 selection-level 纯函数规则，并用 fake candidates 单元测试覆盖。
2. 设计 runner artifact capture，明确 candidate / trajectory 字段。
3. 设计 Length-Controlled GEPA runner，但先不运行。
4. 若 runner design 通过审查，再考虑小范围执行 selection variant。
5. selection variant 有稳定证据后，才讨论 optimizer variant。

## 进入真实 Length-Controlled GEPA 的准入条件

只有满足以下条件，才应进入真实 Length-Controlled GEPA：

- 已完成 selection-level 规则设计；
- 已完成 artifact capture 设计；
- runner 能保存足够的 candidate / trajectory artifacts；
- 明确它是新方法变体，不是原始 GEPA 复现；
- 明确新实验的 seed、预算、模型后端、评价指标与停止条件；
- 明确不把 post-hoc 负结果解释为 length-control 最终失败。

## 暂停条件

出现以下情况应暂停，不继续跑实验：

- artifacts 仍只能保存少量最终候选；
- selected candidate 无法追溯到 candidate pool；
- validation score 与 prompt length 字段无法交叉验证；
- length-control rule 会无条件选择低质量短 prompt；
- runner 需要修改 optimizer 核心但没有独立设计文档；
- 任何流程需要 API key、模型调用或 GEPA 调用但未被明确批准为新实验。

## 本地验证

本阶段验证只允许本地静态和单元测试：

```bash
python -m compileall src scripts tests
pytest -q
```

验证通过只能说明选择规则纯函数和测试通过，不能说明 Length-Controlled GEPA 有性能收益。

## 建议结论

当前建议继续进入 `Length-Controlled GEPA runner design`，但仍不运行实验。runner design 的目标应是把 selection-level rules 接入 artifact capture 和离线可审计 comparison，而不是直接修改 GEPA optimizer。
