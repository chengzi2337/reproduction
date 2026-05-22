# Stage 1 环境复验 fresh pilot 结果

## 文档定位

- 本文档记录主线回退后的 `fresh pilot revalidation` 结果。
- 本文档用于封存这次 `pilot + saved prompt eval` 检查点。
- 本文档**不是** `Stage 1` 历史结果重写。
- 本文档**不是** `official_budget` 结果。
- 本文档**不是** `same-model reproduction`。

## 执行环境

- 主验证环境：`WSL Ubuntu-22.04-Fresh`
- 虚拟环境：`.venv-wsl`
- `git_commit`: `7fb8ecd61a63e0d019923ccc46ff80b56344b5a2`
- `provider`: `deepseek`
- `task_model`: `deepseek-v4-flash`
- `reflection_model`: `deepseek-v4-pro`
- `benchmark`: `aime`
- `seed`: `42`

## fresh pilot 摘要

- `run dir`: `outputs/gepa_aime_pilot/20260522T005441+0800`
- `max_metric_calls`: `50`
- `total_metric_calls`: `96`
- `best_score`: `0.8444444444444444`
- `num_candidates`: `2`
- `num_full_val_evals`: `2`
- `optimized_prompt != seed_prompt`: `true`

## prompt evolution 证据

- `Iteration 0` 的 baseline full valset score 为 `0.13333333333333333`
- `Iteration 1` 产生了新的 `system_prompt`
- 新候选在 valset 上达到 `0.8444444444444444`
- `best_idx` 从 baseline `0` 更新为新候选 `1`

因此，本次 fresh pilot 明确出现了：

- candidate expansion
- prompt evolution
- 非 baseline-only 的迭代迹象

## saved prompt eval 摘要

- 评估脚本：`scripts/05_eval_saved_prompt.py`
- 评估目标 run dir：`outputs/gepa_aime_pilot/20260522T005441+0800`
- 最终评估摘要文件：`outputs/gepa_aime_pilot/20260522T005441+0800/saved_prompt_eval_summary.json`
- `saved prompt eval` 是否完成：`true`
- `split`: `test split`
- `eval_model`: `deepseek-v4-flash`
- `eval_timestamp`: `20260522T030603+0800`
- `seed prompt eval score`: `0.20666666666666667`
- `optimized prompt eval score`: `0.6533333333333333`
- `score_delta`: `0.44666666666666666`
- `seed num_errors`: `0`
- `optimized num_errors`: `0`
- `valid_for_performance_claim`: `true`

## 关于评估续跑的说明

- 首次 `saved prompt eval` 在执行层面因超时窗口耗尽而中断，未生成最终 summary 文件。
- run dir 中已保留 `per_example_eval.jsonl` 中间结果，可用于断点续跑。
- 随后使用 `--resume` 继续完成评估，并生成最终 `saved_prompt_eval_summary.json`。
- `notes.md` 中同时保留了首次未完成尝试的中间摘要与后续 `resume` 完成后的最终摘要。
- 本次归档以 `saved_prompt_eval_summary.json` 作为权威结果来源。

## 成功标准核对

1. `scripts/00_check_env.py`：通过
2. `scripts/01_check_deepseek_models.py --config configs/deepseek_pilot.yaml`：通过
3. fresh pilot 成功执行并生成 `gepa_result_summary.json`：通过
4. `total_metric_calls > 45`：通过，实际为 `96`
5. 存在 candidate expansion 或 prompt evolution 的明确迹象：通过
6. `saved prompt eval` 成功完成：通过

## 结论

- 本次结果足以确认：当前干净主线与主验证环境下，`Stage 1` 的 `smoke -> pilot -> saved prompt eval` 链路可以重新跑通。
- 本次结果应被解释为 `environment revalidation checkpoint`。
- 本次结果**不**改写 `reports/stage1_final_status.md` 的历史封版结论。
- 本次结果**不**把项目提升为 `same-model reproduction`。
- 本次结果**不**等于 `official_budget`。

## 固定声明

- `not_stage1_rewrite = true`
- `not_same_model_reproduction = true`
- `not_official_budget = true`

## 留痕

- 记录时间：`2026-05-22 03:45:31 +08:00`
