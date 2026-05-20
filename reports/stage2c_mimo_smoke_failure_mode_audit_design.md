# Stage 2C MiMo Smoke Failure-Mode Audit Design

## 定位

本文档只定义 `Stage 2C: MiMo explicitly controlled-generation GEPA path` 的 smoke 失败模式审计方案。

- 它不是新的 GEPA 实验。
- 它不是 pilot。
- 它不是性能实验。
- 它不改 `GEPA optimizer`、`DefaultAdapter`、evaluator。
- 它不触发新的 `gepa.optimize()` 调用。

本文档的唯一目标是解释：为什么 `Stage 2C controlled-generation GEPA smoke passed` 的同时，`best_score = 0.0`。

## 背景

当前已知事实：

- Stage 2A strict default path 在真实 AIME 题面上 blocked。
- Stage 2B 已证明：在 `thinking.disabled` 与 `max_completion_tokens = 512` 条件下，MiMo 能对真实 AIME 单样本返回非空 `content`。
- Stage 2C sanity 已通过一次最小闭环。
- Stage 2C smoke 已通过一次 `max_metric_calls = 10` 的 execution-stability 闭环。
- 本次 smoke 的结果摘要为：
  - `path_type = stage2c_mimo_controlled_generation_gepa_smoke`
  - `execution_completed = true`
  - `total_metric_calls = 45`
  - `num_candidates = 1`
  - `num_full_val_evals = 1`
  - `best_score = 0.0`

因此，当前问题已经不是“能不能跑完”，而是“为什么能跑完但得分为 0.0”。

## 审计边界

本次 audit 只允许做以下事情：

- 读取已有 smoke 输出目录中的本地文件。
- 读取已有 `stage2c_smoke_input_snapshot.json` 与 `stage2c_smoke_result_summary.json`。
- 读取 `generated_best_outputs_valset/task_*/iter_0_prog_0.json` 中保存的样本级回答。
- 检查内容是否为空、是否被截断、是否包含 `### <answer>` 最终格式。
- 检查当前 smoke 运行是否只完成了一轮 baseline-like valset 评估。

本次 audit 明确不做以下事情：

- 不运行新的 `gepa.optimize()`
- 不重跑 smoke
- 不进入 pilot
- 不做 saved prompt eval
- 不改 `thinking.disabled`
- 不改 `max_completion_tokens = 512`
- 不把 `reasoning_content` 手工拼进 `content`
- 不把审计结果写成 MiMo 性能结论

## 可用证据

当前 smoke 输出目录中，已确认至少有以下材料：

- `stage2c_smoke_input_snapshot.json`
- `stage2c_smoke_result_summary.json`
- `generated_best_outputs_valset/task_*/iter_0_prog_0.json`
- `notes.md`

其中，`generated_best_outputs_valset/task_*/iter_0_prog_0.json` 已包含 `full_assistant_response` 字段，因此当前 audit 具备最低限度的样本级输出审查能力。

这意味着本次 audit 可以直接回答以下一部分问题：

1. `content` 是否非空。
2. 回答是否明显被截断。
3. 是否出现 `### <answer>` 最终格式。
4. 是否存在“长推理正文 + 无最终答案标记”的失败模式。

但当前证据仍然不足以直接回答以下问题：

1. 某个样本的最终错误是“数值答案错”还是“格式解析错”。
2. evaluator 对每个样本的逐项判分细节是什么。
3. GEPA 内部 candidate 演化中间态是否存在质量改善但未保留到最终摘要。

因此，本次 audit 的目标是先把 `0.0` 的原因收敛到“格式失败 / 截断失败 / 内容质量失败 / 证据不足”中的一个或多个类别，而不是过度解释模型能力。

## 核心审计问题

本次 audit 必须回答以下问题：

