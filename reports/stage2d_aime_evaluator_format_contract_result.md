# Stage 2D AIME Evaluator Format Contract Result

## 结论摘要

Stage 2D 已确认：

1. GEPA AIME 默认使用的 official evaluator 可以被定位；
2. AIME 官方 answer contract 是精确字符串 `### 72` 这种形式；
3. official metric 的核心契约不是语义抽取，而是**字符串包含匹配**；
4. 因此 `### <answer>\n72\n</answer>` 这类文本即使人类一眼能读出答案，也会被 official evaluator 记为 `0.0`。

## 证据来源

- official evaluator：
  - `gepa.adapters.default_adapter.default_adapter.ContainsAnswerEvaluator`
- AIME answer contract：
  - `gepa.examples.aime.init_dataset`

### official evaluator 核心逻辑

`ContainsAnswerEvaluator` 的实际逻辑是：

```python
is_correct = data["answer"] in response
score = 1.0 if is_correct else self.failure_score
```

### AIME ground truth 核心逻辑

`gepa.examples.aime.init_dataset()` 中，answer 被构造成：

```python
"### " + str(x["answer"])
```

这说明 official contract 实际期待的是：

```text
### 72
```

而不是：

```text
### <answer>
72
</answer>
```

## Synthetic responses 审计结果

### official pass

- `### 72`
- `解题过程 + 最后一行 ### 72`

### official fail，但 normalized / relaxed 可提取

- `### <answer>\n72\n</answer>`
- `### <answer> 72`
- `The answer is 72.`
- `Final answer: 72.`
- `\boxed{72}`
- `### Step 1 + 解题过程 + Final answer: 72`

## 结果解释

当前最关键的判定是：

- `official_score`
  - 只代表 official evaluator 是否认可
- `normalized_score`
  - 只代表在 Stage 2D relaxed 规则下，人类或宽松规则是否能提取出语义答案

这两者必须严格分开。

例如：

```text
response = "### <answer>\n72\n</answer>"
official_score = 0.0
normalized_score = 1.0
```

这只能说明：

> 该输出语义上可提取答案，但不满足 official output protocol。

不能说明：

> GEPA official score 应该算 1.0

## 当前意义

这份审计结果把当前 Stage 2C / Stage 2D 的核心矛盾彻底说清楚了：

- 当前 MiMo 不是“没有答案”
- 而是“答案经常不按 official evaluator 需要的协议出现”

因此当前 blocker 可以更准确地写成：

- `output_protocol_violation`
- `format_missing relative to official evaluator contract`

## 边界声明

- 本审计不调用模型
- 本审计不调用 `gepa.optimize()`
- 本审计不是性能实验
- 本审计不修改 official evaluator
- 本审计不把 `normalized_score` 写成 official score
