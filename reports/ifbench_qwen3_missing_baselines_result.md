# IFBench Qwen3 缺失 Baseline 补齐结果

生成时间：2026-06-17 09:23:08 +08:00

## 结论

seed1 与 seed2 的 Baseline 已补齐到 `294/294`，没有缺失索引和重复索引。两条 run 都存在 `evaluation_results/evaluation_result.txt`，并且 metric sum 与 score 一致。

但这次补跑脚本未启用 `--disable-dspy-cache`。seed2 日志在开头出现每秒几十到几百条的评测速度，说明大量复用了 DSPy 缓存。因此，这两条结果只适合用于“同一缓存口径下补齐 seed1/seed2 GEPA 对照”，不适合表述为“两个完全独立的云 API 随机重复 Baseline”。

后续已经补跑 no-cache Baseline，正式研究判断应优先采用 `reports/ifbench_qwen3_missing_baseline_nocache_result.md`。

## 补齐明细

| seed | optimizer | rows | missing | duplicate | metric sum | score | backfill |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| 0 | Baseline | 294 | `[]` | 0 | 107.5 | 36.564626 | 1 |
| 0 | GEPA | 294 | `[]` | 0 | 105.5 | 35.884354 | 1 |
| 1 | Baseline | 294 | `[]` | 0 | 101.5 | 34.523810 | 1 |
| 1 | GEPA | 294 | `[]` | 0 | 104.0 | 35.374150 | 1 |
| 2 | Baseline | 294 | `[]` | 0 | 101.5 | 34.523810 | 1 |
| 2 | GEPA | 294 | `[]` | 0 | 106.5 | 36.224490 | 0 |

## GEPA 对 Baseline

| seed | Baseline | GEPA | delta |
| --- | ---: | ---: | ---: |
| 0 | 36.564626 | 35.884354 | -0.680272 |
| 1 | 34.523810 | 35.374150 | +0.850340 |
| 2 | 34.523810 | 36.224490 | +1.700680 |

三组均值口径：

| optimizer | mean |
| --- | ---: |
| Baseline | 35.204082 |
| GEPA | 35.827664 |
| delta | +0.623583 |

## 解释边界

- 对“复现论文 Qwen/IFBench 强提升”而言，结果仍不理想：当前平均提升约 `+0.62`，低于论文图中约 `+1.7` 的读数，且绝对 GEPA 分数仍在 `35.37-36.22` 区间，没有达到论文约 `38.6`。
- 对“研究问题发现”而言，结果有价值：seed0 负向、seed1/seed2 正向，说明 GEPA 收益不稳定；hard-constraint P2/MHC 实验已显示约束优先级改写能显著提高双方分数，这是更强的改良线索。
- 对“独立重复证据”而言，本次补齐 Baseline 仍不足：seed1/seed2 Baseline 使用了缓存口径，不能替代 no-cache Baseline 重复实验。

## 后续建议

如果目标是提交论文级证据，下一步应补跑 `--disable-dspy-cache` 的 seed1/seed2 Baseline，或明确把当前 seed1/seed2 Baseline 降级为缓存口径辅助对照。当前更强的主证据仍应来自 no-cache exact replay、deterministic replay 和 hard-constraint P2/MHC。