1. `best_score = 0.0` 更像是格式问题，还是答案质量问题。
2. `full_assistant_response` 是否普遍非空。
3. 输出是否包含 `### <answer>`。
4. 输出是否出现明显截断。
5. `thinking.disabled` 是否导致回答过短或直接失去数学推理链路。
6. `max_completion_tokens = 512` 是否可能过低，导致回答在接近最终答案前被截断。
7. 本次 smoke 是否实际上只完成了单 candidate 的 valset 评估，而未形成有效 prompt 优化。

## 推荐审计流程

### 第 1 步：运行级事实确认

从 `stage2c_smoke_result_summary.json` 中确认：

- `execution_completed = true`
- `num_candidates = 1`
- `num_full_val_evals = 1`
- `best_score = 0.0`

如果这些字段成立，则先把当前 run 定义为：

`可执行性 smoke 通过，但未显示有效 prompt 优化收益`

### 第 2 步：样本输出抽样

优先抽查以下样本：

- `task_0`
- `task_1`
- `task_2`
- 以及任意 2-3 个后续样本

对每个样本记录：

- `full_assistant_response` 是否为空
- 是否包含 `###`
- 是否包含 `### <answer>` 风格的最终答案行
- 文本是否在明显未完结处停止
- 是否呈现“长正文 + 无最终格式”模式

### 第 3 步：失败模式归类

建议使用以下四类标签：

- `format_missing`
  - 有正文，但没有 `### <answer>` 最终格式
- `truncated_before_final`
  - 有正文，但在明显未结束处截断
- `content_present_but_answer_wrong`
  - 有最终格式，但内容明显错误
- `insufficient_evidence`
  - 现有材料不足以判断

同一个 run 可以命中多个标签，但必须给出主标签。

## 当前最可能的失败模式假设

基于已经看到的 `task_0` 原始输出样本，当前最优先的假设是：

- `truncated_before_final`
- `format_missing`

也就是：

- MiMo 在 `thinking.disabled + max_completion_tokens = 512` 条件下可以产出非空数学正文；
- 但正文可能在到达最终 `### <answer>` 之前被截断；
- 从而 evaluator 拿不到可解析的最终答案；
- 最终体现为 smoke 得分 `0.0`。

这个假设目前仍然只是审计优先方向，不是最终结论。正式 audit 必须在更多样本上复核。

## 审计完成后的分叉规则

### 分叉 A：主因是 `format_missing`

如果多数样本都有正文，但普遍缺失 `### <answer>`，则说明：

- 当前 Stage 2C 更像是格式可达性不足；
- 下一步应优先讨论 prompt 约束或输出后处理审计方案；
- 不应直接进入 pilot。

### 分叉 B：主因是 `truncated_before_final`

如果多数样本被截断，则说明：

- `max_completion_tokens = 512` 很可能过低；
- 下一步应先做参数调整设计；
- 不应直接进入 pilot。

### 分叉 C：主因是 `content_present_but_answer_wrong`

如果输出完整且有最终格式，但答案普遍错误，则说明：

- 当前 controlled-generation 路径虽然可执行，但质量不足；
- 下一步仍应先做参数调整或样本级质量诊断设计；
- 不应直接进入 pilot。

### 分叉 D：证据不足

如果现有文件仍不足以支撑判断，则必须明确写出：

`当前 smoke 只支持执行层判断，不足以解释 0.0 的具体原因。`

此时下一步只能新增更细的样本级 audit 入口，仍然不进入 pilot。

## 当前结论约束

在 audit 真正执行前，关于这次 smoke，当前只允许写：

- `Stage 2C controlled-generation GEPA smoke passed`
- `best_score = 0.0` 是 smoke-run artifact / warning signal
- 当前需要先做 failure-mode audit

当前明确不允许写：

- `MiMo baseline`
- `MiMo pilot`
- `MiMo performance`
- `MiMo outperforms DeepSeek`
- `Stage 2C already ready for pilot`

## 下一步

当前正确顺序应为：

1. 封存 smoke result checkpoint。
2. 执行本 failure-mode audit。
3. 基于 audit 结论决定是否先做参数调整设计。
4. 在 audit 或参数调整结论出现前，不进入 pilot。
