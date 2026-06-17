# IFBench/Qwen3 full-budget GEPA 多 seed 审计

## 状态

- 路线：`DashScope/Qwen3 paper-adapted cloud-low-concurrency`
- 复现边界：这不是 strict Arbor/local Qwen reproduction。
- requested seeds：`[0, 1, 2]`
- 已完成 seed：`3/3`
- 全部 requested seeds 完成：`true`
- 完成 seed 分数：`[35.88, 35.37, 36.22]`
- 分数均值：`35.82333333333333`
- 分数总体标准差：`0.34931679350157613`
- 分数范围：`35.37` 到 `36.22`

## Seed 明细

| seed | status | protocol | budget | optimizer evals | overshoot | candidates | traces | train rows | val rows | test rows | score | metric sum | parse failures | provider rejects | score consistent |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 0 | complete | true | 3593 | 3852 | 259 | 12 | 62 | 309 | 3572 | 294 | 35.88 | 105.5 | 1 | 10 | true |
| 1 | complete | true | 3593 | 3828 | 235 | 12 | 52 | 274 | 3758 | 294 | 35.37 | 104.0 | 1 | 4 | true |
| 2 | complete | true | 3593 | 3654 | 61 | 11 | 95 | 458 | 3272 | 294 | 36.22 | 106.5 | 0 | 4 | true |

## Group Score

| seed | count | custom | format | ratio | repeat | sentence | words |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 40.566038 | 0.0 | 69.230769 | 16.176471 | 0.0 | 20.454545 | 14.666667 |
| 1 | 49.056604 | 10.0 | 59.89011 | 19.117647 | 0.0 | 25.0 | 14.0 |
| 2 | 46.226415 | 20.0 | 60.989011 | 11.764706 | 0.0 | 36.363636 | 16.666667 |

## Prompt Bias 命中

| seed | repeat_request_first | long_or_structured_answer | hard_constraint_priority |
| ---: | --- | --- | --- |
| 0 | true | true | false |
| 1 | true | false | false |
| 2 | true | false | false |

## 判定门禁

- seed 只有在配置满足 Qwen3/DashScope/temperature=0.6/top_p=0.95/num_threads=1、`evaluation_result.txt` 存在、test 为 294/294、索引完整唯一、分数一致且 budget=3593 时才标记为 complete。
- `optimizer evals` 来自 `gepa_state.bin` checkpoint。GEPA 在每轮开始前检查 budget，整批 full-val evaluation 可能导致最终调用数超过 3593，因此记录 `overshoot` 而不是把它视作协议失败。
- seed1/seed2 的 Baseline backfill 曾存在 cache caveat，不能作为完全独立 no-cache API replay 证据。本报告只汇总 full-budget GEPA，不把 cached baseline backfill 与 no-cache replay 混为一类。
- 当前三 seed GEPA 均值低于后续 no-cache Baseline 三 seed均值，不能支持“DashScope/Qwen3 cloud-adapted 条件下 GEPA 稳定优于 Baseline”的结论。
