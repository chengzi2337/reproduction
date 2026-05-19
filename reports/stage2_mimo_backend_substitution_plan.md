# Stage 2 Xiaomi MiMo backend-substitution plan

## 定位

- MiMo 路径只定义为 `Stage 2: Xiaomi MiMo backend-substitution experiment`
- 当前项目整体仍然是 `GEPA method-level reproduction`
- 该路径 **不是** `original same-model reproduction`
- 该路径 **不是** Stage 1 DeepSeek wrapper baseline 的改写

## 不变项

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

## 解释边界

- MiMo 路径不构成 `original same-model reproduction`
- MiMo 路径不直接对标 GEPA 原论文分数
- MiMo 路径不与 Stage 1 DeepSeek wrapper baseline 混写
- MiMo 结果只能解释为：
  - 在 GEPA 官方核心路径不变的前提下，替换到 Xiaomi MiMo OpenAI-compatible backend 的 Stage 2 backend-substitution 观察结果

## provider 与 temperature 说明

- provider：`mimo`
- backend_family：`openai_compatible`
- MiMo thinking 模式下，`mimo-v2.5-pro` 和 `mimo-v2.5` 的 temperature 视为 `provider-controlled`
- 因此本项目中对 MiMo 仍然只能写：
  - `temperature not explicitly controlled`
  - `provider-controlled`
- 不能声称：
  - `temperature_task=0.0 已生效`
  - `temperature_reflection=0.7 已生效`

## 当前实现范围

- 抽象 `OpenAI-compatible` 通用工具层
- 保留 `src/deepseek_utils.py` 作为兼容层，避免破坏 Stage 1
- 扩展 `src/config.py` 支持：
  - `deepseek`
  - `mimo`
- 新增 MiMo 配置：
  - [mimo_smoke.yaml](C:/Users/lin/Documents/New%20project%202/configs/mimo_smoke.yaml)
  - [mimo_pilot.yaml](C:/Users/lin/Documents/New%20project%202/configs/mimo_pilot.yaml)
- 新增 MiMo probe 脚本：
  - [00_check_mimo_models.py](C:/Users/lin/Documents/New%20project%202/scripts/00_check_mimo_models.py)

## 后续实验顺序

1. raw OpenAI SDK probe
2. LiteLLM `openai/<model>` probe
3. strict README quickstart dry-run
4. MiMo smoke `max_metric_calls=10`
5. saved prompt eval `limit=10`
6. MiMo pilot `max_metric_calls=50`
7. full saved prompt eval

## 与 Stage 1 的关系

- Stage 1 DeepSeek wrapper path 已封版
- 本次改动不改写任何 Stage 1 历史结论
- 本次改动不要求重跑 Stage 1 baseline
- DeepSeek 仍然保留为已完成的 Stage 1 backend 路径
- MiMo 是新增的 Stage 2 backend-substitution 路径

## 当前结论

- 这次改动的目标不是证明 MiMo 分数优于或等于原论文
- 这次改动的目标是把项目从 `DeepSeek-only backend` 扩展为 `OpenAI-compatible multi-provider backend`
- 在这个边界内，MiMo 只承担 Stage 2 provider-substitution 的角色
