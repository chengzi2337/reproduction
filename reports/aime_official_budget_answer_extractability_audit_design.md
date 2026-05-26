# AIME official_budget answer extractability 只读审计设计

## 设计目标

本审计用于解释 official score 的组成，而不是替换 official score。

核心问题：

```text
official_score = reasoning / task behavior + output-protocol adherence
```

逐题样例显示，seed prompt 已要求 `### <answer>`，但模型经常输出 `\boxed{...}`。这会让一些数值正确的回答在 official evaluator 下得 0。因此需要一个只读诊断，把 official score 中的格式损失与更可能的解题错误拆开看。

## 审计边界

- 不调用模型；
- 不调用 API；
- 不调用 GEPA；
- 不运行新实验；
- 不修改 optimizer；
- 不修改 evaluator；
- 不修改已有 official results；
- 不提交 outputs；
- 不把 relaxed score 写成 official score。

## 输入 artifacts

只读使用 5 个 official_budget run 的：

```text
per_example_eval.jsonl
```

每条记录应包含：

- `sample_id`
- `prompt_version`
- `question`
- `prediction`
- `gold`
- `score`
- `error`
- `attempt_count`

## 分类定义

对每条逐题记录生成如下诊断分类：

- `official_correct`: official score 为 1。
- `format_loss`: official score 为 0，但从 prediction 中保守提取的最终答案与 gold 一致。
- `reasoning_error`: official score 为 0，且可提取答案与 gold 不一致。
- `empty_or_invalid`: official score 为 0，且 prediction 为空或无法提取答案。

## 答案提取规则

提取器只做保守诊断：

1. 优先提取 `### 70` 这类 official protocol 答案；
2. 其次提取 `\boxed{70}`；
3. 再尝试提取 `Final answer: 70` 或 `answer is 70`；
4. 无法提取则归为 `empty_or_invalid`。

本审计只面向当前 AIME artifacts 中的整数答案，不声称覆盖所有数学表达式。

## 诊断指标

每个 seed、每个 prompt_version 输出：

- `official_score`
- `relaxed_extractable_score`
- `format_loss_count`
- `reasoning_error_count`
- `empty_or_invalid_count`
- `relaxed_minus_official`

其中：

```text
relaxed_extractable_score = (official_correct + format_loss) / examples
```

## 结论边界

可以写：

- official score 是当前 GEPA/AIME evaluator 下的正式任务分数；
- relaxed score 是 diagnostic only；
- seed prompt 的 format loss 明显多于 optimized prompt；
- observed score gain 不能解释为 pure reasoning improvement。

不能写：

- relaxed score 是 official GEPA score；
- relaxed score 可以替代 official score；
- 所有提升都来自格式；
- 所有提升都来自推理能力；
- 这是新实验或新性能评估。
