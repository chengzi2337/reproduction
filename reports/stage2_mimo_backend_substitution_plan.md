# Stage 2 Xiaomi MiMo Backend-Substitution Plan

## 定位

- MiMo 路径只定义为 `Stage 2: Xiaomi MiMo backend-substitution experiment`
- 整个仓库仍然是 `GEPA method-level reproduction and backend-substitution study`
- 它不是 `original same-model reproduction`
- 它不改写 Stage 1 DeepSeek 历史结论

## 不变边界

- 不修改 `GEPA optimizer`
- 不修改 `gepa.examples.aime.init_dataset()`
- 不修改默认 evaluator
- 不修改 Stage 1 历史结果
- 不把 MiMo 路径写成 strict official path
- 不把 MiMo 路径写成性能实验
- 不启动 pilot / official_budget
- 不进行 saved prompt eval

## MiMo 配置边界

- `provider = mimo`
- `backend_family = openai_compatible`
- `provider=mimo` 时必须显式设置 `MIMO_API_BASE`
- 当前已验证的 Token Plan OpenAI-compatible endpoint：
  - `https://token-plan-cn.xiaomimimo.com/v1`
- MiMo thinking 模式下的 temperature 只允许表述为：
  - `temperature not explicitly controlled`
  - `provider-controlled`

## Stage 2A 已完成事项

- provider connectivity 可用
- key 有效
- LiteLLM `openai/<model>` 路径可用
- prompt complexity decomposition 已完成
- `first_blocked_level = 3`
- Level 0-2 passed
- Level 3-5 `HardTimeout`
- direct SDK 与 LiteLLM 行为一致
- blocker 由真实 AIME 题面复杂度在 MiMo strict default generation 下触发
- `README quickstart seed prompt` 不是主触发因素
- `official AIME-style seed prompt` 不能移除 blocker
- Stage 2A 没有调用 `gepa.optimize()`
- Stage 2A 没有使用 `thinking.disabled`
- Stage 2A 没有使用 `max_completion_tokens`

## Stage 2B 已完成事项

- 在 `thinking.disabled`
- 且 `max_completion_tokens = 512`
- 且 provider / LiteLLM 路径可达

的条件下，MiMo 可以对真实 AIME 单样本返回非空 `content`。

这只是 `Stage 2B: controlled-generation diagnostic path`，不是 strict path，不是 GEPA smoke。

## Stage 2C 当前节点

- Stage 2A strict default path 当前 blocked
- 因此当前转入 `Stage 2C: MiMo explicitly controlled-generation GEPA path`
- Stage 2C 的 design and scaffold 已完成
- Stage 2C 的第一次 `max_metric_calls = 1` controlled-generation sanity 已通过
- Stage 2C 的第一次 `max_metric_calls = 10` controlled-generation smoke 已通过

## Stage 2C 当前解释边界

- 已验证 controlled-generation 条件下的最小 GEPA 闭环可执行性
- 已验证 controlled-generation 条件下的 smoke execution-stability 闭环可执行性
- 当前还没有 pilot
- 当前还没有 saved prompt eval
- 当前不和 DeepSeek Stage 1 对比
- 当前不写性能结论
- `best_score = 0.0` 只作为 smoke-run artifact / warning signal 记录

## 当前明确禁止

- 不运行 `configs/mimo_pilot.yaml`
- 不把 Stage 2C 写成 strict path
- 不把 Stage 2C 写成 MiMo baseline
- 不把 Stage 2C 写成 GEPA original reproduction
- 不把 smoke 结果解释成模型有效性能

## 下一步

- 当前下一步应先做 `Stage 2C smoke failure-mode audit design`
- 在 audit 完成前，不直接运行 pilot
- 若 audit 认为需要调整参数，应先做参数调整设计，再决定是否重跑 sanity / smoke
## Stage 2C smoke audit checkpoint

- Stage 2C smoke result 已封存
- Stage 2C smoke failure-mode audit 已完成只读审计
- 当前已确认：
  - `45/45` 样本存在非空正文
  - `0/45` 样本出现精确的 `### <answer>`
  - 至少 `23/45` 样本出现明显截断
- 因此，当前 `0.0` 更接近格式与截断问题，而不是“完全无输出”
- 当前不进入 pilot
- 当前下一步应先做 `Stage 2C parameter-adjustment design`

## Stage 2C parameter-adjustment checkpoint

- Stage 2C parameter-adjustment diagnostic 已完成
- 当前已确认：
  - `1024` 仍然会触发 `finish_reason = length`
  - `2048` 已可到 `finish_reason = stop`
  - 但两种设置都未稳定产出精确的 `### <answer>`
- 因此，当前问题已从“token 太低导致截断”进一步收敛到：
  - `token 上限不足` 是部分原因
  - `最终答案格式可达性不足` 仍然存在
- 当前不进入 pilot
- 当前下一步应先做 `Stage 2C prompt-first / format-enforcement design`
