# IFBench Qwen3 exact replay 稳定性对比报告

## 总览

- 路线：`DashScope/Qwen3 paper-adapted cloud-low-concurrency`
- replay 参数：`temperature=0.6`，`top_p=0.95`
- Baseline replay：3 次，均为 `294/294`
- GEPA optimized replay：3 次，均为 `294/294`
- Baseline exact replay score：`36.56`
- GEPA exact replay score：`34.013605`
- GEPA - Baseline：`-2.546395`
- GEPA 退化 / 改善 / 持平：`46 / 36 / 212`
- finish_reason 捕获状态：`not_captured_by_current_runner`

## Group Score

| group | count | baseline | gepa | delta |
| --- | ---: | ---: | ---: | ---: |
| count | 53 | 48.113208 | 37.735849 | -10.377358 |
| custom | 10 | 30.0 | 10.0 | -20.0 |
| format | 91 | 60.989011 | 65.384615 | 4.395604 |
| ratio | 34 | 22.058824 | 20.588235 | -1.470588 |
| repeat | 9 | 0.0 | 0.0 | 0.0 |
| sentence | 22 | 29.545455 | 13.636364 | -15.909091 |
| words | 75 | 12.666667 | 12.666667 | 0.0 |

## 产物位置

- Baseline aggregate：`.codex/gepa-artifact/experiment_runs_data/experiment_runs/seed_0/IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-paper-adapted-exact-t06-baseline-aggregate.json`
- GEPA aggregate：`.codex/gepa-artifact/experiment_runs_data/experiment_runs/seed_0/IFBench_IFBenchCoT2StageProgram_GEPA_qwen3-8b-dashscope-paper-adapted-exact-t06-optimized-aggregate.json`
- sample-level score matrix：上述两个 aggregate 文件的 `sample_level_score_matrix`

## 初步判断

Exact replay 后，GEPA 仍明显低于 Baseline，而且退化集中在 `count`、`custom`、`sentence` 这类 hard-constraint group；`format` group 有改善。这个结果强化了先前假设：GEPA final prompt 可能学到通用解释/结构化偏置，对部分格式任务有利，但损害精确计数、定制规则和句子链式约束。

该结果仍不是 strict Arbor 论文复现，只能作为 DashScope 云 API 迁移条件下的稳定性证据。
