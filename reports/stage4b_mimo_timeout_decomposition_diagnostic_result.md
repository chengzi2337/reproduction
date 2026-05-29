# Stage 4B MiMo timeout decomposition diagnostic 结果

## 定位

- 本报告只记录 MiMo 的 timeout / generation stability diagnostic。
- 它不是 GEPA 结果。
- 它不是 official_budget 结果。
- 它不是 pilot。
- 它不是 5-seed。
- 它不是 MiMo vs GLM 排名。
- 所有真实调用都只允许解释为 diagnostic，不允许写成 performance claim。

## 边界标记

- `model_called = true`
- `api_called = true`
- `new_experiment_executed = true`
- `diagnostic_only = true`
- `not_gepa_result = true`
- `not_official_budget = true`
- `not_performance_claim = true`

## 本轮真实执行范围

本轮在 `WSL Ubuntu-22.04-Fresh` 中执行，分成两个受控子矩阵：

1. `test-1`
   - `prompt_layer = l3_original_seed, l4_strong_format`
   - `mode = non_streaming, streaming`
   - `timeout = 60, 240`
2. `test-2, test-5`
   - `prompt_layer = l3_original_seed, l4_strong_format`
   - `mode = non_streaming, streaming`
   - `timeout = 60`

说明：

- 所有请求都使用 `raw_sdk`
- 所有请求都保留 `sleep_between_requests = 60`
- 所有请求都保留 `max_retries = 0`
- 没有注入 `thinking.disabled`
- 没有注入 `max_completion_tokens`
- 没有改 temperature

## health check 结果

所有已执行轮次的 pre / post health check 都正常：

- `non_streaming @ 60s`：`OK`
- `non_streaming @ 240s`：`OK`
- `streaming @ 60s`：`OK`
- `streaming @ 240s`：`OK`

这意味着本轮观测到的 AIME timeout 不能先写成 key / endpoint / model-id / 网络不可用问题。

## timeout decomposition 结论

### 1. `60s` 对 MiMo strict non-streaming path 偏紧，但不是对所有组合都同样偏紧

已观察到：

- `test-1 + l3_original_seed + non_streaming + 60s`：timeout
- `test-2 + l3_original_seed + non_streaming + 60s`：timeout
- `test-5 + l3_original_seed + non_streaming + 60s`：timeout
- `test-2 + l4_strong_format + non_streaming + 60s`：timeout
- `test-5 + l4_strong_format + non_streaming + 60s`：timeout

但也观察到：

- `test-1 + l4_strong_format + non_streaming + 60s`：完成，`official_correct`

因此当前更准确的写法是：

- `60s` 对 MiMo 的 strict non-streaming path 在真实 AIME 样本上明显过紧
- 但它不是“所有样本、所有 prompt layer 一律不够”的简单结论

### 2. 当前观察到的 non-streaming timeout 发生在首 token 之前

所有 non-streaming timeout 记录都满足：

- `first_token_observed = false`
- `content_nonempty = false`
- `finish_reason = null`
- `error_type = APITimeoutError`

所以这批 timeout 目前更像：

- 首 token 前等待过长
- 或 non-streaming 完整响应返回路径等待过长

而不是“已经开始稳定吐 token，但因为输出过长才超时”。

### 3. streaming 与 non-streaming 的行为差异非常明显

对同样的真实 AIME 样本：

- `non_streaming + 60s` 多次在首 token 前 timeout
- `streaming + 60s` 所有已测样本都在数秒内拿到首 token，并最终完成

已观测到的 `time_to_first_token_seconds`：

- `test-1 + l3 + streaming + 60s`：`3.56s`
- `test-1 + l4 + streaming + 60s`：`3.84s`
- `test-2 + l3 + streaming + 60s`：`4.12s`
- `test-5 + l3 + streaming + 60s`：`5.32s`
- `test-2 + l4 + streaming + 60s`：`3.19s`
- `test-5 + l4 + streaming + 60s`：`3.75s`

因此当前最强的机制结论之一是：

- MiMo 在真实 AIME prompt 上，`streaming` 明显优于 `non_streaming`
- 问题不只是“模型完全不会起 token”，而是 non-streaming 路径在 strict 60s 下极不稳定

