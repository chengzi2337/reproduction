# Stage 4C MiMo streaming GEPA sanity 结果

## 定位

- 本报告只记录 MiMo streaming GEPA feasibility sanity。
- 本路径不是 strict default path。
- 本路径不是 official_budget 结果。
- 本路径不是模型排名，也不是性能结论。
- 默认 dry-run；只有显式 `--execute` 才允许进入 `gepa.optimize()`。

## 边界标记

- `model_called = true`
- `api_called = true`
- `new_experiment_executed = true`
- `diagnostic_only = true`
- `not_official_budget = true`
- `not_performance_claim = true`
- `not_model_ranking = true`
- `not_strict_default_path = true`
- `streaming_path_only = true`
- `thinking_enabled = true`

## 请求快照

- provider：`mimo`
- model：`mimo-v2.5-pro`
- path_type：`stage4c_mimo_streaming_gepa_sanity`
- streaming：`true`
- thinking：`{"type": "enabled"}`
- first_token_timeout_seconds：`1800.0`
- sdk_timeout_seconds：`1800.0`
- emergency_after_first_token_seconds：`None`
- max_metric_calls：`1`
- execute_optimize：`true`
- task_lm：`openai/mimo-v2.5-pro`
- reflection_lm：`openai/mimo-v2.5-pro`
- seed_prompt_source：`src.gepa_official_runner.SEED_PROMPT`
- dataset_source：`local_hf_cache::.cache/huggingface/datasets/AI-MO___aimo-validation-aime/default/0.0.0/13f9e12f613e720c2a2b2f345dd04b998a29494d/aimo-validation-aime-train.arrow|.cache/huggingface/datasets/MathArena___aime_2025/default/0.0.0/c94da77eb22bbd6439e62a323bec18493a421302/aime_2025-train.arrow|semantic_source=gepa.examples.aime.init_dataset`
- trainset_size：`45`
- valset_size_full：`45`
- valset_size_used：`1`
- diagnostic_val_limit：`1`
- effective_min_metric_calls：`2`
- testset_size：`150`
- gepa_optimize_called：`true`
- no_api_key_written：`true`

## 配置状态

- api_base_present：`true`
- model_present：`true`
- missing_config_reasons：`none`

## 执行状态

- optimize_attempted：`true`
- optimize_succeeded：`true`
- error_type：`None`

## health check 汇总

- check_count：`2`
- ok_count：`2`
- error_count：`0`
- avg_latency_seconds：`5.155436`

## bridge 调用摘要

- bridge_call_count：`1`
