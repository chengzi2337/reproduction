# Stage 2C MiMo Controlled-Generation GEPA Smoke Design

## 定位

- 本文档定义 `Stage 2C: MiMo explicitly controlled-generation GEPA path` 的 smoke 设计。
- 本文档只做设计，不启动运行。
- 本文档不是 smoke result。
- 本文档不是性能结论。
- 本文档不是 strict official path 设计。

## 前置事实

### Stage 2A 已知结论

- `first_blocked_level = 3`
- Level 0-2 passed
- Level 3-5 `HardTimeout`
- direct SDK 与 LiteLLM 行为一致
- blocker 由真实 AIME 题面复杂度在 MiMo strict default generation 下触发
- `README quickstart seed prompt` 不是主触发因素
- `official AIME-style seed prompt` 不能移除 blocker

### Stage 2B 已知结论

- 在 `thinking.disabled`
- 且 `max_completion_tokens = 512`
- 且 provider / LiteLLM 路径可达

的条件下，MiMo 可以对真实 AIME 单样本返回非空 `content`。

### Stage 2C sanity 已知结论

- `Stage 2C controlled-generation GEPA sanity passed`
- `max_metric_calls = 1`
- `execution_completed = true`
- `controlled_generation_applied = true`
- 没有无界挂起

## 设计目标

Stage 2C smoke 的目标不是性能评估，而是：

> 在 controlled-generation 条件下，把 GEPA 从最小 sanity 扩展到一个更稳定、但仍然严格受限的 execution-stability 检查。

## 非 strict 声明

必须持续明确：

- Stage 2C smoke 仍然是 non-strict controlled-generation path
- Stage 2C smoke 不是 `strict_readme_quickstart_path`
- Stage 2C smoke 不是 original same-model reproduction
- Stage 2C smoke 不是 Stage 1 DeepSeek continuation
- Stage 2C smoke 不是 baseline
- Stage 2C smoke 不是性能实验
- Stage 2C smoke 不和 Stage 1 DeepSeek 直接比较

## 范围

### 允许范围

- `provider = mimo`
- `backend_family = openai_compatible`
- `task_model = mimo-v2.5-pro`
- `reflection_model = mimo-v2.5-pro`
- `thinking.type = disabled`
- `max_completion_tokens = 512`
- `timeout_seconds = 120`
- `max_metric_calls = 10`
- 使用 `gepa.examples.aime.init_dataset()`
- 使用 README quickstart seed prompt

### 明确禁止

- 不进入 pilot
- 不进入 official_budget
- 不进行 saved prompt eval
- 不修改 GEPA optimizer
- 不修改 evaluator
- 不修改 Stage 1 历史结果
- 不写性能优劣结论
- 不把结果称为 baseline

## 关于 max_metric_calls 的解释

- `max_metric_calls = 10` 只能解释为 GEPA 控制参数。
- 它不是 provider-call count 的保证值。
- 不能把它写成“只调用 10 次模型”。
- Stage 2C sanity 已经表明：
  - `max_metric_calls = 1`
  - 但 `total_metric_calls = 45`
- 因此 smoke 设计中必须持续把 `max_metric_calls` 与实际 provider 调用次数分开记录。

## 运行入口设计

当前不建议直接复用：

- `scripts/stage2c_run_mimo_controlled_generation_gepa_sanity.py`

去执行 smoke，并继续写入：

- `path_type = stage2c_mimo_controlled_generation_gepa_sanity`

否则会污染后续报告边界。

更稳的做法是后续单独实现其一：

### 方案 A：新增 smoke guarded runner

- `scripts/stage2c_run_mimo_controlled_generation_gepa_smoke.py`

### 方案 B：让现有 runner 显式支持 run-kind

- `--run-kind sanity|smoke`

无论采用哪种方式，未来 smoke 都必须写入独立身份：

- `path_type = stage2c_mimo_controlled_generation_gepa_smoke`
- 独立 output_dir
- 独立 snapshot filename
- 独立 result summary filename

## 受控生成要求

Smoke 仍必须保持与 sanity 完全一致的 controlled-generation 参数：

- `thinking.disabled`
- `max_completion_tokens = 512`
- `timeout = 120`

不得在 smoke 阶段引入新的生成控制变量，否则会把 smoke 解释边界再次扩大。

## 成功标准

Stage 2C smoke 若未来运行，成功标准应收紧为：

- `execute_optimize = true`
- `path_type = stage2c_mimo_controlled_generation_gepa_smoke`
- `provider = mimo`
- `controlled_generation.enabled = true`
- `max_metric_calls = 10`
- `execution_completed = true`
- 生成独立 smoke result summary
- 没有无界挂起
- `total_metric_calls` 有记录
- `num_candidates` 有记录
- `num_full_val_evals` 有记录
- `not_performance_claim = true`
- `not_baseline = true`
- `not_pilot = true`

## 失败标准

若未来运行 smoke，以下任一条件都应视为失败：

- 再次出现不可恢复挂起
- 受控生成参数未生效
- provider / LiteLLM 返回不可恢复错误
- 输出结构无法稳定生成独立 smoke result summary
- 需要修改 GEPA optimizer 或 evaluator 才能继续

## 停止规则

- 只允许一次 `max_metric_calls = 10` smoke
- 成功后先写 smoke checkpoint，不自动进入 pilot
- 失败后先记录 `error_type` 与结果摘要，不反复重跑
- 如果出现 `HardTimeout`、provider instability 或 `content` 为空，不扩大 timeout 硬顶

## 报告规则

如果未来运行 smoke，结果只允许写成：

- `Stage 2C controlled-generation GEPA smoke passed`
- `Stage 2C controlled-generation GEPA smoke failed`

明确禁止写成：

- `MiMo baseline`
- `MiMo pilot`
- `MiMo strict path passed`
- `MiMo outperforms DeepSeek`
- `GEPA original reproduction`

## 当前决策

- 当前只完成 smoke design
- 当前不运行 smoke
- 当前不运行 pilot
- 当前不扩展到 saved prompt eval

## 下一步顺序

1. 审阅本设计文档
2. 若同意，先实现 smoke guarded runner 或 `run-kind` 支持
3. runner 审查通过后，再单独批准 Stage 2C smoke execute
4. smoke 通过后，先写 smoke result checkpoint
5. checkpoint 完成前，不讨论 pilot
