# Stage 2D Phase 2 Official-Contract Prompt Adaptation Design

## 定位

本阶段属于：

- `Stage 2D Phase 2: official-contract prompt adaptation diagnostic`
- MiMo backend-substitution failure-mode study
- 非 GEPA 路径
- 非 baseline
- 非 pilot
- 非性能实验

目标是在不调用 `gepa.optimize()` 的前提下，使用 direct SDK 与 LiteLLM 小样本诊断，验证更明确的 prompt 是否能让 MiMo 稳定输出 official evaluator 接受的精确字符串：

```text
### N
```

其中 `N` 是 AIME 样本的最终整数答案。

## 背景

已封存的 Stage 2D 审计确认：

- GEPA AIME 默认 evaluator 为 `gepa.adapters.default_adapter.default_adapter.ContainsAnswerEvaluator`
- AIME answer contract 为 `"### " + str(x["answer"])`
- official contract 是字符串包含匹配：`data["answer"] in response`
- 因此 `### 72` 会 official pass，`### <answer>\n72\n</answer>` 会 official fail

Stage 2C prompt-first 诊断已显示，普通格式提示仍不能稳定产出 official evaluator 需要的精确 `### <integer>`。本阶段只验证更明确的 official contract prompt 是否能改善这一 failure mode。

## 非目标

本阶段不做以下事项：

- 不调用 `gepa.optimize()`
- 不运行 GEPA smoke
- 不进入 pilot
- 不修改 official evaluator
- 不修改 GEPA optimizer
- 不生成 baseline
- 不写性能结论
- 不把 `normalized_score` 写成 `official_score`
- 不与 Stage 1 DeepSeek strict result 做横向性能比较

## 固定参数

- provider：`mimo`
- model：`mimo-v2.5-pro`
- api_base：必须来自 `MIMO_API_BASE` 或 `--api-base`
- thinking：`disabled`
- max_completion_tokens：`2048`
- timeout：`120`
- sample_count：`5`
- data：真实 AIME val 样本
- 调用路径：
  - direct OpenAI-compatible SDK
  - LiteLLM `openai/mimo-v2.5-pro`

## Prompt 变体

### Variant D：exact-substring final answer only

```text
Solve the problem internally. Do not show your reasoning.

Your entire response must be exactly one line.
It must match this pattern:
### 123

Replace 123 with the final integer answer.
Do not write "<answer>".
Do not write XML tags.
Do not write explanations.
Do not write Markdown headings.
```

### Variant E：final answer only

```text
Compute the answer internally.

The first and only line of your response must be:
### N

where N is the final nonnegative integer answer.
Do not include any other text.
```

### Variant F：official evaluator contract explicit

```text
The grader only checks whether your response contains the exact string:
### N

where N is the final integer answer.

Your response must contain exactly one such line and no other "###" headings.

Example of valid output:
### 72
```

## 评价字段

每条调用结果记录以下字段：

- `content_nonempty`
- `finish_reason`
- `official_evaluator_compatible`
- `contains_exact_official_answer_string`
- `strict_regex_match_###_integer`
- `first_line_matches_###_integer`
- `contains_xml_tag_placeholder`
- `contains_markdown_heading_misuse`
- `relaxed_human_extractable`
- `normalized_extracted_answer`
- `official_score`
- `normalized_score`

其中：

- `official_score` 只表示 official contract 字符串包含匹配是否通过。
- `normalized_score` 只用于诊断 relaxed extraction，不是 GEPA official score。

## 通过标准

某个 prompt variant 只有同时满足以下条件，才允许进入后续 adapted GEPA smoke 讨论：

- direct SDK：`5 / 5 official_evaluator_compatible = true`
- LiteLLM：`5 / 5 official_evaluator_compatible = true`
- `finish_reason != length`
- `contains_xml_tag_placeholder = 0`
- `contains_markdown_heading_misuse = 0`

如果低于 `5 / 5`，只能写成 partial improvement，不得进入 GEPA adapted smoke。

## 输出资产

- 设计文档：`reports/stage2d_official_contract_prompt_adaptation_design.md`
- 诊断脚本：`scripts/stage2d_diagnose_official_contract_prompt_adaptation.py`
- 测试文件：`tests/test_stage2d_official_contract_prompt_adaptation.py`
- 结果报告：`reports/stage2d_official_contract_prompt_adaptation_result.md`
- 本地运行输出：`outputs/stage2d_official_contract_prompt_adaptation_diagnostic/`

## 验证计划

1. 运行 dry-run，确认不调用模型且生成输入快照。
2. 在 `MIMO_API_KEY` 与 `MIMO_API_BASE` 可用时执行小样本诊断。
3. 生成结果报告，只写 official / normalized 的诊断区分。
4. 运行：

```powershell
python -m compileall src scripts tests
pytest -q
```

5. 若模型调用失败或凭据不可用，结果报告必须明确写出失败原因，不得伪造通过结论。
