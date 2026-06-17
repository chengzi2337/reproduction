# IFBench Qwen3 缺失 Baseline no-cache 补跑结果

生成时间：2026-06-17 16:29:47 +08:00

## 结论

seed1 与 seed2 的 Baseline no-cache replay 已完成。两条均启用 `disable_dspy_cache=true`，均为 `294/294`，无缺失索引、无重复索引、无 provider rejection。

这次补跑修正了此前 seed1/seed2 Baseline 使用缓存口径的 caveat。新的 no-cache Baseline 分数显著高于 cached 补跑分数，因此此前用 cached Baseline 得出的 seed1/seed2 GEPA 正向幅度被削弱。

## 结果表

| seed | Baseline no-cache | rows | metric sum | parse failure | provider rejection | 说明 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 36.564626 | 294 | 107.5 | 1 | 0 | 完整 metric 后因 Windows 长路径收尾失败，已从 294 条 metric 恢复 summary/aggregate；token 字段不可恢复，记为 0 |
| 2 | 36.054422 | 294 | 106.0 | 1 | 0 | 正常收尾，`evaluation_result.txt` 已生成 |

## 与 GEPA full-budget 对照

| seed | Baseline no-cache | GEPA full-budget | GEPA - Baseline |
| --- | ---: | ---: | ---: |
| 0 | 36.564626 | 35.884354 | -0.680272 |
| 1 | 36.564626 | 35.374150 | -1.190476 |
| 2 | 36.054422 | 36.224490 | +0.170068 |

三 seed 均值：

| optimizer | mean |
| --- | ---: |
| Baseline no-cache | 36.394558 |
| GEPA full-budget | 35.827664 |
| delta | -0.566893 |

## 解释边界

- 当前 no-cache 补跑后，三 seed 平均结果不支持“GEPA 在 DashScope/Qwen3 paper-adapted IFBench 上稳定优于 Baseline”。
- seed2 仍有轻微正向，但幅度只有 `+0.17`，不足以支撑论文图中约 `+1.7` 的稳定提升。
- seed1 的恢复是收尾恢复，不是样本重算；分数、sample matrix、finish reason、parse failure 均来自完整的 294 条真实 metric log。
- 当前路线仍是 DashScope/Qwen3 paper-adapted 云 API 复现，不是 strict Arbor/local Qwen 论文复现。

## 研究含义

no-cache Baseline 补齐后，原始 GEPA full-budget 在三 seed 平均上低于 Baseline。结合此前 hard-constraint P2/MHC 的强正向结果，更合理的研究方向不是“云 API 下 GEPA 原始收益稳定复现”，而是：

- GEPA 的原始 prompt 搜索在 IFBench 上可能引入不稳定的通用解释/结构化偏置。
- IFBench 对 hard constraints 极敏感，显式约束优先级提示能显著改善 Baseline 和 GEPA。
- 后续论文研究应把“约束优先级、反射模型/任务模型差异、provider 后端差异、缓存/采样方差”作为机制变量，而不是只报告单次 full-budget 分数。
