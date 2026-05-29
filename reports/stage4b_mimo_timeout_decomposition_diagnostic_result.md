# Stage 4B MiMo timeout decomposition diagnostic 结果

## 定位

- 本报告只记录 `MiMo` 的 timeout / generation stability diagnostic。
- 它不是 `GEPA` 结果。
- 它不是 `official_budget` 结果。
- 它不是 `pilot`。
- 它不是 `5-seed`。
- 它不是 `MiMo vs GLM` 排名。
- 所有真实调用都只允许解释为 `diagnostic`，不允许写成 performance claim。

## 边界标识

- `model_called = true`
- `api_called = true`
- `new_experiment_executed = true`
- `diagnostic_only = true`
- `not_gepa_result = true`
- `not_official_budget = true`
- `not_performance_claim = true`
- `no_gepa_optimize_called = true`
- `mimo_only = true`
- `not_strict_stage4b_result = true`

## 已执行子矩阵

- 子矩阵 A：`test-1`，`L3/L4`，`non_streaming/streaming`，`timeout=60/240`
- 子矩阵 B：`test-2,test-5`，`L3/L4`，`non_streaming/streaming`，`timeout=60`
- 子矩阵 C：`test-2,test-5`，`L3/L4`，`non_streaming`，`timeout=240`

所有真实执行都在 `WSL` 中完成，且每轮 AIME 请求前后都执行了 `Return exactly: OK` health check。

## health check 结论

- `Stage 4A raw_sdk provider probe` 正常。
- 本轮所有已执行子矩阵的 health check 都正常。
- 因此当前 blocker 不是 `endpoint / key / model-id / 基础网络不可用`。

## 关键观测

### 1. `test-1` 不是全面失败

- `test-1` 在 `non_streaming + L4 + 60s` 下可以完成并得到 `official_correct`。
- `test-1` 在 `non_streaming + L3 + 60s` 下会 timeout，但把 timeout 提高到 `240s` 后可以完成。
- `test-1` 的 `streaming` 路径在 `60s` 和 `240s` 下都能完成，并在约 `3.6s-8.9s` 内观察到首 token。

这说明 `MiMo` 不是完全不会做 AIME，也不是所有 strict/default AIME 请求都会失败。

### 2. `test-2/test-5` 的 `non_streaming + 60s` 稳定失败

| sample_id | prompt_layer | mode | timeout | completed | first_token_observed | 备注 |
|---|---|---|---:|---:|---:|---|
| `test-2` | `L3` | `non_streaming` | 60 | 0 | 0 | 首 token 前 timeout |
| `test-2` | `L4` | `non_streaming` | 60 | 0 | 0 | 首 token 前 timeout |
| `test-5` | `L3` | `non_streaming` | 60 | 0 | 0 | 首 token 前 timeout |
| `test-5` | `L4` | `non_streaming` | 60 | 0 | 0 | 首 token 前 timeout |

这说明 harder samples 在 strict/default 的非流式完整响应路径上明显更脆弱。

### 3. `streaming` 能缓解 timeout，但不是 strict `60s` 成功

| sample_id | prompt_layer | mode | timeout | completed | ttft_seconds | wall_clock_seconds | 结果 |
|---|---|---|---:|---:|---:|---:|---|
| `test-2` | `L3` | `streaming` | 60 | 1 | 4.118691 | 317.841182 | `format_loss` |
| `test-2` | `L4` | `streaming` | 60 | 1 | 3.192898 | 114.654710 | `official_correct` |
| `test-5` | `L3` | `streaming` | 60 | 1 | 5.324237 | 347.127510 | `format_loss` |
| `test-5` | `L4` | `streaming` | 60 | 1 | 3.745361 | 281.663626 | `official_correct` |

这里最重要的现象不是“能流出来”，而是：

- `streaming` 在约 `3s-5s` 内就能拿到首 token。
- 但总墙钟会继续拉长到约 `114s-347s`。

因此当前 provider / SDK 上的 `streaming` timeout 语义并不表现为严格墙钟 `60s` 上限。它可以作为机制诊断证据，但不能直接当成 strict `non_streaming 60s` 的成功对照。

### 4. `non_streaming + 240s` 只部分救回 `test-2/test-5`

| sample_id | prompt_layer | mode | timeout | completed | latency_seconds | finish_reason | 结果 |
|---|---|---|---:|---:|---:|---|---|
| `test-2` | `L3` | `non_streaming` | 240 | 1 | 64.896690 | `stop` | `format_loss` |
| `test-5` | `L3` | `non_streaming` | 240 | 1 | 68.392059 | `stop` | `reasoning_error` |
| `test-2` | `L4` | `non_streaming` | 240 | 0 | 241.749521 | `null` | `timeout` |
| `test-5` | `L4` | `non_streaming` | 240 | 0 | 241.849006 | `null` | `timeout` |

