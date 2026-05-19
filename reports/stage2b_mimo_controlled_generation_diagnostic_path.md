# Stage 2B MiMo controlled-generation diagnostic path

## 定位

- 该路径是 `Stage 2B: MiMo controlled-generation diagnostic path`
- 它不是 `strict_readme_quickstart_path` 的 execute completion
- 它不是 GEPA smoke
- 它不是 `original same-model reproduction`

## 不变边界

- 不修改 `GEPA optimizer`
- 不修改 `DefaultAdapter`
- 不修改 evaluator
- 不引入 callable
- 不改写 Stage 1 DeepSeek 历史结论

## 路径特征

该路径显式使用：

- `thinking.disabled`
- `max_completion_tokens` 上限
- proxy reachable path

因此它不是 strict official path，也不能和 strict path 混写。

## 作用

该路径只用于确认以下事实：

1. MiMo endpoint 可达
2. key 有效
3. MiMo 可对真实 AIME 单样本返回非空 `content`
4. LiteLLM `openai/<model>` 在受控生成条件下可返回非空 `content`

它不用于：

- GEPA optimize
- smoke / pilot 实验
- 性能结论
- 与 GEPA 原论文分数对标

## 默认控制参数

- 模型：`mimo-v2.5-pro`
- Base URL：`https://token-plan-cn.xiaomimimo.com/v1`
- `thinking.type = disabled`
- `max_completion_tokens = 512`
- `timeout = 120`

## 代码与输出

- 脚本：`scripts/02_validate_mimo_controlled_generation_path.py`
- 输出目录：`outputs/mimo_controlled_generation_validation/<timestamp>/controlled_generation_results.json`

输出 JSON 至少包含以下解释字段：

- `path_type = stage2b_mimo_controlled_generation_diagnostic_path`
- `not_strict_official_path = true`
- `not_performance_claim = true`
- `no_gepa_optimize_called = true`

## 当前结论

- 该路径已经证明 MiMo 在受控生成条件下可以完成真实 AIME 单样本返回
- 该路径不等于 strict default path 已闭环
- 该路径不等于 MiMo GEPA smoke 已完成

## 后续分叉

### A. strict default path 未来可稳定返回

如果未来 strict default path 可以在稳定可达路径上返回，再回到 strict execute sanity。

### B. 只有 controlled-generation path 可用

如果未来仍然只有这条受控生成路径可用，则它必须单独作为非 strict 诊断路径报告，不能混写成 strict official path。

### C. 未来要让 GEPA 使用这些生成控制参数

如果未来要让 GEPA 也显式使用：

- `thinking.disabled`
- `max_completion_tokens` 上限

则必须另开 `Stage 2C: MiMo explicitly controlled-generation GEPA path`，并明确标注它偏离 strict official path。
