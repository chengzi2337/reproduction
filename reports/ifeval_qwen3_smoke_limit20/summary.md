# IFEval prompt-transfer limit=20 smoke test

## 边界

- 这是 `limit=20 smoke test`，不是全量 IFEval 实验。
- 这是 prompt-transfer，不是 GEPA optimization。
- 结果只能作为链路验证和初步信号，不能作为论文主结论。
- 使用 official IFEval rule checker，不使用 LLM judge。
- 如果 MHC/P2 有提升，只能写 preliminary signal，不能写 proved。
- 如果结果不稳定或不提升，不改 prompt、不删样本，原样报告。

## 总览

- status：`completed`
- limit：`20`
- variant_count：`6`
- model_calls_planned：`120`
- model_calls_completed：`120`
- prompt_level_accuracy：`0.825`
- instruction_level_accuracy：`0.8833333333333333`
- provider_error_count：`0`
- provider_rejection_count：`0`
- timeout_count：`0`

## Per-variant

| variant | prompt_level_accuracy | instruction_level_accuracy |
|---|---:|---:|
| `baseline` | `0.8` | `0.8666666666666667` |
| `baseline_mhc` | `0.85` | `0.9` |
| `verbose_helpfulness` | `0.8` | `0.8666666666666667` |
| `mhc_concise` | `0.8` | `0.8666666666666667` |
| `ifbench_gepa_prompt_transfer` | `0.8` | `0.8666666666666667` |
| `gepa_p2_transfer` | `0.9` | `0.9333333333333333` |

## Pairwise delta

| pair | prompt delta | instruction delta |
|---|---:|---:|
| `baseline_mhc - baseline` | `0.04999999999999993` | `0.033333333333333326` |
| `verbose_helpfulness - baseline` | `0.0` | `0.0` |
| `mhc_concise - baseline_mhc` | `-0.04999999999999993` | `-0.033333333333333326` |
| `gepa_p2_transfer - ifbench_gepa_prompt_transfer` | `0.09999999999999998` | `0.06666666666666665` |
