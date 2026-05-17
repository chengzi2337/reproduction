# GEPA DeepSeek Reproduction

## 温度控制说明

- 当前配置文件中存在 `temperature_task` 和 `temperature_reflection`
- 但基于当前安装包源码检查，`gepa.optimize()` 默认字符串模型路径没有显式消费这两个配置
- 因此 Stage 1 当前应理解为：
  - `temperature is not explicitly controlled unless GEPA default path applies it internally`
- 当前仓库不应暗示 `temperature_task=0.0` 或 `temperature_reflection=0.7` 已被严格控制进模型调用
- 详见 `reports/temperature_control_audit.md`

项目目标：
使用 DeepSeek OpenAI-compatible API 复现 GEPA 的核心 prompt evolution 闭环。

实验性质：
- `GEPA method-level reproduction with DeepSeek backend`
- 这不是 `original same-model reproduction`
- 当前仓库只覆盖 `Stage 1 smoke/pilot baseline`

复用原则：
- 优先复用 GEPA 官方 AIME 数据入口 `gepa.examples.aime.init_dataset()`
- 优先复用 GEPA 官方优化入口 `gepa.optimize()`
- 优先复用 GEPA 官方默认适配器 `DefaultAdapter`
- DeepSeek 只作为 OpenAI-compatible 后端替换，不自写 provider、optimizer、benchmark 或 metric

## 当前状态

- 已完成：`Stage 1 smoke/pilot baseline`
- 已验证主环境：`WSL Ubuntu-22.04-Fresh`
- 未完成：论文级多 seed / 多任务 / 多模型结论
- 未运行：`official_budget`

已验证的真实运行结果位于：
- `outputs/gepa_aime_smoke/20260517T152050+0800`
- `outputs/gepa_aime_pilot/20260517T155236+0800`

对应的静态脱敏报告位于：
- `reports/stage1_deepseek_method_reproduction_report.md`

## Stage 1 Reports

- `reports/stage1_deepseek_method_reproduction_report.md`
  - Stage 1 `smoke / pilot` 静态脱敏实验报告
- `reports/official_core_path_comparison.md`
  - 官方核心路径与自定义外壳偏差对照
- `reports/temperature_control_audit.md`
  - `temperature` 控制语义审计
- `reports/stage1_final_status.md`
  - Stage 1 封版状态说明

## 主运行环境

Primary verified environment: `WSL Ubuntu-22.04-Fresh`

说明：
- Stage 1 主推荐运行路径是 WSL。
- Windows 原生执行路径曾出现 `OSError: [Errno 22] Invalid argument`。
- `Windows native execution is not treated as the primary supported path in Stage 1`。

## 模型配置

推荐角色：
- `TASK_MODEL=<your-available-deepseek-chat-model>`
- `REFLECTION_MODEL=<your-available-deepseek-stronger-model>`

已验证过的一组示例配置：
- `TASK_MODEL=deepseek-v4-flash`
- `REFLECTION_MODEL=deepseek-v4-pro`

实际模型名必须以你的 DeepSeek 账号可调用列表为准。代码不会自动替换模型。

## 关键边界

- 不允许模型训练
- 不允许实现新方法
- 不允许做 `regression-aware gate`
- 不允许做 `cost-aware gate`
- 不允许做通用大 harness
- 不允许自写 benchmark、provider、GEPA optimizer、AIME evaluator
- 不允许自动替换模型
- 不新增 OpenRouter、GPT 模型、dashboard、数据库、Docker

## 安装步骤

### WSL / Ubuntu 推荐方式

