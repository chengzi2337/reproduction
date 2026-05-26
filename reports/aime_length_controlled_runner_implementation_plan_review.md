# AIME Length-Controlled GEPA runner implementation plan review

## 审查结论

当前 implementation plan 符合既定方向：它把下一步限定为 artifact wiring 和 offline selection comparison，没有进入真实实验。

本阶段允许：

- 写实现计划；
- 写非执行 plan manifest；
- 用 fake 数据测试计划结构；
- 明确未来 implementation 文件。

本阶段不允许：

- 调用模型；
- 调用 GEPA；
- 运行 seed；
- 修改 optimizer；
- 修改 evaluator；
- 修改既有 official_budget outputs；
- 声称 length control 已验证。

## 关键风险

最大风险是跳过 `inspect_gepa_result_capabilities`，直接假设 GEPA result 能提供完整 candidate pool。implementation plan 已把该步骤放在第一位，并规定字段不足时必须输出 artifact limitation。

第二个风险是把 hard cap 误写成强行短 prompt 选择。后续 comparison 实现必须复用已有 selection rules，并保留 best_val fallback。

第三个风险是把 validation tradeoff 写成 test performance claim。后续 summary writer 必须包含 `not_performance_claim = true`。

## 通过标准

本阶段通过标准是：

- `src/length_controlled_runner_plan.py` 只表达计划，不导入执行路径；
- 测试覆盖阶段顺序、非执行 flags、停机条件和静态禁用调用；
- 文档明确下一步仍是 fake-result / dry-run artifact wiring；
- 本地 `compileall` 和 `pytest` 通过。

## 下一步建议

下一步可以做 `fake-result artifact wiring implementation`，但仍不运行实验。该步骤应先实现 candidate extraction adapter 和 artifact writer，并用 fake GEPA result 覆盖字段缺失、score alignment 失败和 fallback summary。
