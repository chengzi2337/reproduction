# GEPA 在 IFBench/Qwen3 上的样本级退化现象研究札记

生成时间：2026-06-10

## 定位

本文是基于 `DashScope/Qwen3 paper-adapted cloud-low-concurrency` 复现实验得到的研究札记，目的不是宣称已经完成 strict paper reproduction，而是把当前一条完整 IFBench 复现实验中的异常现象整理成可进一步验证的论文研究方向。

当前证据应被视为 pilot evidence。它足以提出研究假设和后续实验计划，但不足以单独支撑最终论文结论。

## 核心研究问题

GEPA 这类 prompt optimizer 在优化平均验证集收益时，是否可能学习到一种通用写作或解释偏置，从而提升部分宽泛格式任务，却损害需要精确可验证约束的任务子类？

更具体地说：

> Prompt optimizer 的整体平均分是否会掩盖 group-wise regression，尤其是在 `count`、`ratio`、`custom`、`sentence` 等严格约束子任务上？

## 当前复现实验事实

实验口径：

- benchmark：IFBench
- program：`IFBenchCoT2StageProgram`
- model route：`qwen3-8b-dashscope-paper-adapted`
- optimizer：Baseline 与 GEPA
- test size：294
- seed：0
- runtime：DashScope 云 API 适配路线，不是 strict Arbor runtime

最终结果：

| 项目 | Baseline | GEPA |
| --- | ---: | ---: |
| score | 36.56 | 35.88 |
| metric sum | 107.5 / 294 | 105.5 / 294 |
| test rows | 294 / 294 | 294 / 294 |
| missing idx | 0 | 0 |
| duplicate idx | 0 | 0 |

论文 Figure 9(b) 中 IFBench/Qwen3 的手工读数约为 Baseline `36.9`、GEPA `38.6`、提升 `+1.7`。当前 DashScope adapted 复现没有复现出该正向提升。

## 样本级差分

按 `idx_in_split` 对齐 Baseline 与 GEPA 的 `metric_output` 后得到：

| 类别 | 数量 | 分数贡献 |
| --- | ---: | ---: |
| GEPA 退化样本 | 30 | -27.5 |
| GEPA 改善样本 | 28 | +25.5 |
| 持平样本 | 236 | 0 |
| 净差 | - | -2.0 |

这说明 GEPA 不是整体崩溃，而是改善与退化几乎互相抵消，最终略低于 Baseline。

## 子任务分组现象

按 instruction 大类聚合后，GEPA 的净变化呈现明显异质性：

| 指令大类 | 样本数 | 退化数 | 改善数 | 净变化 |
| --- | ---: | ---: | ---: | ---: |
| `count` | 59 | 9 | 6 | -3.0 |
| `ratio` | 44 | 5 | 1 | -3.0 |
| `custom` | 10 | 3 | 0 | -3.0 |
| `sentence` | 28 | 5 | 3 | -2.5 |
| `words` | 80 | 5 | 8 | +2.5 |
| `format` | 96 | 7 | 16 | +8.5 |

初步模式是：GEPA 在一部分格式任务上确实有收益，但在精确计数、比例、定制规则和句子序列规则上出现更明显退化。

## 典型退化机制

### 1. 输出变长导致精确计数失败

`idx=20` 要求响应中包含 exactly 3 numbers。Baseline 输出 `3 stakeholders, 50% involvement, 10 centers.`，满足 3 个数字。GEPA 输出以 `3 numbers: 1... 2... 3...` 开头，并继续扩写解释，导致数字数量超标，metric 变为 0。

该现象说明：GEPA 的“更完整解释”倾向会破坏 exact-count constraints。

### 2. 改写用户指定分隔符

`idx=85` 要求列表项之间使用字面量 `SEPARATOR`，Baseline 使用该分隔符，GEPA 改成分号。语义上答案仍合理，但 IFBench metric 只接受指定格式，因此 GEPA 得 0。

该现象说明：通用自然表达偏好会覆盖用户给定的机器可检验格式。

### 3. 生成元解释而不是目标格式

`idx=94` 要求 each word on a new line。Baseline 逐词换行。GEPA 输出解释性句子，说明自己遵守了请求，但没有真正按词换行。

该现象说明：优化后的 prompt 可能诱导模型生成 compliance explanation，而不是执行 compliance behavior。

