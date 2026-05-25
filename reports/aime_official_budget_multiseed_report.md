# AIME official_budget 3-seed 稳定性报告

## 文档定位

- 本文档汇总 `AIME official_budget` 在 `DeepSeek` 后端下的 `3-seed` 结果。
- 本文档关注的问题是：`optimized prompt` 是否在多 seed 下稳定优于 `seed prompt`。
- 本文档不是 `Stage 1` 历史结论改写。
- 本文档不是 `same-model reproduction` 声明。
- 本文档不是论文级稳定性结论。

## 固定实验边界

- `benchmark`: `aime`
- `provider`: `deepseek`
- `task_model`: `deepseek-v4-flash`
- `reflection_model`: `deepseek-v4-pro`
- `max_metric_calls`: `150`
- `dataset source`: `gepa.examples.aime.init_dataset()`
- `eval split`: `test split`
- `eval model`: `deepseek-v4-flash`
- `temperature_explicitly_controlled`: `false`
- `not_same_model_reproduction = true`
- `single_benchmark_only = true`
- `single_backend_only = true`

## 运行清单

- `seed0`
  - `run_dir`: `outputs/gepa_aime_official_budget_seed0/20260522T121001+0800`
- `seed1`
  - `run_dir`: `outputs/gepa_aime_official_budget_seed1/20260522T175103+0800`
- `seed2`
  - `run_dir`: `outputs/gepa_aime_official_budget_seed2/20260522T221654+0800`

## 主结果表

| seed | run_dir | total_metric_calls | num_candidates | num_full_val_evals | best_val_score | seed_test_score | optimized_test_score | score_delta | seed_num_errors | optimized_num_errors | valid_for_performance_claim |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | `outputs/gepa_aime_official_budget_seed0/20260522T121001+0800` | 150 | 3 | 3 | 0.8444444444444444 | 0.2 | 0.6333333333333333 | 0.4333333333333333 | 0 | 0 | `true` |
| 1 | `outputs/gepa_aime_official_budget_seed1/20260522T175103+0800` | 162 | 3 | 3 | 0.9111111111111111 | 0.16666666666666666 | 0.6666666666666666 | 0.5 | 0 | 0 | `true` |
| 2 | `outputs/gepa_aime_official_budget_seed2/20260522T221654+0800` | 150 | 3 | 3 | 0.6888888888888889 | 0.22666666666666666 | 0.9266666666666666 | 0.7 | 0 | 0 | `true` |

## Prompt 长度表

说明：
- 这里先用 `system_prompt` 字符数作为长度近似指标。
- `token_est` 仅用 `chars / 4` 做粗略估算，不作为严格成本结论。

| seed | seed_prompt_chars | optimized_prompt_chars | prompt_char_growth | seed_prompt_tokens_est | optimized_prompt_tokens_est | token_growth_est |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 100 | 2917 | 2817 | 25 | 729 | 704 |
| 1 | 100 | 1144 | 1044 | 25 | 286 | 261 |
| 2 | 100 | 940 | 840 | 25 | 235 | 210 |

## 聚合统计

- `optimized > seed` 的 seed 数：`3 / 3`
- `mean_seed_score = 0.19777777777777775`
- `mean_optimized_score = 0.7422222222222222`
- `mean_delta = 0.5444444444444444`
- `min_delta = 0.4333333333333333`
- `max_delta = 0.7`
- `delta_range = 0.26666666666666666`
- `optimized_score_range = 0.29333333333333333`
- `best_val_score_range = 0.2222222222222222`
- `mean_prompt_growth_chars = 1567.0`
- `min_prompt_growth_chars = 840`
- `max_prompt_growth_chars = 2817`

## 结果判断

### 方向性稳定性

从最基本的问题看，这组结果支持一个明确结论：

> 在当前 `AIME + DeepSeek + official_budget` 设定下，`optimized prompt` 在 `3 / 3` 个 seed 上都优于 `seed prompt`。

这意味着：

- `GEPA` 的 prompt evolution 并不是只在单个 seed 上偶然成立。
- 当前链路至少具备了**初步多 seed 稳定性**。
- 结果已经超过“只有单次 official_budget 跑通”的证据强度。

### 波动性判断

这组结果同时也说明，当前稳定性还不够强，原因有三点：

1. `optimized_test_score` 的范围较大：`0.6333333333333333 -> 0.9266666666666666`
2. `score_delta` 的范围较大：`0.4333333333333333 -> 0.7`
3. `best_val_score` 与 `optimized_test_score` 之间不是严格单调对应：
   - `seed1` 的 `best_val_score` 最高，为 `0.9111111111111111`
   - 但 `seed2` 的 `optimized_test_score` 最高，为 `0.9266666666666666`

因此，更准确的判断不是“已经非常稳定”，而是：

> 当前结果支持“初步稳定、但波动仍然明显”的结论。

换句话说，它已经足够支持继续做下一阶段研究，但还不足以直接写成“强稳定的论文级多 seed 结论”。

### 长度与性能关系

三个 seed 的 `optimized prompt` 都显著长于 `seed prompt`，但长度增长与测试分数并不单调对应：

- `seed0` 的 prompt 增长最大：`+2817 chars`
- `seed2` 的 prompt 增长最小：`+840 chars`
- 但 `seed2` 的 `optimized_test_score` 反而最高：`0.9266666666666666`

这说明：

- 当前 `GEPA` 的收益不能简单解释为“prompt 越长越好”
- prompt length / token cost 已经成为值得单独研究的变量
- `Length-Controlled GEPA` 仍然是很自然的下一步切口

## 关于 seed2 恢复的说明

- `seed2` 的 `official_budget` optimize 阶段是完成的。
- 它第一次 `saved prompt eval` 失败时，出现了：
  - `AttributeError after 4 attempts: 'BadRequestError' object has no attribute 'choices'`
- 随后确认 `DeepSeek` 账户余额此前不足，充值后在原 `run_dir` 上使用 `--resume --retry-failed` 完成恢复。
- 最终权威结果以恢复后的 `saved_prompt_eval_summary.json` 为准：
  - `seed_prompt_score = 0.22666666666666666`
  - `optimized_prompt_score = 0.9266666666666666`
  - `valid_for_performance_claim = true`

因此，`seed2` 应视为**恢复完成后的有效结果**，而不是失败样本。

## 结论

本轮 `3-seed` 汇总可以支持如下表述：

> `AIME official_budget` 在 `DeepSeek` 后端下，已经表现出初步多 seed 稳定性：`3 / 3` 个 seed 上，`optimized prompt` 都优于 `seed prompt`。

但本轮还不能支持如下表述：

- “已经得到强稳定的论文级多 seed 结论”
- “已经完成 same-model reproduction”
- “更大 budget 一定带来更高 test performance”
- “prompt 越长越好”

## 建议

当前最合理的下一步有两种解释路径：

1. 如果你想先把 baseline 证据做得更硬：
   - 先补到 `5-seed`
   - 再决定是否扩 benchmark

2. 如果你想开始进入小创新：
   - `Length-Controlled GEPA` 是最自然的下一步
   - 因为当前已经同时观察到了：
     - `3/3` 的稳定正向提升
     - prompt 长度显著膨胀
     - 长度增长与 test performance 不单调对应

综合判断：

> 当前 baseline 已经不再是“只能跑通一次”的状态，而是“有初步稳定性、但仍有明显波动”的状态。

这足以支持继续研究，但最好不要跳过多 seed 汇总就直接宣传复现完成。
