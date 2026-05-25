# AIME official_budget prompt length 只读审计设计

## 目标

本设计定义一个只读审计流程，用于分析 5 个既有 `AIME official_budget` run_dir 中，`optimized prompt` 相对 `seed prompt` 的长度增长与测试收益之间的关系。

本任务不是新实验，不调用模型，不调用 GEPA，不修改已有 run artifact。

## 输入范围

固定读取以下 5 个 run_dir：

| seed | run_dir |
|---:|---|
| 0 | `outputs/gepa_aime_official_budget_seed0/20260522T121001+0800` |
| 1 | `outputs/gepa_aime_official_budget_seed1/20260522T175103+0800` |
| 2 | `outputs/gepa_aime_official_budget_seed2/20260522T221654+0800` |
| 3 | `outputs/gepa_aime_official_budget_seed3/20260525T104154+0800` |
| 4 | `outputs/gepa_aime_official_budget_seed4/20260525T135207+0800` |

每个 run_dir 必须包含：

- `seed_prompt.json`
- `optimized_prompt.json`
- `gepa_result_summary.json`
- `saved_prompt_eval_summary.json`

如果任一 artifact 缺失、JSON 无法解析、字段缺失或 prompt artifact 结构不符合预期，脚本必须显式失败，不允许静默编造。

## 输出字段

每个 seed 输出以下字段：

- `seed`
- `run_dir`
- `seed_prompt_score`
- `optimized_prompt_score`
- `score_delta`
- `best_val_score`
- `seed_prompt_chars`
- `optimized_prompt_chars`
- `prompt_char_growth`
- `length_growth_ratio`
- `seed_prompt_lines`
- `optimized_prompt_lines`
- `seed_prompt_words`
- `optimized_prompt_words`
- `num_candidates`
- `num_full_val_evals`

全局 metadata 必须包含：

- `not_new_experiment = true`
- `no_model_called = true`
- `no_api_called = true`
- `no_gepa_optimize_called = true`
- `not_performance_claim = true`
- `token_estimate_for_audit_only = true`
- `not_exact_tokenizer_count = true`

## 统计定义

- `*_prompt_chars`: Python 字符串 `len(prompt)`。
- `*_prompt_lines`: `prompt.splitlines()` 的行数；空字符串计为 `0`。
- `*_prompt_words`: `prompt.split()` 的词数。
- `prompt_char_growth`: `optimized_prompt_chars - seed_prompt_chars`。
- `length_growth_ratio`: `optimized_prompt_chars / seed_prompt_chars`；若 seed prompt 长度为 `0` 则显式失败。
- `*_prompt_tokens_est`: `chars / 4` 的粗略估算，仅用于审计说明。

token 估算不是 tokenizer 精确计数，不能用于严格成本或模型上下文长度结论。

## 分析问题

结果报告必须回答：

1. `optimized prompt` 是否显著长于 `seed prompt`。
2. prompt 长度增长是否与 `optimized_test_score` 单调对应。
3. prompt 长度增长是否与 `score_delta` 单调对应。
4. 是否存在“最长 prompt 不是最高分”“最短 optimized prompt 反而最高分”的现象。
5. 是否支持下一步设计 `Length-Controlled GEPA`。
6. 当前是否只是只读 audit，而不是 `Length-Controlled GEPA` 实验。

## 边界声明

允许写出的结论：

- prompt length growth is substantial。
- length does not monotonically explain score gains。
- prompt length is a reasonable next audit/control variable。

禁止写出的结论：

- prompt 越长越好。
- 控制长度一定能提升。
- `Length-Controlled GEPA` 已验证。
- 这是新的性能实验。

## 验证策略

本地验证必须包括：

- `python -m compileall src scripts tests`
- `pytest -q`

测试覆盖：

- prompt 长度统计函数。
- 脚本模块不导入 GEPA、OpenAI、LiteLLM 或 evaluator。
- 缺失 artifact 时显式失败。
- JSON 与报告中包含 `not_new_experiment = true`、`no_gepa_optimize_called = true`、`not_performance_claim = true`。
