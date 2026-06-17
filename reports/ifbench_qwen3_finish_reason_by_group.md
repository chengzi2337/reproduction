# IFBench/Qwen3 finish_reason 分组审计

本报告只读取 `reports/replay_aggregates/*.json`，不调用模型 API，不修改实验原始数据。

## 汇总表

| aggregate | variant | temperature | repetitions | stop | length | provider rejects | parse failures | length groups |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-paper-adapted-nb-s2-t06-baseline-aggregate.json | baseline | 0.6 | 1 | 576 | 11 | 0 | 1 | custom, format, sentence, words |
| IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-paper-adapted-nocache-deterministic-t0-baseline-aggregate.json | baseline | 0.0 | 3 | 1734 | 30 | 0 | 0 | count, custom, format, words |
| IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-paper-adapted-nocache-exact-t06-baseline-aggregate.json | baseline | 0.6 | 3 | 1746 | 16 | 0 | 2 | custom, format, ratio, sentence, words |
| IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-paper-adapted-nocache-mhc-t0-optimized-aggregate.json | mhc | 0.0 | 1 | 576 | 12 | 0 | 0 | count, custom, format, words |
| IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-paper-adapted-nocache-missing-baseline-seed1-t06-baseline-aggregate.json | baseline | 0.6 | 1 | 579 | 8 | 0 | 1 | custom, format, words |
| IFBench_IFBenchCoT2StageProgram_GEPA_qwen3-8b-dashscope-paper-adapted-nocache-deterministic-t0-optimized-aggregate.json | gepa | 0.0 | 3 | 1704 | 56 | 0 | 4 | count, custom, format, ratio, sentence, words |
| IFBench_IFBenchCoT2StageProgram_GEPA_qwen3-8b-dashscope-paper-adapted-nocache-exact-t06-optimized-aggregate.json | gepa | 0.6 | 3 | 1718 | 44 | 0 | 3 | count, custom, format, sentence, words |
| IFBench_IFBenchCoT2StageProgram_GEPA_qwen3-8b-dashscope-paper-adapted-nocache-p2-t0-optimized-aggregate.json | p2 | 0.0 | 2 | 1147 | 28 | 0 | 2 | custom, format, sentence, words |

## P2 length event audit

- P2 aggregate：`IFBench_IFBenchCoT2StageProgram_GEPA_qwen3-8b-dashscope-paper-adapted-nocache-p2-t0-optimized-aggregate.json`
- length 事件总数：`28`
- length 涉及 group：`{'custom': 6, 'format': 6, 'sentence': 4, 'words': 12}`
- length 最多的 group：`words`，占比 `0.428571`
- 含 length 样本均分：`0.1`，非 length 样本均分：`0.396127`
- 含 length 样本均分差：`-0.296127`
- 解释边界：这些数字只能说明 length 事件在当前 aggregate 中的分布和同批样本得分差异，不能单独证明截断是低分的因果原因。

## 分组明细

### IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-paper-adapted-nb-s2-t06-baseline-aggregate.json

- 状态：`ok`
- finish_reason 捕获状态：`captured`

| group | samples | stop | length | other | length sample average | length sample ids |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| count | 53 | 106 | 0 | 0 | None | - |
| custom | 10 | 17 | 3 | 0 | 0.0 | 281, 283 |
| format | 91 | 179 | 2 | 0 | 0.0 | 108, 112 |
| ratio | 34 | 68 | 0 | 0 | None | - |
| repeat | 9 | 18 | 0 | 0 | None | - |
| sentence | 22 | 42 | 2 | 0 | 0.5 | 189 |
| words | 75 | 146 | 4 | 0 | 0.166667 | 10, 205, 222 |

### IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-paper-adapted-nocache-deterministic-t0-baseline-aggregate.json

- 状态：`ok`
- finish_reason 捕获状态：`captured`

| group | samples | stop | length | other | length sample average | length sample ids |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| count | 53 | 314 | 4 | 0 | 0.0 | 49 |
| custom | 10 | 56 | 4 | 0 | 0.333333 | 281 |
| format | 91 | 531 | 15 | 0 | 0.291667 | 88, 90, 108, 112 |
| ratio | 34 | 204 | 0 | 0 | None | - |
| repeat | 9 | 54 | 0 | 0 | None | - |
| sentence | 22 | 132 | 0 | 0 | None | - |
| words | 75 | 443 | 7 | 0 | 0.166667 | 10, 205, 242, 263 |

### IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-paper-adapted-nocache-exact-t06-baseline-aggregate.json

- 状态：`ok`
- finish_reason 捕获状态：`captured`

