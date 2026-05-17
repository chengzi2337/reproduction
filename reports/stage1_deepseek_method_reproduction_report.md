# Stage 1 DeepSeek Method-Level Reproduction Report

## Temperature Control Note

- Temperature control is `not recorded as explicitly applied in the current GEPA default path`.
- In Stage 1, `temperature_task` and `temperature_reflection` should be treated as recorded configuration fields, not as proven controlled experimental variables, unless GEPA default path applies them internally.
- See `reports/temperature_control_audit.md`.

## Summary

- This project is a `GEPA method-level reproduction with DeepSeek backend`.
- It is `not original same-model reproduction`.
- It is `not final paper-level conclusion`.
- `official_budget` has `not` been run in Stage 1.
- Stage 1 temperature handling follows `方案 A`: `not explicitly controlled`, no rerun required for the current Stage 1 baseline.
- The next planned Stage 1 step is `pilot saved prompt eval`.
- This report only summarizes the two verified Stage 1 runs that already exist in the repository-local `outputs/` directory:
  - smoke: `outputs/gepa_aime_smoke/20260517T152050+0800`
  - pilot: `outputs/gepa_aime_pilot/20260517T155236+0800`

Related reports:

- `reports/official_core_path_comparison.md`
- `reports/temperature_control_audit.md`
- `reports/stage1_final_status.md`

## Verified Environment

- Verified execution environment label: `WSL Ubuntu-22.04-Fresh`
- Artifact platform string: `Linux-6.6.114.1-microsoft-standard-WSL2-x86_64-with-glibc2.35`
- Python version: `3.10.12`
- `gepa`: `0.0.27`
- `dspy`: `3.2.1`
- `litellm`: `1.84.0`
- `openai`: `2.36.0`
- `git_commit`: `not recorded in current run artifact`

## Smoke Run

- Run directory: `outputs/gepa_aime_smoke/20260517T152050+0800`
- `task_model`: `deepseek-v4-flash`
- `reflection_model`: `deepseek-v4-pro`
- `max_metric_calls`: `10`
- `total_metric_calls`: `45`
- `best_score`: `0.2222222222222222`
- `optimized_prompt` generated: `yes`
- Seed prompt equals optimized prompt: `yes`
- `raw_result_path`: `raw_result.json`

### Smoke Prompt Snapshot

- Seed prompt:
  - `You are a helpful assistant. Answer the question. Put your final answer in the format '### <answer>'`
- Optimized prompt:
  - `You are a helpful assistant. Answer the question. Put your final answer in the format '### <answer>'`

## Pilot Run

- Run directory: `outputs/gepa_aime_pilot/20260517T155236+0800`
- `task_model`: `deepseek-v4-flash`
- `reflection_model`: `deepseek-v4-pro`
- `max_metric_calls`: `50`
- `total_metric_calls`: `96`
- `best_score`: `0.8444444444444444`
- `optimized_prompt` generated: `yes`
- Prompt evolution observed: `yes`
- `raw_result_path`: `raw_result.json`

### Pilot Prompt Change Summary

- Seed prompt:
  - `You are a helpful assistant. Answer the question. Put your final answer in the format '### <answer>'`
- Optimized prompt changed the system prompt to:
  - explicitly frame the task as competition math / AIME-style integer-answer solving
  - require the final answer to be an integer between `0` and `999`
  - require the final line format to be exactly `### XXX`
  - require zero-padded three-digit output, such as `### 081`
  - explicitly forbid alternate final-answer formatting such as `\boxed{}`

## Notes and Limitations

- `max_metric_calls` does not guarantee equality with the final `total_metric_calls`; GEPA may perform a full baseline evaluation before later search steps.
- These runs establish a Stage 1 smoke/pilot baseline only.
- They do not establish same-model reproduction of the original GEPA paper.
- They do not establish paper-level evidence across multiple seeds, tasks, or model families.
- Saved prompt evaluation for the pilot run is `not recorded in current run artifact`.
