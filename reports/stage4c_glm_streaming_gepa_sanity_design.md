# Stage 4C GLM streaming GEPA micro-sanity 设计

## 定位

- 本阶段只验证 `GLM-4.7` 在 `streaming + GEPA micro-sanity` 路径下是否能跑通最小闭环。
- 它不是 `official_budget`。
- 它不是 `smoke / pilot / 5-seed`。
- 它不是模型排名。
- 它不是最终性能比较。

## 已知前提

- Stage 4A provider probe 已通过。
- Stage 4B 发现：
  - non-streaming 下，GLM 会出现 rate-limit 与 timeout。
  - streaming 下，首 token 延迟极高，但在更宽时间预算下能完成更多样本。
  - `thinking=default` 很慢但更准，`thinking=disabled` 很快但会掉正确率。

## 调用链审查结论

- `src/gepa_official_runner.py` 与 `scripts/06_minimal_official_path_sanity.py` 证明本仓库 GEPA 主入口仍是官方 `gepa.optimize()`。
- 已安装 `gepa.adapters.default_adapter.default_adapter.DefaultAdapter.evaluate()` 在字符串模型路径下明确调用 `litellm.batch_completion(...)`。
- 已安装 `gepa.api.optimize()` 在 `reflection_lm` 为字符串时明确调用 `litellm.completion(...)`。
- 因此 Stage 4C 必须同时 patch：
  - `litellm.batch_completion`
  - `litellm.completion`

## 缺失文件说明

以下路径在当前仓库中不存在，只能记录为缺失，不作为实现依赖：

- `scripts/07_strict_readme_quickstart_path.py`
- `scripts/stage2c_run_mimo_controlled_generation_gepa_sanity.py`
- `src/mimo_controlled_generation.py`

## 运行边界

- provider 固定为 `GLM`
- backend 固定为 `raw_sdk`
- mode 固定为 `streaming`
- paired thinking arm：
  - `default`
  - `disabled`
- 顺序执行，不并发
- 每个 arm 前后都执行 health check：`Return exactly: OK`
- 默认先 dry-run；只有 `--execute` 才调用 `gepa.optimize()`

## 默认真实执行参数

- `max_metric_calls = 1`
- `diagnostic_val_limit = 3`
- `seed_prompt = strong_format`
- `sleep_between_requests = 120`
- `max_retries = 0`

## timeout guard

### default arm

- `sdk_timeout_seconds = 1800`
- `first_token_timeout_seconds = 1800`
- `post_first_token_timeout_seconds = 900`
- `application_wall_clock_timeout_seconds = 2700`
- `emergency_guard_timeout_seconds = 3600`

### disabled arm

- `sdk_timeout_seconds = 900`
- `first_token_timeout_seconds = 300`
- `post_first_token_timeout_seconds = 900`
- `application_wall_clock_timeout_seconds = 1200`
- `emergency_guard_timeout_seconds = 1800`

### 分类规则

- 首 token 前超时：`FirstTokenTimeout`
- 首 token 后超时：`PostFirstTokenTimeout`
- 单请求整体墙钟超时：`ApplicationWallClockTimeout`
- 整个 arm 超出紧急保护：`EmergencyGuardTimeout`

## artifact 设计

所有结果写入：

- `outputs/stage4c_glm_streaming_gepa_sanity/<timestamp>/`

至少保存：

- `input_snapshot.json`
- `paired_results.json`
- `run_summary.json`
- `failure_cases.json`
- `health_checks.jsonl`
- `per_request_eval.jsonl`
- `arms/<thinking_type>/arm_result.json`
- `raw_responses/*.json`

## 报告边界标记

报告必须包含：

- `diagnostic_only = true`
- `not_official_budget = true`
- `not_performance_claim = true`
- `not_model_ranking = true`
- `not_strict_default_path = true`
- `streaming_path_only = true`
- `glm_backend = true`
- `paired_thinking_diagnostic = true`

## 测试要求

- dry-run 不调模型、不进 `gepa.optimize()`
- 只有 `--execute` 才进 GEPA
- API key 不写入 artifacts / report
- default arm 在 disabled arm 之前
- health check 失败阻止对应 arm
- patch `completion/batch_completion` 后恢复原函数
- timeout 分类明确
- 输出不包含本地绝对路径

## 结果解释边界

可以写：

- GLM 在 streaming GEPA micro-sanity 下是否跑通最小闭环
- default / disabled thinking 两个 arm 是否都完成
- health check 是否正常
- 请求级首 token / complete 时间与 timeout 类型

不能写：

- GLM 比 MiMo 强
- GLM 已适合 official_budget
- GLM 已具备 GEPA 正式复现 readiness
- 任何模型能力排名结论
