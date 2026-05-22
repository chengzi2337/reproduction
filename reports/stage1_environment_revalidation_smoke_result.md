# Stage 1 环境复验 smoke 结果

## 文档定位

- 本文档记录主线回退后的 `environment revalidation smoke`。
- 本文档只用于封存这次环境复验检查点。
- 本文档**不是** `Stage 1` 历史结论重写。
- 本文档**不是**新的 baseline 封版。

## 复验背景

- 主线回退锚点：`7fb8ecd61a63e0d019923ccc46ff80b56344b5a2`
- 主验证环境：`WSL Ubuntu-22.04-Fresh`
- Windows 直连环境当前不作为 primary supported path
- 本次 smoke 只用于确认：
  - 环境仍可用
  - `Stage 1` 闭环仍可重新跑通

## 运行摘要

- `run dir`: `outputs/gepa_aime_smoke/20260521T235647+0800`
- `provider`: `deepseek`
- `task_model`: `deepseek-v4-flash`
- `reflection_model`: `deepseek-v4-pro`
- `dataset source`: `gepa.examples.aime.init_dataset()`
- `trainset size`: `45`
- `valset size`: `45`
- `testset size`: `150`
- `max_metric_calls`: `10`
- `total_metric_calls`: `45`
- `best_score`: `0.13333333333333333`
- `num_candidates`: `1`
- `num_full_val_evals`: `1`
- `not_stage1_rewrite = true`
- `not_new_baseline = true`

## 证据来源

- `manifest.json`
  - `git_commit = 7fb8ecd61a63e0d019923ccc46ff80b56344b5a2`
  - `platform = Linux-6.6.114.1-microsoft-standard-WSL2-x86_64-with-glibc2.35`
  - `python_version = 3.10.12`
  - `gepa_version = 0.0.27`
  - `dspy_version = 3.2.1`
  - `litellm_version = 1.84.0`
  - `openai_version = 2.36.0`
- `stdout.log`
  - `AIME 数据来源` 指向当前 `.venv-wsl` 中的官方 `gepa/examples/aime.py`
  - 日志记录 `train=45 val=45 test=150`
  - 日志记录 `Iteration 0: Base program full valset score: 0.13333333333333333 over 45 / 45 examples`
- `stderr.log`
  - 为空

## 结果解释

- 这次 smoke 证明在主线回退后，当前 `WSL Ubuntu-22.04-Fresh` 环境仍能重新执行一次新的 Stage 1 smoke。
- 这次 smoke 没有出现 candidate expansion，`optimized_prompt` 与 `seed_prompt` 相同，因此它只能作为环境复验检查点，不能作为新的性能结论。
- 这次 smoke 不改写 `reports/stage1_final_status.md` 的历史封版结论。

## 下一步

- 按 `reports/stage1_next_phase_revalidation_plan.md` 继续执行：
  1. `scripts/00_check_env.py`
  2. `scripts/01_check_deepseek_models.py --config configs/deepseek_pilot.yaml`
  3. `scripts/03_run_gepa_aime_pilot.py --config configs/deepseek_pilot.yaml`
  4. 若 pilot 成功，再执行 `scripts/05_eval_saved_prompt.py`

## 留痕

- 记录时间：`2026-05-22 00:47:44 +08:00`
