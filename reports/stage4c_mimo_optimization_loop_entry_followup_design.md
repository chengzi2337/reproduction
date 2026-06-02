# Stage 4C MiMo optimization-loop entry follow-up 设计

## 目标

- 只做一次最小 follow-up，验证 MiMo 是否能从 `seed-evaluation sanity` 前进一步，进入真正的 `optimization-loop entry`。
- 该 follow-up 不是分数实验，不是模型排名，也不是 GEPA 正式扩展。

## 当前前置结论

- 已证明：
  - `MiMo thinking.enabled + streaming bridge` 能完成至少一次 GEPA seed-evaluation。
- 尚未证明：
  - `reflection / mutation / candidate generation`
  - `num_candidates > 1`
  - optimization loop 真正进入

## 本轮边界

- `provider = mimo`
- `model = mimo-v2.5-pro`
- `thinking = enabled`
- `streaming = true`
- `diagnostic_val_limit = 1`
- `max_metric_calls = 2`
- 不进入 `official_budget`
- 不进入 `smoke`
- 不进入 `pilot`
- 不做模型排名
- 不改 `optimizer`
- 不改 `evaluator`
- 不改 AIME metric

## 为什么必须保持 `diagnostic_val_limit = 1`

- 当前单样本 seed-evaluation 已经观测到：
  - `time_to_complete_seconds = 818.400078`
- full-val 长任务还观测到：
  - 多条请求在数百秒到 `1800s` 级
  - 第 17 条请求出现 `MidStreamFallbackError`

因此：

- 在尚未证明 optimization-loop entry 的前提下，扩大 valset 只会放大 latency 和 stream instability。
- 本轮 follow-up 的唯一合理目标是“是否能进入 loop”，不是“是否能稳定扩到更多样本”。

## 建议配置

- `first_token_timeout_seconds = 1800`
- `sdk_timeout_seconds = 1800`
- `emergency_after_first_token_seconds = null`
- `diagnostic_val_limit = 1`
- `max_metric_calls = 2`
- `thinking.enabled` 继续通过 `extra_body` 透传
- 继续保留 pre/post `Return exactly: OK` health check

## 本轮要回答的问题

1. `total_metric_calls` 是否达到 `2`
2. `num_candidates` 是否大于 `1`
3. 是否出现非 seed candidate
4. 是否出现 reflection / mutation / candidate generation 的直接证据
5. 第二次调用在 MiMo streaming bridge 下是否仍能稳定返回
6. 是否出现新的 timeout / stream hang / malformed response / mid-stream fallback

## 判定规则

### 1. optimization-loop entry passed

满足：

- `total_metric_calls >= 2`
- `num_candidates > 1`

可写为：

- `MiMo streaming GEPA optimization-loop entry passed`

但仍不能写：

- `MiMo GEPA fully passed`
- `MiMo 适合 official_budget`

### 2. additional metric call passed, but candidate-generation evidence insufficient

满足：

- `total_metric_calls = 2`
- 但 `num_candidates = 1`

只能写为：

- `additional metric call passed, but candidate-generation evidence insufficient`

### 3. seed-eval only / expansion blocked

如果第二次调用失败、极慢或中途断流：

- 说明 MiMo streaming path 当前最多只能完成 seed-evaluation sanity
- 不建议继续 GEPA expansion

### 4. latency too high even if passed

如果 follow-up 虽然成功，但第二次调用仍然是十几分钟级：

- 说明 loop entry 虽可观察，但成本过高
- 仍然不建议扩到 45-val / smoke / official_budget

## 输出要求

报告里必须显式区分：

- `seed-evaluation sanity`
- `optimization-loop entry`
- `expanded validation stability`

不能把这三者混写成一个“GEPA 已跑通”的结论。

## 执行建议

- 如果要继续执行，只建议在 `WSL Ubuntu-22.04-Fresh` 中跑。
- Windows 当前已观测到 raw SDK `APIConnectionError: Connection error.`，不应作为主执行环境。

## 当前建议

- 先封存 `c1b8616` 对应的 Stage 4C 脚手架和 seed-eval checkpoint。
- 如需继续，只做这一轮 `max_metric_calls = 2 + diagnostic_val_limit = 1` follow-up。
- 在该 follow-up 之前，不建议再跑 full-val、smoke 或更高 budget。
