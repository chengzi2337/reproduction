# Stage 4B MiMo streaming extended-timeout diagnostic 设计

## 目标

本设计只服务于 `MiMo` 的 `streaming extended-timeout diagnostic`，不比较 `GLM`，不进入 `GEPA`，不进入 `official_budget`，不进入 `pilot`，不运行 `5-seed`。

第一轮只回答这些问题：

1. `MiMo` 在 `streaming + extended-timeout` 条件下，能否稳定完成真实 AIME fixed-prompt diagnostic。
2. `L4 strong_format_seed_prompt` 下，输出协议是否稳定。
3. completed 样本的 `official / relaxed / format_loss / reasoning_error / empty_or_invalid` 是否可解释。
4. 单样本真实墙钟耗时是多少。
5. 是否仍存在 timeout、空输出、reasoning-only output、finish_reason 异常。
6. 是否具备后续扩到 `30-sample streaming diagnostic` 的前置条件。

## 执行边界

- 只允许 `provider=mimo`
- 只允许 `backend_path=raw_sdk`
- 只允许 `mode=streaming`
- 默认 `dry-run`
- 只有显式 `--execute` 才调用模型
- 第一轮真实执行最多 5 个样本
- 只执行 `L4 strong_format_seed_prompt`
- 不调用 `gepa.optimize`
- 不改 `optimizer`
- 不改 `evaluator`
- 不提交 `outputs/*`
- 不提交 `.codex/*`
- 不提交 `.pytest_tmp/*`
- 不提交 API key
- 不提交本地绝对路径

## 标记要求

所有 artifact 和报告都必须带：

- `streaming_path_only = true`
- `extended_timeout_diagnostic = true`
- `not_strict_non_streaming_path = true`
- `not_strict_60s_comparison = true`
- `not_gepa_result = true`
- `not_official_budget = true`
- `not_model_ranking = true`
- `not_performance_claim = true`
- `diagnostic_only = true`

## 默认执行参数

- `--provider mimo`
- `--api-key-env MIMO_API_KEY`
- `--api-base-env MIMO_API_BASE`
- `--model-env MIMO_MODEL`
- `--backend-path raw_sdk`
- `--sample-ids test-1 test-2 test-3 test-4 test-5`
- `--prompt-variant l4_strong_format`
- `--application-wall-clock-timeout 600`
- `--sdk-timeout 600`
- `--sleep-between-requests 60`
- `--max-retries 0`
- `--output-dir outputs/stage4b_mimo_streaming_extended_timeout_diagnostic`

## prompt

固定只用 `L4 strong_format_seed_prompt`：

```text
Solve the problem.
Your final answer must be exactly one line in this format:
### N
where N is the final integer answer.
Do not use \boxed{}.
Do not use XML tags.
Do not write "Final answer:".
Do not write the final answer in any other format.
```

## application wall-clock guard

本轮不允许只依赖 SDK streaming timeout。

必须在应用层记录：

- `start_time = time.monotonic()`
- `application_wall_clock_timeout_seconds`
- `sdk_timeout_seconds`
- `timeout_enforced_by`

当 `elapsed > application_wall_clock_timeout_seconds` 时：

- 主动停止当前样本
- 尝试关闭 `stream`
- 保留 partial content
- 标记 `error_type = ApplicationWallClockTimeout`

## 记录字段

逐样本记录：

- `provider`
- `model`
- `backend_path`
- `mode`
- `sample_id`
- `prompt_variant`
- `application_wall_clock_timeout_seconds`
- `sdk_timeout_seconds`
- `sleep_between_requests`
- `max_retries`
- `started_at`
- `completed_at`
- `time_to_first_token_seconds`
- `time_to_complete_seconds`
- `latency_seconds`
- `first_token_observed`
- `content_nonempty`
- `partial_content_nonempty`
- `reasoning_content_present`
- `finish_reason`
- `official_score`
- `relaxed_extractable_correct`
- `extracted_answer`
- `format_loss`
- `reasoning_error`
- `empty_or_invalid`
- `timeout`
- `timeout_enforced_by`
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

- health check 失败时，不得把 AIME 失败直接归因为题目复杂度或模型能力。
- `ApplicationWallClockTimeout` 要单独计数，不能和 SDK/provider timeout 混写。
- `partial_content_nonempty = true` 时，必须保留 partial content 预览并单列说明。
- `content` 为空但 `reasoning_content_present=true` 时，必须单列为 `reasoning_only_output`。
- `format_loss` 只能解释为协议损失，不能写成 reasoning failure。
- 即使 `5/5` 都完成，也不能写成 strict non-streaming path 已成功。

## 交付物

- `scripts/stage4b_mimo_streaming_extended_timeout_diagnostic.py`
- `tests/test_stage4b_mimo_streaming_extended_timeout_diagnostic.py`
- `reports/stage4b_mimo_streaming_extended_timeout_diagnostic_result.md`

## 提交策略

第一提交只包含：

- 设计文档
- 脚本
- 测试
- dry-run 结果报告

真实执行结果必须单独提交，不能和脚手架混写。
