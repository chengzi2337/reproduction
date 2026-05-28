# Stage 4A provider probe 设计

## 设计目标

Stage 4A 只回答一个问题：

> MiMo Pro 与 GLM-4.7 在当前 OpenAI-compatible / LiteLLM 探测路径下，是否具备进入后续 fixed-prompt 诊断的最小前置条件。

这里的“前置条件”只包括：

- provider connectivity
- authentication 行为
- model support
- 最小生成稳定性
- output protocol adherence 的最粗粒度观察
- timeout / empty output / finish_reason 行为

## 当前边界

- 不调用 GEPA
- 不调用 `gepa.optimize()`
- 不跑 `official_budget`
- 不跑 `pilot`
- 不进入 Stage 4B
- 不做 5-seed
- 不改 optimizer
- 不改 evaluator
- 不写成“谁更强”
- 不把 `official_score` 单独当作能力结论

## CLI 设计

脚本：

`scripts/stage4a_probe_mimopro_glm47.py`

必须支持：

- `--providers mimo glm`
- `--mimo-api-base`
- `--mimo-api-key-env`，默认 `MIMO_API_KEY`
- `--mimo-model`
- `--glm-api-base`
- `--glm-api-key-env`，默认 `GLM_API_KEY`
- `--glm-model`
- `--timeout`
- `--probe-raw-sdk`
- `--probe-litellm`
- `--output-dir`
- `--execute`

默认行为：

- 如果不传 `--execute`，只做 dry-run
- 如果不显式限制 probe path，则同时计划 `raw_sdk` 与 `litellm`

## provider 配置原则

### MiMo

建议环境变量：

- `MIMO_API_KEY`
- `MIMO_API_BASE`
- `MIMO_MODEL`

### GLM

建议环境变量：

- `GLM_API_KEY`
- `GLM_API_BASE`
- `GLM_MODEL`

规则：

- 如果用户没提供，就写 `missing credential/config`
- 不猜测 key
- 不猜测 base URL
- 不猜测 model id
- 不把 API 细节写死到代码里

## Probe 内容

### 1. simple OK

```text
Return exactly: OK
```

### 2. short math

```text
What is 19 + 23? Return only the final answer.
```

### 3. strong format micro

```text
Solve 19 + 23. Your entire response must be exactly one line: ### N
```

## 输出记录字段

每条记录至少包含：

- `provider`
- `model`
- `api_base_present`
- `backend_family`
- `provider_string`
- `probe_type`
- `probe_prompt_id`
- `status`
- `http_status`
- `content_nonempty`
- `content_preview`
- `reasoning_content_present`
- `finish_reason`
- `latency_seconds`
- `error_type`
- `error_message_sanitized`
- `timeout`
- `not_performance_claim = true`
- `no_gepa_optimize_called = true`
- `not_gepa_result = true`

为了后续 Stage 4B 复用，脚本还应额外保留：

- `expected_exact`
- `expected_answer`
- `extracted_answer`
- `protocol_exact_match`
- `format_loss`
- `protocol_category`

## 探测路径

### raw SDK

- 使用 OpenAI Python SDK 的 OpenAI-compatible chat completion
- 记录 `http_status`、`finish_reason`、`message.content`

### LiteLLM

- 默认优先探测 `openai/<model>`
- 不假设必然存在 `zhipu/...`、`glm/...`、`mimo/...`
- 如有需要，可通过可选 provider string 参数显式传入
- provider string 必须是显式配置，不是硬编码真值

## dry-run / execute 语义

### dry-run

- 不发请求
- 不调用模型
- 只生成 probe 计划、配置快照、空执行摘要和结果报告

### execute

- 只有显式 `--execute` 才允许
- 逐个 provider / path / probe 顺序执行
- 记录原始响应样本、失败样本、汇总 JSON

## artifact 设计

执行结果写入：

`outputs/stage4a_provider_probe/<timestamp>/`

至少包含：

- `input_snapshot.json`
- `probe_results.json`
- `per_example_eval.jsonl`
- `run_summary.json`
- `failure_cases.json`
- `raw_responses/*.json`

报告写入：

`reports/stage4a_provider_probe_result.md`

## failure-mode 处理层级

任何异常都按以下层级归因：

1. provider connectivity
2. authentication
3. model support
4. parameter support
5. generation stability
6. output protocol
7. evaluator contract

不允许：

- 把 output protocol 问题写成 reasoning failure
- 把 provider timeout 写成模型能力弱
- 把 relaxed 可提取正确写成 official 正确

## 报告允许结论

- provider reachable / not reachable
- key valid / invalid / unknown
- model supported / unsupported / unknown
- content returned / empty
- timeout / no timeout
- raw SDK 与 LiteLLM 是否一致

## 报告禁止结论

- MiMo 比 GLM 强
- GLM 比 MiMo 强
- 可以用于 GEPA `official_budget`
- 数学能力已经有结论
- Stage 4B 可以绕过 Stage 4A blocker
