# AIME Length-Controlled GEPA runner design review

## 审查结论

本阶段进入 runner design 的方向符合前序结论，但必须继续保持非执行边界。

综合判断：

- 当前不应运行 Length-Controlled GEPA；
- 当前不应修改 GEPA optimizer；
- 当前不应增加 seed 或预算；
- 当前应先固定 runner artifact 契约和 selection comparison 契约；
- 当前新增的 manifest builder 只能作为设计脚手架，不能作为实验 runner。

## 与既定方向的一致性

既定方向是先完成 Stage 1 official_budget revalidation，再做只读 prompt length audit 和 post-hoc length-control audit，最后再决定是否进入 length-control 方向。

当前 runner design 与该方向一致，原因是：

- 它承认 official_budget 5-seed 只是 method-level reproduction under DeepSeek backend；
- 它没有把 length audit 写成“越长越好”；
- 它没有把 post-hoc 负结果写成 length-control 失败最终证明；
- 它把下一步限定为 selection variant，而不是 optimizer variant；
- 它要求增强 candidate / trajectory artifacts 后再运行实验。

## 风险评估

主要风险是 runner design 被误用为已验证方法。为避免该风险，manifest 中必须固定：

- `execution_status = not_executed`
- `stage = runner_design_only`
- `not_new_experiment = true`
- `no_model_called = true`
- `no_gepa_optimize_called = true`

第二个风险是 hard cap rule 退化成“强行选短 prompt”。设计中必须要求 hard cap 同时满足 validation score gap，并在不满足时 fallback 到 best_val。

第三个风险是 artifact 太薄，导致 selection comparison 无法解释。因此 runner implementation plan 必须优先解决 candidate pool 和 trajectory capture。

## 后续准入条件

进入 runner implementation plan 前，需要满足：

- 已确认 manifest builder 测试通过；
- 已确认设计文档不包含新性能主张；
- 已确认不需要 API key；
- 已确认不需要调用 GEPA；
- 已确认 implementation plan 不修改 optimizer 核心。

进入真实实验前，还需要额外满足：

- runner 能保存完整 candidate pool；
- runner 能保存 trajectory summary；
- selection comparison 能离线复现；
- 实验计划明确 seed、预算、后端、停止条件和报告边界；
- 用户明确批准运行新实验。

## 当前建议

下一步建议是 `Length-Controlled GEPA runner implementation plan`，仍然先不运行实验。实现计划应先定义如何从 GEPA result 中抽取 candidate pool 和 trajectory，如果现有 GEPA result 无法提供字段，则应先写 artifact limitation，而不是补跑实验。
