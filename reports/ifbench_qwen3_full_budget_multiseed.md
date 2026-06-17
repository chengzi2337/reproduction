# IFBench/Qwen3 full-budget GEPA 多 seed 审计

## 状态

- 已完成 seed：`2/3`
- 全部完成：`False`
- 完成 seed 分数：`[35.88, 35.37]`
- 分数均值：`35.625`
- 分数总体标准差：`0.25500000000000256`

## Seed 明细

| seed | status | protocol | budget | optimizer evals | progress | overshoot | candidates | train rows | val rows | test rows | score | parse failures | provider rejects | hard API errors |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | complete | True | 3593 | 3852 | 100.0% | 259 | 12 | 309 | 3572 | 294 | 35.88 | 1 | 10 | 0 |
| 1 | complete | True | 3593 | 3828 | 100.0% | 235 | 12 | 274 | 3758 | 294 | 35.37 | 1 | 4 | 0 |
| 2 | not_started | False | None | None | None | None | 0 | 0 | 0 | 0 | None | None | 0 | 0 |

## Prompt Bias

- `repeat_request_first`：完成 seed 中全部命中=`True`
- `long_or_structured_answer`：完成 seed 中全部命中=`False`
- `hard_constraint_priority`：完成 seed 中全部命中=`False`

## 判定门禁

- 只有配置满足 Qwen3/DashScope/temperature=0.6/top_p=0.95/num_threads=1、`evaluation_result.txt` 存在、test 为 294/294、索引完整唯一、分数一致且 budget=3593，seed 才标记为 complete。
- 未完成 seed 的 train/val 行数只用于进度观察，不用于计算最终均值或研究结论。
- 本报告属于 DashScope/Qwen3 paper-adapted 路线，不是 strict Arbor 论文复现。
- `optimizer evals` 来自 `gepa_state.bin` checkpoint；GEPA 在每轮开始前检查 budget，整批 full-val evaluation 可导致最终调用数超过 3593，超出量记为 overshoot。
