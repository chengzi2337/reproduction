# Stage 1 下一阶段：环境复验后的 fresh pilot 确认计划

> Status: Superseded.
>
> 本文档记录的是 `official_budget` 运行前的 revalidation 计划。
> 实际的 `official_budget` 结果已归档于
> `reports/stage1_official_budget_revalidation_result.md`。

## 文档定位

- 本文档用于固化当前主线回退后的下一阶段执行计划。
- 本文档只定义 `environment revalidation` 的目标、边界与执行顺序。
- 本文档**不是** `Stage 1` 历史结论重写。
- 本文档**不是**新的 baseline 封版报告。

## 当前状态

### 已确认成立

- 当前项目定位仍是 `GEPA method-level reproduction with DeepSeek backend`
- 当前项目**不是** `original same-model reproduction`
- `Stage 1` 历史封版结论仍以 `reports/stage1_final_status.md` 为准
- 当前主验证环境仍是 `WSL Ubuntu-22.04-Fresh`
- 已存在历史 `smoke / pilot / saved prompt eval` 静态归档：
  - `reports/stage1_deepseek_method_reproduction_report.md`
- 主线回退后的最新 smoke 复验结果为：
  - `run dir = outputs/gepa_aime_smoke/20260521T235647+0800`
  - `best_score = 0.13333333333333333`

### 当前不应做

- 不继续 MiMo
- 不继续 GLM
- 不运行 `official_budget`
- 不修改 GEPA optimizer
- 不修改 evaluator
- 不重写 `reports/stage1_final_status.md`
- 不重新引入 strict continuation / Stage 2 诊断链

## 下一阶段主线

### 阶段名称

`Stage 1 环境复验后的 fresh pilot 确认阶段`

### 核心问题

> 在已经回退到干净主线后，项目是否还能在主验证环境里，重新完成一条“从 smoke 到 pilot 到 saved prompt eval”的完整 Stage 1 链路？

### 为什么先做这件事

如果这条链路能够重新跑通，至少说明：

- 当前仓库主线是干净的
- 当前 WSL 主验证环境可复用
- 当前 Stage 1 不是只能依赖历史 artifacts 才成立

## 固定边界

- `not_stage1_rewrite = true`
- `not_same_model_reproduction = true`
- `not_official_budget = true`

进一步约束：

- Windows 原生直连环境当前**不是** primary supported path
- 所有模型调用都应在 `WSL Ubuntu-22.04-Fresh` 下完成
- fresh pilot 只用于 revalidation，不用于改写 Stage 1 历史封版结论

## 阶段拆分

### 阶段 A：封存这次环境复验 smoke

新增：

- `reports/stage1_environment_revalidation_smoke_result.md`

必须写清楚：

- 这是在主线回退到 `7fb8ecd` 之后做的环境复验
- 主验证环境是 `WSL Ubuntu-22.04-Fresh`
- Windows 直连环境当前不作为 primary supported path
- 本次 smoke 只说明：
  - 环境可用
  - Stage 1 闭环仍可重新跑通
- 不改写原 `reports/stage1_final_status.md`
- 应记录字段：
  - `run dir`
  - `provider`
  - `task_model`
  - `reflection_model`
  - `dataset source`
  - `train/val/test sizes`
  - `best_score`
  - `max_metric_calls`
  - `not_stage1_rewrite = true`
  - `not_new_baseline = true`

### 阶段 B：运行 fresh Stage 1 pilot

使用现有入口：

- `scripts/03_run_gepa_aime_pilot.py`
- `configs/deepseek_pilot.yaml`

固定参数保持不变：

- `provider = deepseek`
- `task_model = deepseek-v4-flash`
- `reflection_model = deepseek-v4-pro`
- `max_metric_calls = 50`
- `seed = 42`

### 阶段 C：对 fresh pilot 做 saved prompt eval

在 fresh pilot 成功后运行：

- `scripts/05_eval_saved_prompt.py`

目标不是追求更高分，而是验证：

- 当前干净主线下仍能出现 prompt evolution
- 当前 fresh pilot 的 saved prompt eval 仍能形成有效对照

### 阶段 D：形成 fresh revalidation checkpoint

新增：

- `reports/stage1_environment_revalidation_pilot_result.md`

必须写清楚：

- 这是 fresh revalidation pilot
- 它不是 Stage 1 历史结果重写
- 它不是 `official_budget`
- 它不是 `same-model reproduction`