这一步把关键缺口补上后，可以排除一种过度简化的解释：当前现象不能概括成“`60s` 太短，拉到 `240s` 就都能救回”。

更准确地说：

- `L3 original_seed` 下，`non_streaming + 240s` 可以让 `test-2/test-5` 返回完整响应。
- 但返回质量并不稳定：一个是 `format_loss`，一个是 `reasoning_error`。
- `L4 strong_format` 下，`non_streaming + 240s` 对 `test-2/test-5` 仍然在首 token 前 timeout。

## prompt layer 影响

- `L4 strong_format` 对协议遵循有明显帮助。
- 在 `streaming` 路径上，`L4` 把 `test-2/test-5` 从 `format_loss` 拉回到了 `official_correct`。
- 但在 `non_streaming` 路径上，`L4` 没有稳定降低 timeout；相反，对 `test-2/test-5`，`L4 + non_streaming + 240s` 仍然 timeout。

因此可以写成：

- `L4` 改善了 output protocol adherence。
- `L4` 没有解决 MiMo strict/default `non_streaming` 路径上的 generation stability 问题。

不能写成：

- `L4` 证明 MiMo reasoning 更强。
- `format_loss` 就是 reasoning failure。

## timeout 分层归因

### 可以成立的归因

1. `MiMo` 的基础 provider 没坏。
2. 当前主要 blocker 集中在真实 AIME prompt 下的 strict/default `non_streaming` 完整响应路径。
3. 对 harder samples，`timeout=60s` 明显过紧，但“加到 `240s` 就全部恢复”这个说法不成立。
4. `streaming` 说明后端其实在继续生成，因为它能快速给出首 token 并最终完成。
5. 当前机制更像是长推理 / 长生成导致的 generation latency，而不是基础 API 不通。

### 不能过度外推的地方

1. 不能写成 `MiMo` 数学能力差。
2. 不能写成 `MiMo` strict Stage 4B 已经跑通。
3. 不能写成 `streaming + 60s` 等同于 strict `non_streaming + 60s` 成功。
4. 不能写成 `240s` 已经证明 `non_streaming` 路径足以支撑后续 `GEPA`。

## 当前三分判断

### 判断一：基础 provider 正常

- `Stage 4A raw_sdk provider probe` 正常。
- 本轮 health check 正常。
- 因此问题不在基础连通性。

### 判断二：strict/default `non_streaming` 路径才是主要 blocker

- `test-2/test-5` 在 `non_streaming + 60s` 下稳定 timeout。
- `test-2/test-5` 在 `non_streaming + 240s` 下也只在 `L3` 部分救回，`L4` 仍稳定 timeout。
- 这说明 `non_streaming` 完整响应路径对真实 AIME harder samples 不稳。

### 判断三：`streaming` 可以明显缓解，但不能等同 strict `60s`

- `streaming` 可以在几秒内给出首 token，并最终完成。
- 但总墙钟远超 `60s`。
- 所以它更像一条可诊断、可后续扩展的替代路径，而不是 strict `60s` 的直接成功证据。

## 对后续工作的含义

- 当前状态不支持直接进入 `GEPA`。
- 当前状态也不支持直接把 `MiMo non_streaming 60s` 扩成 `30-sample`。
- 如果继续走 `non_streaming`，后续只能写成 `extended_timeout_diagnostic`，不能写成 strict `60s` 对照。
- 如果继续走 `streaming`，必须单独建立 `streaming_path_only` 诊断，并补上应用层墙钟记录或 `application wall-clock guard`。

## 下一步建议

1. 不进入 `GEPA`。
2. 不直接跑 `MiMo 30-sample`。
3. 如果继续补 strict/default 线，建议把后续工作命名为 `MiMo extended-timeout diagnostic`，并显式标记：
   - `extended_timeout_diagnostic = true`
   - `not_strict_60s_comparison = true`
   - `not_gepa_result = true`
   - `not_model_ranking = true`
4. 如果后续目标是“找到可稳定完成真实 AIME 的 MiMo 路径”，建议优先转向：
   - `MiMo streaming extended-timeout diagnostic`
   - 或 `MiMo application-level wall-clock guarded streaming diagnostic`
5. 在这些工作完成前，不把 MiMo 写成 strict path 已经可用于后续 rerun 或 GEPA sanity。

## 结论边界

- 可以写：provider 正常 / health check 正常 / timeout 与 `mode`、`timeout_setting`、`prompt_layer`、`sample_id` 有关。
- 可以写：首 token 是否出现、总墙钟是否过长、`streaming` 与 `non_streaming` 是否存在明显差异。
- 可以写：`L4` 改善协议遵循，但没有稳定解决 `non_streaming` generation stability。
- 不可以写：`MiMo` 数学能力差。
- 不可以写：output-protocol failure 就是 reasoning failure。
- 不可以写：strict Stage 4B 已经成功。
- 不可以写：已经具备直接进入 `GEPA` 的前置条件。
