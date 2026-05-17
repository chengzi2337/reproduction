# GEPA DeepSeek Reproduction

项目目标：
使用 DeepSeek OpenAI-compatible API 复现 GEPA 的核心 prompt evolution 闭环。

实验性质：
GEPA method-level reproduction with DeepSeek backend。
这不是 original same-model reproduction。

复用原则：

- 优先复用 GEPA 官方 AIME 数据入口 `gepa.examples.aime.init_dataset()`
- 优先复用 GEPA 官方优化入口 `gepa.optimize()`
- 优先复用 GEPA 官方默认适配器 `DefaultAdapter`
- DeepSeek 只作为 OpenAI-compatible 后端替换，不自写 provider、optimizer、benchmark 或 metric

推荐模型角色：

- `task_lm = cheaper/faster DeepSeek model`
- `reflection_lm = stronger DeepSeek model`

示例：

- `TASK_MODEL=deepseek-v4-flash`
- `REFLECTION_MODEL=deepseek-v4-pro`

实际模型名以你的 DeepSeek 账号可调用列表为准。如果你的账号使用其他模型名，请修改环境变量或 YAML 配置；代码不会自动替换模型。

关键边界：

- 不允许模型训练。
- 不允许实现新方法。
- 不允许做 `regression-aware gate`。
- 不允许做 `cost-aware gate`。
- 不允许做通用大 harness。
- 不允许自写 benchmark、provider、GEPA optimizer、AIME evaluator。
- 不允许自动替换模型。

安装步骤

WSL / Ubuntu 推荐方式：

```bash
python3 -m venv ~/venvs/gepa_deepseek
source ~/venvs/gepa_deepseek/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Windows PowerShell 方式：

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

说明：

- 推荐环境是 WSL Ubuntu 22.04 或 24.04，Python 3.10 或 3.11。
- 官方 AIME 示例依赖 `datasets`，所以 `requirements.txt` 额外包含它。
- 本工程不修改 GEPA 源码，只适配当前安装版本的官方入口。
- 若 Windows 本机的 Hugging Face 数据集访问受限，优先改在 WSL 中运行 smoke / pilot。

环境变量：

```bash
export DEEPSEEK_API_KEY="你的真实 DeepSeek key"
export DEEPSEEK_API_BASE="https://api.deepseek.com"
export TASK_MODEL="deepseek-v4-flash"
export REFLECTION_MODEL="deepseek-v4-pro"
```

PowerShell 写法：

```powershell
$env:DEEPSEEK_API_KEY="你的真实 DeepSeek key"
$env:DEEPSEEK_API_BASE="https://api.deepseek.com"
$env:TASK_MODEL="deepseek-v4-flash"
$env:REFLECTION_MODEL="deepseek-v4-pro"
```

如果你的实际模型名不同，请替换 `TASK_MODEL` 和 `REFLECTION_MODEL`。

运行顺序：

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

结果怎么看：

- 模型检查是否通过。
- GEPA 是否完成 `max_metric_calls`。
- 是否生成 `optimized_prompt.json`。
- 是否保存 `manifest.json`。
- 是否保存 `package_versions.txt`。
- `seed_prompt.json` 和 `optimized_prompt.json` 是否能评估。
- 是否没有泄露 key。

常见错误：

- `DEEPSEEK_API_KEY` 未设置。
- `DEEPSEEK_API_BASE` 错误。
- `TASK_MODEL` 模型名不可用。
- `REFLECTION_MODEL` 模型名不可用。
- 余额不足。
- 限流。
- GEPA examples API 路径变化。
- DeepSeek OpenAI-compatible 调用参数不兼容。
- `max_metric_calls` 过高导致成本增加。
- Windows 本机无法顺畅访问 Hugging Face 数据集缓存或网络，导致 AIME 初始化很慢。

输出目录说明：

每次运行都会生成独立目录：

```text
outputs/<experiment_name>/<timestamp>/
```

当前默认配置下会落到：

- `outputs/gepa_aime_smoke/<timestamp>/`
- `outputs/gepa_aime_pilot/<timestamp>/`
- `outputs/gepa_aime_official_budget/<timestamp>/`

目录内至少包含：

- `manifest.json`
- `config_resolved.yaml`
- `package_versions.txt`
- `stdout.log`
- `stderr.log`
- `seed_prompt.json`
- `optimized_prompt.json`
- `gepa_result_summary.json`
- `raw_result.json` 或 `raw_result.pkl`
- `notes.md`

执行 `scripts/05_eval_saved_prompt.py` 后还会追加：

- `per_example_eval.jsonl`
- `saved_prompt_eval_summary.json`

范围声明：

- 本工程只覆盖 DeepSeek 后端的方法级复现。
- 不包含训练、额外 benchmark 扩展、Web UI、数据库、Docker 或成本/回归门控。
- 不新增自写 provider、GEPA optimizer、AIME evaluator。
