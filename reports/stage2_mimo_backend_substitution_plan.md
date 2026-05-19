# Stage 2 Xiaomi MiMo backend-substitution plan

## 定位

- MiMo 路径只定义为 `Stage 2: Xiaomi MiMo backend-substitution experiment`
- 整个仓库仍然是 `GEPA method-level reproduction` 研究仓库
- 它不是 `original same-model reproduction`
- 它不改写 Stage 1 DeepSeek 历史结论

## 不变边界

- 不修改 `GEPA optimizer`
- 不修改 `gepa.examples.aime.init_dataset()`
- 不修改默认 evaluator
- 不引入 custom adapter
- 不引入 callable 替代官方字符串模型路径
- 保持官方核心调用语义：
  - `gepa.examples.aime.init_dataset()`
  - `gepa.optimize(...)`
  - `task_lm = "openai/<model>"`
  - `reflection_lm = "openai/<model>"`

## MiMo 配置边界

- `provider = mimo`
- `backend_family = openai_compatible`
- `provider=mimo` 时必须显式设置 `MIMO_API_BASE`
- 当前已验证的 Token Plan OpenAI-compatible endpoint：
  - `https://token-plan-cn.xiaomimimo.com/v1`
- MiMo thinking 模式下的 temperature 只能表述为：
  - `temperature not explicitly controlled`
  - `provider-controlled`

## 已完成事项

1. provider connectivity probe：已完成
2. LiteLLM `openai/<model>` probe：已完成
3. strict README quickstart dry-run：已完成
4. Stage 2B controlled-generation single-sample validation：已完成

## 当前解释边界

- 当前不把 MiMo 路径写成 strict official path 已完成
- 当前不把 MiMo 路径写成 GEPA smoke 已完成
- 当前不把 MiMo 结果写成性能结论
- 当前不把 MiMo 结果与 Stage 1 DeepSeek wrapper baseline 混写

## 当前稳定结论

- `mimo-v2.5-pro` 已在受控生成条件下通过 direct SDK 与 LiteLLM 单样本验证
- `mimo-v2-flash` 不再作为当前 Token Plan endpoint 的优先实验模型
- MiMo provider 已经接入，但 strict default execute 路径尚未闭环

## 下一步顺序

1. 已选择 `路线 A 的前半段`：优先尝试恢复 strict default path
2. 在路线 A 未闭环前，不进入 `Stage 2C: MiMo explicitly controlled-generation GEPA path`
3. 只有 strict default path 未来能够稳定返回时，才重新进入 strict execute sanity
4. 在 strict default path 未闭环前，不讨论 MiMo GEPA smoke / pilot
5. 在任何阶段，都不把 Stage 2B 混写成 strict execute completion

## 与 Stage 1 的关系

- Stage 1：DeepSeek method-level reproduction baseline，已封版
- Stage 2：MiMo backend-substitution 研究，不改写 Stage 1
- Stage 2B：MiMo controlled-generation diagnostic path，只证明受控生成单样本可达
- Stage 2C：尚未开始；若开启，必须明确标注为非 strict 工程适配路径
