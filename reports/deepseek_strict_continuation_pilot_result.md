# DeepSeek Strict Continuation Pilot Result

## 文档定位

本报告封存一次真实运行的 `DeepSeek strict-readme continuation pilot` 结果。

本报告只记录运行事实，不做以下表述：

- 不写成 Stage 1 历史结论改写
- 不写成 `same-model reproduction`
- 不写成 `official_budget`
- 不写成 paper-level conclusion

## 运行对象

- 结果目录：`outputs/deepseek_strict_continuation_pilot/20260521T204134+0800`
- `path_type = deepseek_strict_continuation_pilot`
- `continuation_track = deepseek_strict_readme_continuation`
- `provider = deepseek`
- `task_lm = openai/deepseek-v4-flash`
- `reflection_lm = openai/deepseek-v4-pro`
- `dataset_source = gepa.examples.aime.init_dataset() with local cache-backed load_dataset`
- `seed_prompt_identity = README quickstart seed prompt`
- `max_metric_calls = 50`
- `seed = 42`

## 关键运行事实

- `execute_optimize = true`
- `execution_completed = false`
- `not_stage1_rewrite = true`
- `not_same_model_reproduction = true`
- `not_official_budget = true`
- `not_paper_level_claim = true`

控制台关键输出包括：

- `Iteration 0: Base program full valset score: 0.17777777777777778 over 45 / 45 examples`
- `Iteration 1: Selected program 0 score: 0.17777777777777778`
- `Iteration 1: Exception during optimization: 'InternalServerError' object has no attribute 'choices'`

## 结果摘要

来自 `deepseek_strict_continuation_pilot_result_summary.json` 的当前可确认字段：

- `execution_completed = false`
- `error_type = AttributeError`
- `error_message = 'InternalServerError' object has no attribute 'choices'`

## 结果解释

当前最准确的解释是：

- `DeepSeek strict continuation pilot started`
- 但它没有完成
- 它失败在第一次 reflective proposal 期间

这意味着：

- 这次 pilot 不是“完全没开始”
- 也不是 smoke 那种仅停在 baseline-only 阶段
- 但它当前不能写成 pilot 通过

## 当前边界

- 本结果不构成 Stage 1 重写
- 本结果不构成 same-model reproduction
- 本结果不构成 official budget 结果
- 本结果不构成 paper-level claim

## 当前建议

在进入下一轮实验前，应先完成：

- `DeepSeek strict continuation pilot` 的只读调用链审计

在该审计明确前，不应：

- 直接重跑 pilot
- 直接进入 `official_budget`
