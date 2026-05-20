# GEPA Method-Level Reproduction and Backend-Substitution Study

本仓库用于开展 GEPA 的方法级复现与后端替换研究，不是 original same-model reproduction。

## 项目定位

- Stage 1 只定义为 `GEPA method-level reproduction with DeepSeek backend`
- Stage 2 只定义为 `Xiaomi MiMo backend-substitution experiment`
- 当前仓库不把任何结果表述为 `same-model reproduction`

## 当前状态

- Stage 1：DeepSeek method-level reproduction baseline，已封版
- strict path closure：`strict_readme_quickstart_path` 已完成 dry-run 和极小执行校验
- Stage 2A：MiMo strict default path diagnosis 已完成，当前被真实 AIME 题面复杂度阻塞
- Stage 2B：MiMo controlled-generation diagnostic path 已完成单样本验证
- Stage 2C：MiMo controlled-generation GEPA path 已完成 design and scaffold，并通过一次最小 sanity 与一次 smoke

## Stage 2A 关键结论

- `first_blocked_level = 3`
- Level 0-2 passed
- Level 3-5 `HardTimeout`
- direct SDK 与 LiteLLM 行为一致
- blocker 由真实 AIME 题面复杂度在 MiMo strict default generation 下触发
- `README quickstart seed prompt` 不是主触发因素，因为 Level 3 已经阻塞
- `official AIME-style seed prompt` 也不能移除 blocker
- Stage 2A 没有调用 `gepa.optimize()`
- Stage 2A 没有使用 `thinking.disabled`
- Stage 2A 没有使用 `max_completion_tokens`

## Stage 2B 关键结论

- `thinking.disabled`
- `max_completion_tokens = 512`
- direct SDK + 真实 AIME 单样本返回非空 `content`
- LiteLLM `openai/mimo-v2.5-pro` + 同条件返回非空 `content`

这些结果只说明 controlled-generation 单样本可达，不构成 strict path 成功，也不构成性能结论。

## Stage 2C 边界

- Stage 2C 是 `MiMo explicitly controlled-generation GEPA path`
- Stage 2C 不是 `strict_readme_quickstart_path`
- Stage 2C 不是 original same-model reproduction
- Stage 2C 是 non-strict controlled-generation engineering adaptation path
- Stage 2C 当前已经通过一次 `max_metric_calls = 1` sanity
- Stage 2C 当前已经通过一次 `max_metric_calls = 10` smoke
- Stage 2C 当前仍然没有 pilot / performance result
- Stage 2C sanity 和 smoke 都不能写成 baseline 或性能结论
- Stage 2C smoke 的 `best_score = 0.0` 只作为 warning signal 记录，不构成 MiMo 性能结论

## 当前不做的事

- 不重写 Stage 1 历史结论
- 不跑 `official_budget`
- 不新增 benchmark
- 不新增方法
- 不修改 `GEPA optimizer`
- 不修改默认 evaluator
- 不引入 callable 替代官方字符串模型路径
- 不运行 `configs/mimo_smoke.yaml`
- 不运行 `configs/mimo_pilot.yaml`

## 官方核心路径边界

当前所有 strict 对齐工作都围绕官方核心调用语义展开：

- `from gepa.examples.aime import init_dataset`
- `import gepa`
- `trainset, valset, testset = init_dataset()`
- `gepa.optimize(...)`
- `task_lm = "openai/<model>"`
- `reflection_lm = "openai/<model>"`

如果未来需要显式传入 `thinking.disabled`、`max_completion_tokens` 等生成控制参数，则必须单独标注为非 strict 路径。

## MiMo 配置边界

- `provider=mimo` 时，必须显式提供 `MIMO_API_BASE`
- 当前已验证可用的 Token Plan OpenAI-compatible endpoint：
  - `https://token-plan-cn.xiaomimimo.com/v1`
- 不应依赖隐式 MiMo 默认 Base URL

## 关键报告

- [reports/stage1_final_status.md](reports/stage1_final_status.md)
- [reports/official_core_path_comparison.md](reports/official_core_path_comparison.md)
- [reports/strict_readme_quickstart_sanity_status.md](reports/strict_readme_quickstart_sanity_status.md)
- [reports/stage2a_mimo_prompt_complexity_decomposition_result.md](reports/stage2a_mimo_prompt_complexity_decomposition_result.md)
- [reports/stage2_mimo_backend_substitution_plan.md](reports/stage2_mimo_backend_substitution_plan.md)
- [reports/stage2b_mimo_controlled_generation_diagnostic_path.md](reports/stage2b_mimo_controlled_generation_diagnostic_path.md)
- [reports/stage2c_mimo_controlled_generation_gepa_design.md](reports/stage2c_mimo_controlled_generation_gepa_design.md)
- [reports/stage2c_mimo_controlled_generation_gepa_sanity_result.md](reports/stage2c_mimo_controlled_generation_gepa_sanity_result.md)
- [reports/stage2c_mimo_controlled_generation_gepa_smoke_result.md](reports/stage2c_mimo_controlled_generation_gepa_smoke_result.md)
- [reports/stage2_current_status.md](reports/stage2_current_status.md)

## 运行环境说明

- Stage 1 主验证环境：`WSL Ubuntu-22.04-Fresh`
- MiMo 当前可用路径：代理可达环境
- Windows 直连 `token-plan-cn.xiaomimimo.com:443` 当前不视为稳定路径

## 验证原则

- 所有结论以本地可重复验证为准
- Stage 2B 当前只证明受控生成单样本可达，不构成性能结论
- Stage 2C 当前已完成一次最小 sanity 与一次 smoke，但仍不构成 pilot / performance result
