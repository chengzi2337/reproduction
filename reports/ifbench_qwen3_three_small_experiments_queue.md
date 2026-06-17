# IFBench/Qwen3 三个小实验补跑队列

## 当前状态

- 路线：`DashScope/Qwen3 paper-adapted cloud-low-concurrency`
- seed1 GEPA full-budget：已补齐审计缺口，`test.jsonl=294/294`，score 仍为 `35.37`
- seed2：暂不启动，状态为 `not_started`
- 当前阻塞：本 shell 未设置 `QWEN_API_KEY`；为避免密钥进入命令历史、进程命令行或文件，暂不在工具调用中明文注入

## 小实验 1：no-cache exact replay

目的：复核 `temperature=0.6, top_p=0.95` 下的 Baseline vs GEPA，不使用 DSPy 缓存。

- Baseline source：`.codex/gepa-artifact/experiment_runs_data/experiment_runs/seed_0/IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-paper-adapted`
- GEPA source：`.codex/gepa-artifact/experiment_runs_data/experiment_runs/seed_0/IFBench_IFBenchCoT2StageProgram_GEPA_qwen3-8b-dashscope-paper-adapted`
- replay repetitions：`3`
- replay tag：`nocache-exact-t06`
- 必须参数：`--disable-dspy-cache --temperature 0.6 --top-p 0.95 --num-threads 1`

## 小实验 2：no-cache deterministic replay

目的：复核 `temperature=0, top_p=0.95` 下采样随机性是否解释 GEPA 退化。

- Baseline source：同小实验 1
- GEPA source：同小实验 1
- replay repetitions：`1`
- replay tag：`nocache-deterministic-t0`
- 必须参数：`--disable-dspy-cache --temperature 0 --top-p 0.95 --num-threads 1`

## 小实验 3：no-cache hard-constraint 机制复核

目的：复核约束优先级 prompt 是否真实改善，而不是缓存造成的假稳定。

- GEPA + P2 program：`.codex/gepa-artifact/experiment_runs_data/prompt_surgery_variants/ifbench_qwen3_gepa_prompt_surgery_P2`
- Baseline + MHC program：`.codex/gepa-artifact/experiment_runs_data/manual_prompt_variants/ifbench_qwen3_baseline_manual_hard_constraint_MHC`
- replay repetitions：P2 建议 `2`，MHC 建议 `1`
- replay tag：`nocache-constraint-priority-t0`
- 必须参数：`--disable-dspy-cache --temperature 0 --top-p 0.95 --num-threads 1`

## 执行门禁

- 不与 seed2 并行运行，避免 API 限流和云端行为混杂。
- 所有 replay 使用 `--request-timeout-seconds 600`、`--process-timeout-seconds 28800`、`--num-retries 2`。
- 小实验完成后，重新运行 replay analyzer 生成 sample-level matrix 与 group score。
- 总队列入口：`scripts/start_ifbench_qwen3_nocache_research_queue.ps1`。
- exact 审计若不是 `gepa_stably_below_baseline`，队列状态写为 `paused_after_exact`，不会运行后续实验或 seed2。
- exact 负结果确认后，依次运行 deterministic、温度效应审计、P2/MHC 机制实验。
- 三个小实验全部完成后，默认通过既有 seed2 接力器启动 full-budget seed2；传入 `-SkipSeed2` 可显式暂停。
- seed2 仍复用 `paper-adapted + cloud-low-concurrency + GEPA + budget=3593`，不改变实验协议。

## 自动审计产物

- exact：`reports/ifbench_qwen3_nocache_exact_replay_audit.json/.md`
- deterministic：`reports/ifbench_qwen3_nocache_deterministic_replay_audit.json/.md`
- 温度效应：`reports/ifbench_qwen3_nocache_temperature_effect.json/.md`
- P2/MHC：`reports/ifbench_qwen3_nocache_constraint_priority_audit.json/.md`
- 总队列状态：`reports/ifbench_qwen3_nocache_research_queue_status.json`
