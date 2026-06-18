# IFEval prompt-transfer canonical smoke summary

## Scope

- limit=20 smoke: `20` samples
- no new API call
- deterministic offline official IFEval checker
- canonical_summary_source: `deterministic_offline_recheck`
- langdetect_seed: `0`
- llm_judge_enabled: `False`

## Variant table

| variant | prompt-level accuracy | instruction-level accuracy | sample count | checker errors |
|---|---:|---:|---:|---:|
| `baseline` | `0.8` | `0.8666666666666667` | `20` | `0` |
| `baseline_mhc` | `0.85` | `0.9` | `20` | `0` |
| `verbose_helpfulness` | `0.85` | `0.9` | `20` | `0` |
| `mhc_concise` | `0.85` | `0.9` | `20` | `0` |
| `ifbench_gepa_prompt_transfer` | `0.85` | `0.9` | `20` | `0` |
| `gepa_p2_transfer` | `0.9` | `0.9333333333333333` | `20` | `0` |

## Pairwise delta table

| pair | improved | degraded | tied | prompt delta | instruction delta |
|---|---:|---:|---:|---:|---:|
| `baseline_mhc - baseline` | `2` | `1` | `17` | `0.04999999999999993` | `0.033333333333333326` |
| `verbose_helpfulness - baseline` | `2` | `1` | `17` | `0.04999999999999993` | `0.033333333333333326` |
| `mhc_concise - baseline_mhc` | `0` | `0` | `20` | `0.0` | `0.0` |
| `gepa_p2_transfer - ifbench_gepa_prompt_transfer` | `1` | `0` | `19` | `0.050000000000000044` | `0.033333333333333326` |

## Main interpretation

- gepa_p2_transfer 相对 ifbench_gepa_prompt_transfer 显示正向 smoke 信号。
- mhc_concise 相对 baseline_mhc 在 canonical deterministic recheck 下没有改善。
- baseline_mhc 相对 baseline 显示正向 smoke 信号。
- verbose_helpfulness 相对 baseline 显示正向 smoke 信号。

## Boundary

- limit=20 smoke 不是 full IFEval 结论。
- full IFEval run 仍然是必要下一步。
- 本 summary 只来自已有 raw_outputs.jsonl 的 deterministic offline official IFEval checker 重算。
