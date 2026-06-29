# IFBench stratified evidence replay selection

??????? evidence replay ????????

- baseline aggregate: `IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-paper-adapted-nocache-exact-t06-baseline-aggregate.json`
- GEPA aggregate: `IFBench_IFBenchCoT2StageProgram_GEPA_qwen3-8b-dashscope-paper-adapted-nocache-exact-t06-optimized-aggregate.json`
- test_indices: `75,83,90,108,274,271,175,176,156,20,8,21`

| idx | key | stratum | group | instruction ids | baseline | GEPA | delta |
|---:|---:|---|---|---|---:|---:|---:|
| 75 | 75 | format_improved | format | `['format:line_indent']` | 0.0 | 1.0 | 1.0 |
| 83 | 83 | format_improved | format | `['format:list']` | 0.0 | 1.0 | 1.0 |
| 90 | 90 | format_improved | format | `['format:newline']` | 0.0 | 1.0 | 1.0 |
| 108 | 108 | format_improved | format | `['format:parentheses']` | 0.0 | 1.0 | 1.0 |
| 274 | 280 | custom_degraded | custom | `['custom:multiples']` | 1.0 | 0.0 | -1.0 |
| 271 | 277 | custom_degraded | custom | `['custom:date_format_list']` | 1.0 | 0.3333333333333333 | -0.6666666666666667 |
| 175 | 175 | ratio_degraded | ratio | `['ratio:stop_words']` | 1.0 | 0.0 | -1.0 |
| 176 | 176 | ratio_degraded | ratio | `['ratio:stop_words']` | 1.0 | 0.3333333333333333 | -0.6666666666666667 |
| 156 | 156 | ratio_degraded | ratio | `['ratio:sentence_balance']` | 0.6666666666666666 | 0.0 | -0.6666666666666666 |
| 20 | 20 | count_degraded | count | `['count:numbers']` | 1.0 | 0.0 | -1.0 |
| 8 | 8 | count_degraded | count | `['count:conjunctions']` | 1.0 | 0.3333333333333333 | -0.6666666666666667 |
| 21 | 21 | count_degraded | count | `['count:numbers']` | 0.6666666666666666 | 0.0 | -0.6666666666666666 |