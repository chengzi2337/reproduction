# Stage 2D Phase 2 Official-Contract Prompt Adaptation Result

## 定位

- `Stage 2D Phase 2: official-contract prompt adaptation diagnostic`
- `not_gepa_path = true`
- `not_baseline = true`
- `not_pilot = true`
- `not_performance_claim = true`
- `normalized_score_is_diagnostic_only = true`

## 运行配置

- provider：`mimo`
- model：`mimo-v2.5-pro`
- api_base：`https://token-plan-cn.xiaomimimo.com/v1`
- sample_count：`5`
- thinking：`disabled`
- max_completion_tokens：`2048`
- timeout：`120.0`
- max_workers：`3`
- execute_diagnostic：`True`
- 输出目录：`outputs\stage2d_official_contract_prompt_adaptation_diagnostic\20260520T231315+0800`

## 边界声明

- 本阶段未调用 GEPA optimizer。
- 本阶段未运行 GEPA smoke。
- 本阶段未进入 pilot。
- 本阶段未修改 official evaluator 或 optimizer。
- `official_score` 与 `normalized_score` 分开记录；`normalized_score` 仅为诊断字段。

## 结果摘要

- 是否存在同时通过 direct SDK 与 LiteLLM 的 prompt variant：`False`
- 通过 variant：`[]`

### Variant D：exact_substring_final_answer_only

- direct_sdk：
  - official_evaluator_compatible：`0 / 5`
  - strict_regex_match_###_integer：`3 / 5`
  - first_line_matches_###_integer：`3 / 5`
  - contains_xml_tag_placeholder：`0`
  - contains_markdown_heading_misuse：`0`
  - finish_reason = length：`0`
  - pass_gate：`False`
- litellm：
  - official_evaluator_compatible：`0 / 5`
  - strict_regex_match_###_integer：`3 / 5`
  - first_line_matches_###_integer：`3 / 5`
  - contains_xml_tag_placeholder：`0`
  - contains_markdown_heading_misuse：`0`
  - finish_reason = length：`0`
  - pass_gate：`False`
- both_paths_pass_gate：`False`

### Variant E：final_answer_only

- direct_sdk：
  - official_evaluator_compatible：`1 / 5`
  - strict_regex_match_###_integer：`2 / 5`
  - first_line_matches_###_integer：`0 / 5`
  - contains_xml_tag_placeholder：`0`
  - contains_markdown_heading_misuse：`0`
  - finish_reason = length：`1`
  - pass_gate：`False`
- litellm：
  - official_evaluator_compatible：`1 / 5`
  - strict_regex_match_###_integer：`2 / 5`
  - first_line_matches_###_integer：`0 / 5`
  - contains_xml_tag_placeholder：`0`
  - contains_markdown_heading_misuse：`0`
  - finish_reason = length：`2`
  - pass_gate：`False`
- both_paths_pass_gate：`False`

### Variant F：official_evaluator_contract_explicit

- direct_sdk：
  - official_evaluator_compatible：`1 / 5`
  - strict_regex_match_###_integer：`2 / 5`
  - first_line_matches_###_integer：`0 / 5`
  - contains_xml_tag_placeholder：`0`
  - contains_markdown_heading_misuse：`1`
  - finish_reason = length：`3`
  - pass_gate：`False`
- litellm：
  - official_evaluator_compatible：`1 / 5`
  - strict_regex_match_###_integer：`4 / 5`
  - first_line_matches_###_integer：`0 / 5`
  - contains_xml_tag_placeholder：`0`
  - contains_markdown_heading_misuse：`2`
  - finish_reason = length：`1`
  - pass_gate：`False`
- both_paths_pass_gate：`False`

## 结论

- 没有 prompt variant 同时满足 direct SDK 与 LiteLLM 的 `5/5 official_evaluator_compatible` 通过标准；只能写成 partial improvement 或不稳定，不得进入 GEPA adapted smoke。
- 本结果不是 MiMo baseline，不是 strict official path，不是性能结论。

## 关键观察

- Variant D 说明“更像 official contract 的格式约束”并不等于“会产生正确答案”：
  - 两条路径都有 `3 / 5 strict_regex_match_###_integer`
  - 但 `official_evaluator_compatible = 0 / 5`
  - 说明不少输出虽然长得像 `### N`，但 `N` 本身是错的
- Variant E / F 各自只达到 `1 / 5 official_evaluator_compatible`
  - 仍然存在 `finish_reason = length`
  - Variant F 仍出现 `### Step 1` 类 heading misuse
- 因此当前 blocker 不能再简化为“只差 prompt 更严一点”，而是：
  - official output contract adherence 仍不稳定
  - 长答案/截断仍存在
  - 答案正确性本身也没有被 prompt-only 方案稳定保住

## 下一步建议

- 不进入路线 B，不做 adapted GEPA smoke。
- 不继续堆 prompt-only 变体。
- 按长期规划，优先考虑两条收束方向之一：
  - 路线 C：停止 MiMo prompt-only 路线，回到 reproduction 主线与总结收束
  - 路线 D：新增 response normalizer / answer extraction diagnostic，只产出 `normalized_score`