## 实验定义

### 实验名称

`Stage 1 fresh pilot revalidation`

### 实验目的

验证在当前干净主线与主验证环境下，项目是否还能重新完成：

- pilot 执行
- prompt evolution
- saved prompt eval

### 推荐环境

- `WSL Ubuntu-22.04-Fresh`
- `.venv-wsl`

## 前置检查

按顺序执行：

1. `scripts/00_check_env.py`
2. `scripts/01_check_deepseek_models.py --config configs/deepseek_pilot.yaml`
3. `scripts/03_run_gepa_aime_pilot.py --config configs/deepseek_pilot.yaml`

## 推荐命令顺序

WSL 中执行：

```bash
export DEEPSEEK_API_KEY="你的临时 key"
export DEEPSEEK_API_BASE="https://api.deepseek.com"
export TASK_MODEL="deepseek-v4-flash"
export REFLECTION_MODEL="deepseek-v4-pro"

.venv-wsl/bin/python scripts/00_check_env.py

.venv-wsl/bin/python scripts/01_check_deepseek_models.py \
  --config configs/deepseek_pilot.yaml

.venv-wsl/bin/python scripts/03_run_gepa_aime_pilot.py \
  --config configs/deepseek_pilot.yaml
```

如果 pilot 成功，再执行：

```bash
.venv-wsl/bin/python scripts/05_eval_saved_prompt.py \
  --run-dir outputs/gepa_aime_pilot/<新的时间戳目录>
```

## 成功标准

本轮至少满足以下全部条件：

1. `check_env` 通过
2. `model probe` 通过
3. `pilot` 成功完成并生成 `gepa_result_summary.json`
4. `total_metric_calls > 45`
5. 存在 candidate expansion 或 prompt evolution 的明确迹象，至少满足其一：
   - `num_candidates > 1`
   - 或 stdout/stderr/log 中出现非 baseline-only 的迭代迹象
   - 或 `optimized_prompt != seed_prompt`
6. `saved prompt eval` 成功完成

## 停机条件

出现以下任一情况就先停，不继续放大预算：

- provider connectivity error
- pilot 失败
- result summary 缺失
- `max_metric_calls = 50` 仍完全停留在 baseline-only
- saved prompt eval 失败
- 需要修改 GEPA optimizer / evaluator 才能继续

## 结果归档要求

### fresh pilot 结果报告应记录

- `run dir`
- `provider`
- `task_model`
- `reflection_model`
- `max_metric_calls`
- `total_metric_calls`
- `best_score`
- `num_candidates`
- `num_full_val_evals`
- `optimized_prompt` 是否与 `seed_prompt` 不同
- `saved prompt eval` 是否完成
- `seed prompt eval score`
- `optimized prompt eval score`

### 结果报告必须显式声明

- `not_stage1_rewrite = true`
- `not_same_model_reproduction = true`
- `not_official_budget = true`

## 本阶段不要做的事

- 不运行 `official_budget`
- 不重启 MiMo
- 不重新走 strict continuation
- 不改 Stage 1 定位
- 不把 fresh revalidation pilot 写成新 baseline 封版

## 允许提交范围

允许提交：

- `reports/stage1_next_phase_revalidation_plan.md`
- `reports/stage1_environment_revalidation_smoke_result.md`
- `reports/stage1_environment_revalidation_pilot_result.md`
- 如有必要，对 `README.md` 做极小引用同步

不要提交：

- `outputs/*`
- `.codex/*`
- `reports/stage1_final_status.md` 的主体结论改动
- Stage 2 / MiMo 相关旧草稿
- handoff 文档
- 本地绝对路径
- API key

## 提交命名建议

1. `封存 Stage 1 environment revalidation smoke`
2. `封存 Stage 1 fresh pilot revalidation result`

## 面向执行窗口的最终输出要求

执行完成后应明确给出：

1. 实际运行的命令
2. fresh pilot 的 `run dir`
3. saved prompt eval 的 `run dir`
4. 这是否只是 `environment revalidation`，而不是 `Stage 1` 重写
5. 是否已经具备继续讨论更大预算的条件

## 当前文档结论

- 当前最合理的下一步是：只做 `fresh pilot revalidation`
- 不并行扩展其他研究分支
- 先封存 smoke revalidation checkpoint，再跑 fresh pilot，再做 saved prompt eval，最后决定是否讨论更大预算