### 4. 过度模板化或重复导致序列规则失控

`idx=219` 要求上一句最后一个词成为下一句第一个词。GEPA 开头满足规则，但后续生成极长重复链，输出形态失控，最终失分。

该现象说明：对于递归式或链式约束，过长输出会累积错误风险。

## 与 optimized program 的关系

从 GEPA 最终 `optimized_program/program.pkl` 中可提取到可读指令片段，显示最终 program 包含更强的通用策略倾向：

- 提供清晰、简洁的解释。
- 响应至少包含 3 句。
- 遵循格式和伦理要求。
- 在需要时使用结构化标题。
- 对数学或逻辑问题提供 step-by-step reasoning。
- 对多部分任务拆分成清晰小节。

这些策略对一般问答可能有利，但和 IFBench 的若干硬约束存在冲突。例如“至少 3 句”会天然伤害短答、exact-count、低停用词比例和 no-whitespace 等约束。

## 研究假设

### H1：平均分优化掩盖子类退化

GEPA 的总体优化目标可能提升部分任务类型，但同时使另一部分 instruction group 退化。只报告 overall score 会隐藏 group-wise regression。

### H2：通用写作偏置与硬约束冲突

优化后的 prompt 若学到“解释更充分、结构更清晰、回答更完整”的通用策略，会损害精确计数、比例、序列和字面格式约束。

### H3：验证集选择驱动 prompt drift

若验证集中的收益样本偏向宽泛格式或解释型任务，GEPA 可能选择对这些样本有利、但对 hard-constraint group 不利的 prompt。

### H4：constraint-aware optimizer 可以降低退化

如果在优化目标中加入 group-aware weighting、worst-group constraint、hard-constraint validator 或 regression penalty，可能保留 GEPA 的收益同时减少子类退化。

## 后续实验计划

### 多 seed 验证

至少运行 3 到 5 个 seed，报告 overall score 与 group-wise score。关键观察不是单次 GEPA 是否赢，而是退化分布是否稳定。

### 多 benchmark 验证

除 IFBench 外，应加入至少一个严格指令遵循 benchmark 和一个非严格生成类 benchmark，判断退化现象是否是 IFBench 特例。

### Prompt ablation

对 GEPA optimized prompt 做消融：

- 移除“至少 3 句”。
- 移除伦理/负责 assistant 段落。
- 移除标题或结构化要求。
- 移除 step-by-step 倾向。
- 增加“短答优先，严格满足字面约束优先”。

比较 `count`、`ratio`、`custom`、`sentence` 组是否恢复。

### Group-aware optimization

设计约束感知变体：

- overall objective + worst-group penalty
- hard-constraint group reweighting
- validation regression guard
- per-instruction-type prompt routing
- prompt ensemble with constraint classifier

### 优化轨迹分析

记录每轮候选 prompt、valset 得分、test group-wise 得分和被选中原因，判断退化是在何时引入的，以及是否由少数验证样本驱动。

## 威胁有效性

- 当前结果基于 DashScope 云 API，不是 strict Arbor runtime。
- 当前只有 seed 0，不能排除随机性。
- 云 API 模型版本不可完全锁定。
- Provider rejection adaptation 可能影响优化轨迹。
- 当前人工归因来自可观察输出和 prompt 字符串，尚未完整回放 GEPA 优化轨迹。

## 潜在论文贡献

1. 提出 prompt optimizer 的 group-wise regression 问题。
2. 展示 overall score 可能掩盖 hard-constraint 子任务退化。
3. 给出 IFBench/Qwen3 上的复现型 pilot evidence。
4. 提出 constraint-aware prompt optimization 的实验框架。
5. 通过 prompt ablation 和优化轨迹分析解释退化机制。

## 当前结论

当前最稳妥的学术表述是：

> 在一条完整的 IFBench/Qwen3 DashScope adapted 复现实验中，GEPA 没有表现出论文读数中的整体提升。样本级分析显示，GEPA 的改善和退化几乎抵消，退化集中于精确计数、比例、定制和句子序列类约束。初步证据表明，GEPA 学到的通用解释/结构化提示可能与 hard-constraint instruction following 存在冲突。这一现象值得作为 prompt optimization 的 group-wise regression 问题进一步系统研究。
