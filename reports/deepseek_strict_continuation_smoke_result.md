# DeepSeek Strict Continuation Smoke Result

## 定位

- 本报告只封存一次已完成的 `DeepSeek strict-readme continuation` smoke 结果。
- 该结果属于 `GEPA method-level reproduction with DeepSeek backend`。
- 它不是 `Stage 1` 历史结果改写。
- 它不是 `same-model reproduction`。
- 它不是 `official_budget`。
- 它不是 `pilot`。
- 它不是论文级性能结论。

## 运行身份

- `path_type = deepseek_strict_continuation_smoke`
- `continuation_track = deepseek_strict_readme_continuation`
- `provider = deepseek`
- `backend_family = openai_compatible`
- `task_model = deepseek-v4-flash`
- `reflection_model = deepseek-v4-pro`
- `task_lm = openai/deepseek-v4-flash`
- `reflection_lm = openai/deepseek-v4-pro`
- `seed_prompt_type = readme_quickstart_seed_prompt`

## 输入快照

- 结果目录：`outputs/deepseek_strict_continuation_smoke/20260521T193315+0800`
- 输入快照文件：`deepseek_strict_continuation_smoke_input_snapshot.json`
- `dataset_source = gepa.examples.aime.init_dataset() with local cache-backed load_dataset`
- `trainset_size = 45`
- `valset_size = 45`
- `testset_size = 150`
- `max_metric_calls = 10`
- `seed = 42`
- `execute_optimize = true`

## 结果摘要

- `execution_completed = true`
- `best_score = 0.2222222222222222`
- `total_metric_calls = 45`
- `num_candidates = 1`
- `num_val_instances = 45`
- `num_full_val_evals = 1`

## 最小解释

- `DeepSeek strict continuation smoke passed`
- 本次 run 已经完成了一次 strict-path smoke 闭环
- 但本次结果当前只能解释为：
  - strict continuation 路径在 DeepSeek 后端下可以执行
  - 本次 smoke 还不能写成 prompt evolution 已成立
  - 本次 smoke 也不能写成 pilot 准备完成

## 边界声明

- 本报告不回写 `Stage 1` baseline。
- 本报告不宣称 `same-model reproduction`。
- 本报告不宣称 `official_budget` readiness 已成立。
- 本报告不宣称论文级性能结论。
- 本报告不提交 `outputs/` 原始目录，只记录结果摘要。
