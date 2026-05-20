# Stage 2D MiMo Existing Outputs Answer-Extractability Result

## 定位

本结果只属于：

- `Stage 2D output-protocol adaptation diagnostic`
- `not performance claim`
- `not GEPA official score revision`

本审计：

- 只读已有 Stage 2C smoke / prompt-first 输出
- 不调用模型
- 不调用 `gepa.optimize()`

## 审计范围

### Stage 2C smoke

- 输出来源：`generated_best_outputs_valset/task_*/iter_0_prog_0.json`
- 内容完整性：完整正文

### Stage 2C prompt-first

- 输出来源：`stage2c_prompt_first_results.json`
- 内容完整性：仅 `content_preview`
- 因此这部分只能作为 preview 级别证据，不等价于完整正文审计

## 汇总结果

### Stage 2C smoke

- 总样本：`45`
- `official_evaluator_compatible = 0`
- `relaxed_human_extractable = 0`
- `output_protocol_violation = 9`
- `markdown_heading_misuse = 9`
- `final_answer_missing = 45`

解释：

- smoke 输出里，所有样本在 official evaluator 下都不兼容；
- 当前没有发现“完整 smoke 正文里已经给出可宽松提取的最终整数答案”的样本；
- 主要 failure mode 是：
  - 长过程正文
  - `### Step 1` 这类 Markdown 标题误用
  - 没有真正落到最终答案协议

### Stage 2C prompt-first（preview 级）

- 总 case：`18`
- `official_evaluator_compatible = 0`
- `relaxed_human_extractable = 3`
- `output_protocol_violation = 3`
- `xml_tag_placeholder_misuse = 3`
- `final_answer_missing = 15`

解释：

- prompt-first 里已经出现了“语义上有人类可提取答案，但 official evaluator 仍给 0”的代表性 case；
- 这些 case 的主模式不是空输出，而是：
  - `### <answer>\n72\n</answer>`
  - `### <answer>\n685`
  - `### <answer>\n2688\n</answer>`

## 代表性失败样本

### Case 1：semantic_answer_present = true，但 evaluator_format_match = false

artifact:

- `stage2c_prompt_first_direct_sdk_preview`
- `Variant B: first-line final answer`

response preview:

```text
### <answer>
20
</answer>
```

结论：

- `relaxed_human_extractable = true`
- `relaxed_extracted_answer = 20`
- `official_evaluator_compatible = false`
- failure mode = `xml_tag_placeholder_misuse`

### Case 2：Markdown heading 误用

artifact:

- `stage2c_smoke`

response preview:

```text
### Step 1: Simplify ...
```

结论：

- `official_evaluator_compatible = false`
- `relaxed_human_extractable = false`
- failure mode = `markdown_heading_misuse`

## 当前总判断

Stage 2D 当前已经把已有输出问题分成两类：

### 1. 真正没有最终答案

- smoke 全量正文里最常见
- 表现为：
  - 长过程
  - 中途标题
  - 没有最后的 `### 72`

### 2. 语义上已有答案，但协议违规

- prompt-first 里已有明确样本
- 表现为：
  - `### <answer>\n72\n</answer>`
  - 这类输出 human-readable，但 official evaluator 不认

## 结论

当前最准确的结论是：

> Stage 2C 当前的 failure mode 不应再只写成“没答出来”或“分数低”。  
> 更准确的说法是：一部分样本是 `final_answer_missing`，另一部分样本已经出现 `semantic_answer_present`，但因为 `output_protocol_violation` 而无法被 official evaluator 计分。

## 边界声明

- 本结果不是 baseline
- 本结果不是 pilot 结论
- 本结果不是 MiMo 性能判断
- 本结果不修改 official score
- 其中 `relaxed_human_extractable / normalized_score` 只用于 Stage 2D 诊断
