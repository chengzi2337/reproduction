# IFBench/Qwen3 约束优先级后续实验

## 实验边界

本报告只描述 `DashScope/Qwen3 paper-adapted cloud-low-concurrency` 路线，不属于
Arbor/local Qwen 的 strict paper reproduction。所有 deterministic replay 均使用：

- `temperature=0`
- `top_p=0.95`
- `max_tokens=8192`
- 串行执行
- 官方 artifact 的 IFBench split、program 结构与 metric

## P2 重复回放稳定性

P2 只在原 GEPA optimized program 的两个 predictor instruction 后追加
`hard-constraint priority`，不修改 program 结构和 metric。

| 指标 | 第 1 次 | 第 2 次 |
|---|---:|---:|
| test 行数 | 294 | 294 |
| score | 38.61 | 38.61 |
| metric sum | 113.5 | 113.5 |
| parse failure | 0 | 0 |
| provider rejection | 0 | 0 |

两次回放的 294 个 sample-level score 完全一致：

- changed samples：0
- improved samples：0
- degraded samples：0
- 所有 instruction group 的 score delta：0

因此，在当前 DashScope 服务版本和 `temperature=0` 设置下，P2 的 38.61 不是单次
采样偶然现象。

## 人工 hard-constraint prompt

为区分“人工规则本身有效”与“必须依赖 GEPA optimized prompt”，本实验从
deterministic Baseline program 出发，只向两个 predictor instruction 追加与 P2
完全相同的 `hard-constraint priority`，记为 MHC。

结构门禁：

- program type 保持 `IFBenchCoT2StageProgram`
- 两个模块保持 `ChainOfThought`
- 只修改 `generate_response_module` 和 `ensure_correct_response_module` 的 instruction
- metric、split 和模型参数不变

### 总体结果

| Program | Score |
|---|---:|
| deterministic Baseline | 34.35 |
| 原 GEPA | 35.20 |
| Baseline + MHC | 37.76 |
| GEPA + P2 | 38.61 |

MHC 相对 Baseline：

- score delta：+3.41
- 改善 / 退化 / 变化样本：33 / 20 / 53
- metric 净增量：+10.0
- parse failure：0
- provider rejection：0

P2 相对 MHC：

- score delta：+0.85
- 改善 / 退化 / 变化样本：25 / 24 / 49
- metric 净增量：+2.5

### 分组结果

| Group | Baseline | MHC | P2 | MHC - Baseline | P2 - MHC |
|---|---:|---:|---:|---:|---:|
| count | 45.28 | 42.45 | 50.94 | -2.83 | +8.49 |
| custom | 40.00 | 30.00 | 20.00 | -10.00 | -10.00 |
| format | 56.04 | 65.93 | 70.33 | +9.89 | +4.40 |
| ratio | 27.94 | 30.88 | 17.65 | +2.94 | -13.24 |
| repeat | 0.00 | 11.11 | 0.00 | +11.11 | -11.11 |
| sentence | 18.18 | 25.00 | 18.18 | +6.82 | -6.82 |
| words | 11.33 | 11.33 | 14.00 | 0.00 | +2.67 |

## Small-budget GEPA 多 seed 审计

现有 `20/20/50`、`max_metric_calls=120` 的 GEPA-Tiny 运行已经覆盖 optimizer
seed 0、1、2：

| Seed | Test score | Optimized program |
|---|---:|---|
| 0 | 44.0 | 完整 |
| 1 | 43.0 | 完整 |
| 2 | 43.0 | 完整 |

三个 seed 的最终 prompt 都独立出现了同一种核心偏置：

> 先逐字重复用户请求，再提供答案。

它们还共同强调输出格式检查，但没有稳定学出 P2 的字面格式、计数、禁止项优先级
清单。由此可见：

1. small-budget GEPA 的 test 提升跨 optimizer seed 稳定。
2. 学出的 prompt bias 也跨 seed 稳定。
3. 该稳定偏置不是当前机制实验中表现最好的 P2 规则。
4. 小 split 上的正向分数不能证明 GEPA 稳定发现了可迁移的 hard-constraint 原理。

## 当前研究判断

DashScope Qwen3 有能力通过人工 instruction 显著恢复 IFBench 分数；MHC 的 +3.41
证明这一点。P2 进一步高出 MHC 0.85，说明原 GEPA prompt 与约束优先规则存在互补，
但不同 group 的方向并不一致。

当前最值得检验的假设是：

> GEPA 在小预算、小验证集上容易稳定学习到表面上高收益、但未必跨 split 或全量
> IFBench 可迁移的 prompt 模式；显式约束优先级可以改善这种搜索偏置，但仍需要
> full-budget 多 seed 验证。
