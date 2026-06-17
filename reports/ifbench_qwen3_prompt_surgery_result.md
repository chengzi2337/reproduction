# IFBench/Qwen3 GEPA Prompt Surgery 机制消融结果

## 结论

在 `DashScope/Qwen3 paper-adapted cloud-low-concurrency` 路线上，原始 GEPA program 的确定性回放分数为 35.20。仅在原 GEPA instruction 后追加“硬约束优先级”规则的 P2 变体达到 38.61，较确定性 Baseline 提升 4.26 分，较原始 GEPA 提升 3.41 分。

这个结果支持一个明确的研究假设：GEPA 在 IFBench 上的效果不仅取决于是否进行了 prompt optimization，还高度取决于最终 prompt 是否把字面格式、计数和禁止项置于解释性、完整性与帮助性偏好之前。

P2 的 38.61 与原论文 Figure 9(b) 中 Qwen3/IFBench GEPA 的约 38.6 非常接近，但不能据此称为 strict paper reproduction。当前结果仍使用 DashScope 云 API、temperature=0、max_tokens=8192 和本地 provider adaptation。

## 实验设置

- Benchmark：IFBench，test 294 条。
- Program：官方 artifact 的 `IFBenchCoT2StageProgram`。
- Source program：完整 GEPA run 保存的 optimized program。
- Provider：DashScope OpenAI-compatible API。
- 模型：Qwen3-8B 云 API。
- 并发：1。
- temperature：0。
- top_p：0.95。
- max_tokens：8192。
- Metric、split 和 program 结构保持不变。
- P1/P2/P3 仅修改两个 predictor 的 instruction。

## 总体结果

| 变体 | 改动 | 分数 | 相对 Baseline | 相对原 GEPA |
|---|---|---:|---:|---:|
| Baseline | 原始 program | 34.35 | 0.00 | -0.85 |
| 原 GEPA | 原 optimized program | 35.20 | +0.85 | 0.00 |
| P1 | 移除长回答、至少三句、结构化和 step-by-step 倾向 | 37.07 | +2.72 | +1.87 |
| P2 | 保留原 prompt，追加 hard-constraint priority | **38.61** | **+4.26** | **+3.41** |
| P3 | P1 去偏 + hard-constraint priority | 34.18 | -0.17 | -1.02 |

所有变体均完成 294/294 条评测。P2、P3 的 parse failure 和 provider rejection 均为 0。

## 分组结果

| 组别 | Baseline | 原 GEPA | P1 | P2 | P3 |
|---|---:|---:|---:|---:|---:|
| count | 45.28 | 40.57 | 34.91 | **50.94** | 36.79 |
| custom | **40.00** | 0.00 | 30.00 | 20.00 | 0.00 |
| format | 56.04 | 66.48 | 64.84 | **70.33** | 62.09 |
| ratio | **27.94** | 20.59 | 26.47 | 17.65 | 26.47 |
| repeat | 0.00 | 0.00 | 11.11 | 0.00 | **11.11** |
| sentence | 18.18 | 29.55 | **34.09** | 18.18 | 18.18 |
| words | 11.33 | 10.67 | **14.67** | 14.00 | 14.00 |

## 机制解释

P1 表明，删除“至少三句”“结构化语言”“step-by-step”等通用质量偏好，可以显著减少 IFBench 硬约束与帮助性 prompt 之间的冲突。

P2 的提升主要来自 count 和 format。它没有删除原 GEPA prompt，而是明确规定：精确格式、计数、禁止项优先于解释质量、完整性和帮助性。这说明原 GEPA prompt 并非整体无效，而是缺少稳定的约束优先级。

P3 没有叠加收益，反而下降到 34.18。这说明“删除通用质量偏好”和“追加硬约束优先级”不是可简单相加的独立改进。P1 的极简倾向与 P2 的检查清单叠加后，可能改变了二阶段 program 的生成与修正分工，导致 count、custom 和 format 回落。

## 研究意义

这组结果比单纯报告“GEPA 是否提升”更有研究价值：

1. GEPA 的平均收益可能掩盖 prompt-level constraint conflicts。
2. 同一个 optimized program 仅改变 instruction priority，就能从 35.20 变为 38.61。
3. 约束优先级是可解释、可审计、可消融的机制变量。
4. 改进并非单调：P3 证明更多约束文本不必然更好。

下一步应对 P2 做多次 deterministic replay、temperature=0.6 重复回放和多 seed 验证，再决定是否进入 full-budget 多 seed GEPA。

## 已知限制

- 不是 Arbor/local Qwen strict reproduction。
- DashScope 模型服务版本无法锁定到论文发布时快照。
- temperature=0 与论文配置 temperature=0.6 不同。
- max_tokens=8192，不是 strict 16384。
- 当前 P1/P2/P3 各只有一次完整 deterministic replay。
- finish_reason 尚未由当前 runner 捕获。
