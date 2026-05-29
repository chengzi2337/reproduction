# Stage 4B MiMo timeout decomposition diagnostic 设计

## 目标

本设计只服务于 `MiMo` 的 timeout / generation stability 诊断，不比较 `GLM`，不进入 `GEPA`，不进入 `official_budget`，不进入 `pilot`，不运行 `5-seed`。

要回答的问题只有这些：

1. `60s` 是否过紧。
2. timeout 是发生在首 token 之前，还是生成开始后输出太长。
3. `non_streaming` 和 `streaming` 是否有显著差异。
4. timeout 是否集中在特定样本。
5. `original_seed_prompt` 与 `strong_format_seed_prompt` 是否影响 timeout。
6. strict/default path 是否已经具备后续 rerun 或 GEPA sanity 的前置条件。

## 执行边界

- 只允许 `provider=mimo`
- 只允许 `backend_path=raw_sdk`
- 默认 `dry-run`
- 只有显式 `--execute` 才调用模型
- 第一轮真实执行最多 5 个样本
- 不调用 `gepa.optimize`
- 不改 `optimizer`
- 不改 `evaluator`
- 不提交 `outputs/*`
- 不提交 `.codex/*`
- 不提交 `.pytest_tmp/*`
- 不提交 API key
- 不提交本地绝对路径

## 输入参数

默认参数：

- `--provider mimo`
- `--api-key-env MIMO_API_KEY`
- `--api-base-env MIMO_API_BASE`
- `--model-env MIMO_MODEL`
- `--backend-path raw_sdk`
- `--sample-ids test-1 test-2 test-3 test-4 test-5`
- `--timeout-values 60 120 240`
- `--sleep-between-requests 60`
- `--max-retries 0`
- `--mode non_streaming streaming`
- `--prompt-layers l2_question_only l3_original_seed l4_strong_format`
- `--output-dir outputs/stage4b_mimo_timeout_decomposition_diagnostic`

## prompt layer 定义

- `l2_question_only`
  - 只传 AIME question，不额外加格式要求。
- `l3_original_seed`
  - `You are a helpful assistant. Answer the question. Put your final answer in the format '### <answer>'`
- `l4_strong_format`
  - 复用 Stage 4B 的强格式 system prompt。

## 记录字段

逐请求记录：

- `provider`
- `model`
- `backend_path`
- `mode`
- `sample_id`
- `prompt_layer`
- `timeout_setting`
- `sleep_between_requests`
- `max_retries`
- `started_at`
- `completed_at`
- `latency_seconds`
- `time_to_first_token_seconds`
- `time_to_complete_seconds`
- `first_token_observed`
- `content_nonempty`
- `reasoning_content_present`
- `finish_reason`
- `official_score`
- `relaxed_extractable_correct`
- `extracted_answer`
- `format_loss`
- `reasoning_error`
- `empty_or_invalid`
- `timeout`
- `error_type`
- `error_message_sanitized`
- `raw_response_preview`
- `raw_response_path`

health check 记录：

- `phase = pre / post`
- `content_exact_ok`
- `content_preview`
- `latency_seconds`
- `error_type`
- `http_status`

## 判读规则

- health check 失败时，不得把 AIME timeout 直接归因为题目复杂度。
- `streaming` 有首 token 但长时间不结束，优先记为“生成后收束问题”。
- `streaming` 无首 token，优先记为“首 token 前等待过长 / provider 排队 / 前置推理过长”。
- `content` 为空但 `reasoning_content_present=true` 时，必须单列为 `reasoning_only_output`，不能写成通过。
- `format_loss` 只能解释为协议损失，不能写成 reasoning failure。

## 交付物

- `scripts/stage4b_mimo_timeout_decomposition_diagnostic.py`
- `tests/test_stage4b_mimo_timeout_decomposition_diagnostic.py`
- `reports/stage4b_mimo_timeout_decomposition_diagnostic_result.md`

## 首提交策略

第一提交只允许包含：

- 设计文档
- 脚本
- 测试
- dry-run 结果报告

首提交不包含真实模型调用结果。
