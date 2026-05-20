# Stage 2D MiMo Output-Protocol Adaptation Design

## 定位

Stage 2D 定义为：

- `Stage 2D: MiMo output-protocol adaptation diagnostic`

它的目标不是提升模型分数，而是回答一个更基础的问题：

> 当前 MiMo 输出里，哪些样本已经有人类可提取答案，但由于不满足 official evaluator 的输出协议而被记成 0 分？

## 非目标声明

Stage 2D 明确不是：

- strict path
- Stage 2C pilot
- 性能实验
- baseline 建立
- GEPA official result

Stage 2D 也不会：

- 修改 official evaluator
- 修改 GEPA optimizer
- 修改 Stage 1 历史结果

## 背景动机

当前已知事实：

1. Stage 2A 已证明 MiMo strict default generation 在真实 AIME prompt 下会 `HardTimeout`。
2. Stage 2B 已证明在 controlled-generation 条件下，MiMo 单样本可以返回非空 `content`。
3. Stage 2C sanity / smoke 已证明 MiMo controlled-generation GEPA 执行闭环可跑通。
4. Stage 2C smoke `best_score = 0.0`，failure-mode audit 已确认主要问题是：
   - `format_missing`
   - `output_protocol_violation`
5. 参数调整到 `max_completion_tokens = 2048` 后，硬截断已缓解，但仍然不能稳定输出 evaluator 需要的精确 `### <integer>`。
6. prompt-first 三种变体也没有稳定解决格式问题。

因此当前最合理的下一步不是继续跑 GEPA，而是先把：

- `official_score`
- `normalized_score`

这两种概念明确分开。

## Stage 2D 的两个子任务

### 1. official evaluator format contract audit

目的：

- 尽量定位 GEPA AIME 官方 metric / parser
- 如果能直接调用官方 evaluator，就对 synthetic responses 做真实判分
- 如果不能，就明确 `evaluator_discovery_failed = true`

当前预期最重要的问题是：

- official evaluator 到底要求什么？
- `### <answer>\n72\n</answer>` 这种语义上可提取答案的文本，会不会被 official evaluator 记分？

### 2. existing outputs answer-extractability audit

目的：

- 只读审计已有 Stage 2C smoke / prompt-first 输出
- 区分：
  - official evaluator 兼容
  - relaxed human extractable
- 解释当前 `best_score = 0.0` 到底是“没有答案”还是“答案存在但协议违规”

## Official Score vs Normalized Score

Stage 2D 必须明确区分两种分数：

### official_score

- 含义：official evaluator 的真实判分结果
- 来源：GEPA AIME 默认 evaluator / metric 契约
- 可写入：`official_metric_score`
- 不允许改写

### normalized_score

- 含义：只为 Stage 2D 诊断定义的“语义上可由人类放松提取答案”的辅助分数
- 来源：Stage 2D 自定义 relaxed extractability 规则
- 只允许用于说明：
  - 模型可能已经给出了语义答案
  - 但没有满足 official output protocol

`normalized_score` 不能写成：

- GEPA official score
- baseline score
- smoke score
- pilot score

## 预期输出

Stage 2D 只允许产出以下类型的结论：

- official evaluator contract 是什么
- 哪些 response official pass / fail
- 哪些 response 语义可提取但 official fail
- 当前主要 failure mode 是什么

Stage 2D 不允许产出以下类型的结论：

- MiMo pilot ready
- MiMo performance improved
- MiMo baseline established
- GEPA original reproduction succeeded

## 成功标准

Stage 2D 成功标准不是“分数变高”，而是：

1. 能明确说明 official evaluator 的格式契约；
2. 能把 `official_score` 与 `normalized_score` 明确隔离；
3. 能对已有输出给出可审计的 failure-mode 分类；
4. 能找到至少一个“语义上有答案但 official fail”的代表性样本；
5. 不调用模型，不调用 `gepa.optimize()`。

## 失败标准

以下任一情况视为 Stage 2D 未完成：

1. 无法说明 official evaluator 契约，却擅自输出官方结论；
2. 把 relaxed extractability 写成 official result；
3. 修改 GEPA evaluator 或 optimizer；
4. 为了 Stage 2D 审计再次运行 GEPA 或模型请求。