### 4. streaming path 的 timeout 语义不是严格墙钟上限

在 `streaming + 60s` 下，已经出现多次总耗时远超 `60s` 但请求仍成功完成：

- `test-2 + l3 + streaming + 60s`：`317.84s`
- `test-5 + l3 + streaming + 60s`：`347.13s`
- `test-2 + l4 + streaming + 60s`：`114.65s`
- `test-5 + l4 + streaming + 60s`：`281.66s`

因此当前不能把 `streaming + 60s` 解释成“真正的 60 秒 strict timeout 对照组”。

更准确的写法是：

- 当前 SDK / provider 的 `stream=True` 路径没有表现为严格墙钟 `60s`
- 后续如果要拿 streaming 做更严谨对照，需要单独加 application-level wall-clock guard

### 5. prompt layer 会显著影响输出协议，但对 non-streaming 60s 的稳定性改善不一致

已观察到：

- `test-1`
  - `l3 + non_streaming + 240s`：完成，但 `format_loss`
  - `l4 + non_streaming + 240s`：完成，`official_correct`
  - `l3 + streaming + 60/240s`：`official_correct`
  - `l4 + streaming + 60/240s`：`official_correct`
- `test-2 / test-5`
  - `l3 + streaming + 60s`：完成，但 `format_loss`
  - `l4 + streaming + 60s`：完成，`official_correct`
  - `l4 + non_streaming + 60s`：仍然 timeout

因此当前更准确的结论是：

- `strong_format` 对输出协议有明显帮助
- 它可以把 `streaming` 路径上的 `format_loss` 拉回 `official_correct`
- 但它没有稳定解决 harder samples 在 `non_streaming + 60s` 下的 timeout

### 6. timeout 具有样本特异性

当前最小样本集已经出现明显分层：

- `test-1`
  - `non_streaming + l3 + 60s`：timeout
  - `non_streaming + l4 + 60s`：可完成
- `test-2 / test-5`
  - `non_streaming + l3 + 60s`：timeout
  - `non_streaming + l4 + 60s`：仍 timeout

因此可以写：

- timeout 确实集中在特定 harder samples 上
- `test-2 / test-5` 比 `test-1` 更像 persistent blocker

## 当前可支持的判断

### 可以支持

- MiMo 当前 blocker 不是 provider 不可用，因为 health check 和 Stage 4A probe 都正常
- MiMo 当前 blocker 主要落在真实 AIME prompt 下的 strict non-streaming generation stability
- `streaming` 和 `non_streaming` 的表现确实显著不同
- `strong_format` 更像协议修正器，不是稳定性万能修复器
- 对 harder samples，`streaming` 能启动并完成，但其 60s 不是严格墙钟

### 不可以支持

- 不能把 non-streaming timeout 写成数学能力差
- 不能把 `format_loss` 写成 reasoning failure
- 不能把 streaming 成功直接写成 strict Stage 4B 成功
- 不能把这批结果直接写成可以进入 GEPA strict sanity

## 对后续 Stage 4B / GEPA 前置条件的判断

当前判断：

- **strict non-streaming 60s path**：不具备稳定 rerun 前置条件
- **extended-time non-streaming path**：只在 `test-1` 上看到恢复，证据还不够
- **streaming diagnostic path**：具备继续诊断价值，但必须单列，不等同 strict path
- **controlled-generation path**：当前还不应该先跳过去，因为 strict/default 的 timeout 语义问题还没完全拆干净

因此更稳妥的下一步是：

1. 继续在 strict/default 框架内补 `test-2 / test-5` 的 `240s` 对照
2. 如需把 streaming 用作后续参考，先补 application-level wall-clock guard
3. 在 strict/default 证据补齐前，不把 MiMo 写成已具备 GEPA sanity 前置条件

## 结论边界

- 可以写：timeout 是否与 timeout 设置、mode、prompt layer、sample_id、health check 结果相关
- 可以写：是否发生在首 token 前，还是生成开始后长时间不结束
- 可以写：是否存在输出协议改善但稳定性未改善
- 不可以写：MiMo 数学能力差
- 不可以写：output-protocol failure 就是 reasoning failure
- 不可以写：strict Stage 4B 已成功或可以直接进入 GEPA
