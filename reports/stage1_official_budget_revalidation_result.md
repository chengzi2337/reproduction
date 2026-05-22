# official_budget 阶段结果

## 文档定位

- 本文档记录 `official_budget` 作为 `Stage 1` 之后下一阶段实验的运行结果。
- 本文档建立在已完成的 environment revalidation 之上。
- 本文档**不是** `Stage 1` 历史结论重写。
- 本文档**不是** `same-model reproduction` 声明。

## 执行环境

- 主验证环境：`WSL Ubuntu-22.04-Fresh`
- 虚拟环境：`.venv-wsl`
- `git_commit`: `7fb8ecd61a63e0d019923ccc46ff80b56344b5a2`
- `provider`: `deepseek`
- `task_model`: `deepseek-v4-flash`
- `reflection_model`: `deepseek-v4-pro`
- `max_metric_calls`: `150`
- `seed`: `42`

## official_budget 主运行摘要

- `run dir`: `outputs/gepa_aime_official_budget/20260522T071703+0800`
- `best_idx`: `2`
- `best_score`: `0.9111111111111111`
- `total_metric_calls`: `162`
- `num_candidates`: `3`
- `num_full_val_evals`: `3`
- `optimized_prompt != seed_prompt`: `true`

## prompt evolution 摘要

- baseline `Iteration 0` 的 full valset score：`0.2`
- `Iteration 1` 首次生成改进后的格式约束型 prompt，valset score 提升到 `0.8666666666666667`
- `Iteration 6` 再次生成更细化的格式与推理要求 prompt，valset score 进一步提升到 `0.9111111111111111`

说明：

- 本次 `official_budget` 并非停留在 baseline-only
- 明确出现了多轮 reflective mutation
- 候选池最终扩展到 `3` 个候选

## saved prompt eval 摘要

- 评估脚本：`scripts/05_eval_saved_prompt.py`
- 最终摘要文件：`outputs/gepa_aime_official_budget/20260522T071703+0800/saved_prompt_eval_summary.json`
- `split`: `test split`
- `eval_model`: `deepseek-v4-flash`
- `eval_timestamp`: `20260522T103658+0800`
- `seed_prompt_score`: `0.18666666666666668`
- `optimized_prompt_score`: `0.6466666666666666`
- `score_delta`: `0.45999999999999996`
- `seed num_errors`: `0`
- `optimized num_errors`: `0`
- `valid_for_performance_claim`: `true`

## 关于 saved prompt eval 续跑的说明

- 首次执行 `saved prompt eval` 时，命令层面因长时间运行触发超时，未生成最终 summary 文件。
- 运行目录中已保留 `per_example_eval.jsonl` 中间结果。
- 随后使用 `--resume` 成功补完剩余评估。
- `notes.md` 同时保留了首次未完成尝试的中间摘要与 `resume` 后的最终摘要。
- 本次归档以 `saved_prompt_eval_summary.json` 作为权威结果来源。

## 结果解释

- 在当前干净主线、当前 `WSL Ubuntu-22.04-Fresh`、当前 DeepSeek 配置下，`official_budget` 已成功跑通。
- 从 valset 最优分数看，`official_budget` 的 `best_score = 0.9111111111111111` 高于 fresh pilot 的 `0.8444444444444444`。
- 从 saved prompt eval 看，优化后 prompt 在 `test split` 上显著优于 seed prompt：
  - `0.6466666666666666` vs `0.18666666666666668`
  - `score_delta = 0.45999999999999996`

## 结论边界

- 当前结果可以支持：
  - `GEPA method-level reproduction with DeepSeek backend` 在 `official_budget` 阶段成功执行
  - 优化 prompt 相比 seed prompt 在本次 `test split` 评估中表现更好
- 当前结果不能支持：
  - `same-model reproduction`
  - 原论文最终结论已被完全复现
  - 多 seed / 多 benchmark / 多后端的论文级稳定性结论

## 建议的后续顺序

1. 先把本次 revalidation 与 `official_budget` 结果整理成可提交文档变更
2. 保持 `reports/stage1_final_status.md` 不改主体结论
3. 如果要继续扩展，只建议进入：
   - 多 seed
   - 多 benchmark
   - 多后端对比

## 固定声明

- `not_stage1_rewrite = true`
- `not_same_model_reproduction = true`
- `official_budget_completed = true`

## 留痕

- 记录时间：`2026-05-22 10:47:58 +08:00`