```bash
python3 -m venv .venv-wsl
source .venv-wsl/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### Windows PowerShell 方式

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

说明：
- 推荐环境是 WSL Ubuntu 22.04 / 24.04，Python 3.10 / 3.11。
- 官方 AIME 示例依赖 `datasets`，所以 `requirements.txt` 包含它。
- 本工程不修改 GEPA 源码，只适配当前安装版本的官方入口。

## 环境变量

### Bash / WSL

```bash
export DEEPSEEK_API_KEY="你的真实 DeepSeek key"
export DEEPSEEK_API_BASE="https://api.deepseek.com"
export TASK_MODEL="<your-available-deepseek-chat-model>"
export REFLECTION_MODEL="<your-available-deepseek-stronger-model>"
```

### PowerShell

```powershell
$env:DEEPSEEK_API_KEY="你的真实 DeepSeek key"
$env:DEEPSEEK_API_BASE="https://api.deepseek.com"
$env:TASK_MODEL="<your-available-deepseek-chat-model>"
$env:REFLECTION_MODEL="<your-available-deepseek-stronger-model>"
```

如果你的实际模型名不同，请替换 `TASK_MODEL` 和 `REFLECTION_MODEL`。

## 运行顺序

```bash
python scripts/00_check_env.py

python scripts/01_check_deepseek_models.py \
  --config configs/deepseek_smoke.yaml

python scripts/02_run_gepa_aime_smoke.py \
  --config configs/deepseek_smoke.yaml

python scripts/05_eval_saved_prompt.py \
  --run-dir outputs/gepa_aime_smoke/<timestamp>
```

pilot 运行：

```bash
python scripts/03_run_gepa_aime_pilot.py \
  --config configs/deepseek_pilot.yaml
```

official budget 运行：

```bash
python scripts/04_run_gepa_aime_official_budget.py \
  --config configs/deepseek_official_budget.yaml \
  --yes
```

注意：
- 当前阶段不建议先跑 `official_budget`。
- 建议先完成 smoke、pilot 和保存 prompt 的评估。

## 预算说明

- `max_metric_calls` 不保证等于最终 `total_metric_calls`
- GEPA 可能会先执行完整 baseline evaluation，因此实际 `total_metric_calls` 可能更高

例如：
- smoke 配置里 `max_metric_calls=10`
- 已验证 smoke run 的 `total_metric_calls=45`

## 输出目录说明

每次运行都会生成独立目录：

```text
outputs/<experiment_name>/<timestamp>/
```

当前默认配置下会落到：
- `outputs/gepa_aime_smoke/<timestamp>/`
- `outputs/gepa_aime_pilot/<timestamp>/`
- `outputs/gepa_aime_official_budget/<timestamp>/`

目录内常见产物：
- `manifest.json`
- `config_resolved.yaml`
- `package_versions.txt`
- `stdout.log`
- `stderr.log`
- `seed_prompt.json`
- `optimized_prompt.json`
- `gepa_result_summary.json`
- `raw_result.json`
- `notes.md`

默认情况下：
- `save_raw_pickle=false`
- 不再默认保存 `raw_result.pkl`

若 `result.to_dict()` 不可用且 `save_raw_pickle=false`，只会在 `notes.md` 中记录原因。

执行 `scripts/05_eval_saved_prompt.py` 后还会追加：
- `per_example_eval.jsonl`
- `saved_prompt_eval_summary.json`

## 常见错误

- `DEEPSEEK_API_KEY` 未设置
- `DEEPSEEK_API_BASE` 错误
- `TASK_MODEL` 模型名不可用
- `REFLECTION_MODEL` 模型名不可用
- 余额不足
- 限流
- GEPA examples API 路径变化
- DeepSeek OpenAI-compatible 调用参数不兼容
- Windows 原生路径触发 `OSError: [Errno 22] Invalid argument`

## 范围声明

- 本工程只覆盖 DeepSeek 后端的方法级复现
- 当前只完成 `Stage 1 smoke/pilot baseline`
- 不包含训练、额外 benchmark 扩展、Web UI、数据库、Docker 或成本/回归门控
- 不新增自写 provider、GEPA optimizer、AIME evaluator
- 当前结果不能直接当作论文最终结论
