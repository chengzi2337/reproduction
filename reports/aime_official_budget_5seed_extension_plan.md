# AIME official_budget 5-seed 扩展计划

## 当前状态

- 当前 `AIME official_budget` 已完成 `seed0`、`seed1`、`seed2` 的结果汇总。
- 现有 `3-seed` 结果支持：
  - `3 / 3` 个 seed 上 `optimized prompt > seed prompt`
  - 具备初步多 seed 稳定性
- 现有结果仍不支持：
  - 强稳定的论文级多 seed 结论
  - `same-model reproduction`

## 本次扩展目标

- 新增 `seed3` 与 `seed4` 的 official_budget 配置。
- 目标是把 baseline evidence 从 `3-seed` 扩展到 `5-seed`。
- 本提交只做配置与计划准备，不运行新实验。

## 本提交明确不做的事

- 不运行 `seed3` official_budget
- 不运行 `seed4` official_budget
- 不运行 `saved prompt eval`
- 不调用模型
- 不调用 GEPA
- 不改已有 `seed0/seed1/seed2` 结果

## 5-seed 判断口径

- 如果 `5 / 5` 个 seed 都满足 `optimized > seed`
  - 可表述为：具备中等强度多 seed 稳定性
- 如果 `4 / 5` 个 seed 满足 `optimized > seed`
  - 只能表述为：多数 seed 正向，但非完全稳定
- 如果 `<= 3 / 5` 个 seed 满足 `optimized > seed`
  - 不能继续写稳定性结论
  - 应转入方差分析与失败模式分析

## 后续顺序

1. 先完成 `seed3` 与 `seed4` 的 official_budget 与 `saved prompt eval`
2. 汇总形成 `5-seed` 报告
3. 再讨论 prompt length audit
4. 再讨论 `Length-Controlled GEPA`

## 固定约束

- 不跳过 `5-seed` 直接进入 `Length-Controlled GEPA`
- 不把 `5-seed` 配置准备误写成实验已完成
- 不改写 `Stage 1` 历史结论
