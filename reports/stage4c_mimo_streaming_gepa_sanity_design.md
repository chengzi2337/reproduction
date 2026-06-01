# Stage 4C MiMo streaming GEPA sanity 设计

## 目标

- 建立 `Stage 4C MiMo streaming GEPA feasibility sanity` 脚手架。
- 默认只做 `dry-run`。
- `dry-run` 只生成 input snapshot、result stub 和测试覆盖，不调用模型，不调用 `gepa.optimize()`。
- 只有后续用户明确批准 `--execute`，才允许进入真实 GEPA optimize 分支。

## 边界

- 只处理 `MiMo`，不碰 `GLM`。
- 不进入 `official_budget`、`smoke`、`pilot`、`5-seed`。
- 不改 `optimizer`、`evaluator`、AIME metric。
- 不做模型排名。
- 不把任何结果写成 performance claim。
- 所有输出必须带：
  - `diagnostic_only = true`
  - `not_official_budget = true`
  - `not_performance_claim = true`
  - `not_model_ranking = true`
  - `not_strict_default_path = true`
  - `streaming_path_only = true`
  - `thinking_enabled = true`

## 只读审查结论

### 1. GEPA 官方调用链

- `src/gepa_official_runner.py` 复用官方 `gepa.optimize()`，task / reflection model 都以字符串形式传入。
- 已安装 `gepa.optimize()` 的 reflection path，在 `reflection_lm` 为字符串时直接调用 `litellm.completion(...)`。
- 已安装 `gepa.adapters.default_adapter.default_adapter.DefaultAdapter.evaluate()` 的 task path，明确调用 `litellm.batch_completion(...)`。

结论：

- 若要让 MiMo 走 streaming，必须同时 patch：
  - `litellm.completion`
  - `litellm.batch_completion`

### 2. Stage 4B MiMo streaming runner

- 现有 `stage4b_mimo_streaming_first_token_only_deadline_diagnostic.py` 已验证：
  - `thinking.enabled`
  - `streaming`
  - `first-token-only deadline`
  - pre/post health check
  - 首 token 计时与首 token 后长生成计时

结论：

- Stage 4C 复用其 timeout 语义，而不是回退到 non-streaming strict path。

### 3. Stage 2C 相关内容

- 当前仓库只保留了 `stage2c_run_mimo_controlled_generation_gepa_sanity.py` 和 `src/mimo_controlled_generation.py` 的 `pyc`，源码缺失。
- 现有可见证据表明 Stage 2C 通过局部 patch LiteLLM completion / batch_completion，把 MiMo 特定参数注入 GEPA 调用链。

结论：

- Stage 4C 不应依赖缺失源码，而应基于当前仓库可见源码和已安装 `gepa` 的真实调用链，重建最小桥接层。

## 方案

### 1. 新增桥接层

新增：

- `src/mimo_streaming_gepa_bridge.py`

职责：

- 以 context manager 方式局部 patch `litellm.completion` / `litellm.batch_completion`
- 强制：
  - `stream=True`
  - `thinking={"type":"enabled"}`
  - `provider=mimo`
  - `model=mimo-v2.5-pro`
- 不默认注入：
  - `thinking.disabled`
  - `max_completion_tokens`
  - `temperature`
- 对每个请求做 streaming 汇聚，向 GEPA 返回可读响应对象：
  - `choices[0].message.content`
  - `choices[0].finish_reason`
  - `usage = None`

### 2. timeout 语义

- `first_token_timeout_seconds = 1800`
- 首 token 前超时：
  - 标记 `FirstTokenTimeout`
  - 尝试关闭 stream
  - 记录 failure mode
- 首 token 后：
  - 默认等待自然完成
  - 可选 `emergency_after_first_token_seconds`
  - 若触发，只标记 emergency，不写成 strict timeout

记录字段：

- `first_token_observed`
- `time_to_first_token_seconds`
- `time_after_first_token_seconds`
- `time_to_complete_seconds`
- `finish_reason`
- `content_nonempty`
- `partial_content_nonempty`
- `error_type`
- `error_message_sanitized`
- `raw_preview`

### 3. dry-run / execute 切换

- 默认 dry-run：
  - 不调用模型
  - 不调用 `gepa.optimize()`
  - 只写 `input_snapshot.json`、`run_summary.json`、报告 stub
- `--execute`：
  - 先做 pre health check
  - pre health check 失败则直接阻断，不进入 GEPA
  - 成功后进入 patch context，再调用 `gepa.optimize(max_metric_calls=1)`
  - 结束后做 post health check

### 4. health check

请求：

- `Return exactly: OK`

判读：

- pre health check 失败：
  - 归因为 provider / key / endpoint / network blocker
  - `gepa.optimize_called = false`
- pre 成功、GEPA 失败：
  - 再区分 patch / optimize / response assembly / artifact parsing

## dry-run snapshot 要求

必须包含：

- `provider`
- `model`
- `path_type`
- `streaming_path_only`
- `thinking_enabled`
- `first_token_only_deadline`
- `max_metric_calls = 1`
- `execute_optimize = false`
- `seed_prompt_source`
- `dataset_source`
- `train/val/test size`
- `task_lm`
- `reflection_lm`
- `gepa_optimize_called = false`
- `diagnostic_only = true`
- `not_performance_claim = true`
- `no_api_key_written = true`

## 测试策略

使用 mock，不需要真实 key。

至少覆盖：

1. dry-run 不调用模型 / GEPA
2. 只有 `--execute` 进入 optimize 分支
3. key 不写入输出
4. `thinking.enabled` 注入
5. 不默认注入 `thinking.disabled` 和 `max_completion_tokens`
6. patch 退出后恢复 `litellm`
7. batch mock response 可被 GEPA 读取
8. `FirstTokenTimeout` 分类
9. 首 token 后自然完成
10. stream error 保留 partial
11. health check 失败阻止 execute
12. missing env/config 清晰报错
13. 输出不含绝对路径和 key

## 结果解释边界

- 可以写：MiMo streaming GEPA sanity 脚手架是否已经具备 dry-run 和 mock execute 能力。
- 可以写：GEPA 官方默认 task/reflection 调用链是否已被 MiMo streaming patch 覆盖。
- 不可以写：MiMo strict path 成功。
- 不可以写：MiMo 已适合 GEPA 正式实验。
- 不可以写：MiMo 比其他模型更强。