| group | samples | stop | length | other | length sample average | length sample ids |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| count | 53 | 318 | 0 | 0 | None | - |
| custom | 10 | 57 | 3 | 0 | 0.0 | 281, 283 |
| format | 91 | 539 | 5 | 0 | 0.0 | 108, 112 |
| ratio | 34 | 203 | 1 | 0 | 0.166667 | 151 |
| repeat | 9 | 54 | 0 | 0 | None | - |
| sentence | 22 | 130 | 2 | 0 | 0.5 | 189 |
| words | 75 | 445 | 5 | 0 | 0.25 | 205, 241 |

### IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-paper-adapted-nocache-mhc-t0-optimized-aggregate.json

- 状态：`ok`
- finish_reason 捕获状态：`captured`

| group | samples | stop | length | other | length sample average | length sample ids |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| count | 53 | 104 | 2 | 0 | 0.0 | 49 |
| custom | 10 | 19 | 1 | 0 | 0.0 | 281 |
| format | 91 | 178 | 4 | 0 | 0.0 | 108, 112 |
| ratio | 34 | 68 | 0 | 0 | None | - |
| repeat | 9 | 18 | 0 | 0 | None | - |
| sentence | 22 | 44 | 0 | 0 | None | - |
| words | 75 | 145 | 5 | 0 | 0.166667 | 13, 205, 230 |

### IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-paper-adapted-nocache-missing-baseline-seed1-t06-baseline-aggregate.json

- 状态：`ok`
- finish_reason 捕获状态：`captured`

| group | samples | stop | length | other | length sample average | length sample ids |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| count | 53 | 106 | 0 | 0 | None | - |
| custom | 10 | 18 | 2 | 0 | 0.0 | 281 |
| format | 91 | 179 | 2 | 0 | 0.0 | 108, 112 |
| ratio | 34 | 68 | 0 | 0 | None | - |
| repeat | 9 | 18 | 0 | 0 | None | - |
| sentence | 22 | 44 | 0 | 0 | None | - |
| words | 75 | 146 | 4 | 0 | 0.0 | 200, 220 |

### IFBench_IFBenchCoT2StageProgram_GEPA_qwen3-8b-dashscope-paper-adapted-nocache-deterministic-t0-optimized-aggregate.json

- 状态：`ok`
- finish_reason 捕获状态：`captured`

| group | samples | stop | length | other | length sample average | length sample ids |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| count | 53 | 313 | 5 | 0 | 0.0 | 49 |
| custom | 10 | 48 | 12 | 0 | 0.0 | 277, 281, 283 |
| format | 91 | 531 | 15 | 0 | 0.708333 | 76, 88, 110, 112 |
| ratio | 34 | 202 | 2 | 0 | 0.0 | 151 |
| repeat | 9 | 54 | 0 | 0 | None | - |
| sentence | 22 | 128 | 4 | 0 | 0.166667 | 181, 196 |
| words | 75 | 428 | 18 | 0 | 0.0 | 13, 205, 219, 220, 243, 246 |

### IFBench_IFBenchCoT2StageProgram_GEPA_qwen3-8b-dashscope-paper-adapted-nocache-exact-t06-optimized-aggregate.json

- 状态：`ok`
- finish_reason 捕获状态：`captured`

| group | samples | stop | length | other | length sample average | length sample ids |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| count | 53 | 316 | 2 | 0 | 0.0 | 49 |
| custom | 10 | 50 | 10 | 0 | 0.111111 | 277, 281, 283 |
| format | 91 | 536 | 10 | 0 | 0.7 | 76, 88, 91, 106, 112 |
| ratio | 34 | 204 | 0 | 0 | None | - |
| repeat | 9 | 54 | 0 | 0 | None | - |
| sentence | 22 | 130 | 2 | 0 | 0.0 | 192 |
| words | 75 | 428 | 20 | 0 | 0.166667 | 12, 13, 200, 219, 220, 221 |

### IFBench_IFBenchCoT2StageProgram_GEPA_qwen3-8b-dashscope-paper-adapted-nocache-p2-t0-optimized-aggregate.json

- 状态：`ok`
- finish_reason 捕获状态：`captured`

| group | samples | stop | length | other | length sample average | length sample ids |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| count | 53 | 212 | 0 | 0 | None | - |
| custom | 10 | 34 | 6 | 0 | 0.0 | 277, 281 |
| format | 91 | 358 | 6 | 0 | 0.5 | 88, 112 |
| ratio | 34 | 136 | 0 | 0 | None | - |
| repeat | 9 | 36 | 0 | 0 | None | - |
| sentence | 22 | 84 | 4 | 0 | 0.0 | 191, 192 |
| words | 75 | 287 | 12 | 0 | 0.0 | 13, 205, 219, 223 |
