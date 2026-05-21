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

## Stage 2B 已完成事项

在：

- `thinking.disabled`
- `max_completion_tokens = 512`
- provider / LiteLLM 路径可达

的条件下，MiMo 可以对真实 AIME 单样本返回非空 `content`。

这只属于 `Stage 2B: controlled-generation diagnostic path`，不是 strict path，也不是 GEPA smoke。

## Stage 2C 当前结论

- Stage 2A strict default path 当前 blocked
- 因此后续转入 `Stage 2C: MiMo explicitly controlled-generation GEPA path`
- Stage 2C 的 design and scaffold 已完成
- Stage 2C 的：
  - `max_metric_calls = 1` sanity 已通过
  - `max_metric_calls = 10` smoke 已通过

但当前只证明：

- controlled-generation 条件下的最小 GEPA 闭环可执行
- smoke execution-stability 闭环可执行

当前不证明：

- pilot
- saved prompt eval
- 与 DeepSeek Stage 1 可比的性能结果

## Stage 2C 当前 failure mode

- smoke failure-mode audit 已确认：
  - `45/45` 样本有非空正文
  - `0/45` 样本出现精确 `### <answer>`
  - 至少 `23/45` 样本出现明显截断
- parameter-adjustment diagnostic 已确认：
  - `1024` 仍会 `finish_reason = length`
  - `2048` 已可到 `finish_reason = stop`
  - 但两种设置都不能稳定输出精确 `### <answer>`
- prompt-first diagnostic 已确认：
  - 三种 prompt 变体都未稳定通过格式门槛

因此当前已收敛为：

- 截断是部分原因
- 但当前主 blocker 已进一步收敛到：
  - `format_missing`
  - `output_protocol_violation`

## Stage 2D 当前结论

- Stage 2D 是 `output-protocol adaptation diagnostic`
- 已完成：
  - official evaluator format contract audit
  - existing outputs answer-extractability audit
  - official-contract prompt adaptation diagnostic

当前已明确：

- GEPA AIME official evaluator 需要的是形如 `### 72` 的精确字符串契约
- `normalized_score` 只能作为诊断字段，不能写成 official result
- prompt-only official-contract adaptation 当前不稳定

### Stage 2D Phase 2 final state

- `MiMo Stage 2D Phase 2 did not meet the entry gate for adapted GEPA smoke`
- `Prompt-only official-contract adaptation is not stable enough`
- 当前不应进入：
  - MiMo pilot
  - adapted GEPA smoke

## 当前主线决策

- 暂停 MiMo experimental expansion
- MiMo 当前保留为已完成的 Stage 2A / 2B / 2C / 2D 诊断资产
- 当前主线返回 `DeepSeek strict-readme continuation`
- 当前不做：
  - MiMo pilot
  - MiMo adapted GEPA smoke
  - `official_budget`

## 下一步

- MiMo 线当前先不扩展
- 若未来要重启 MiMo，必须先出现新的、不是 prompt-only 的解释性突破
- 当前最合理的仓库主线，是基于已完成的 DeepSeek strict continuation smoke，评估是否进入 strict continuation pilot
