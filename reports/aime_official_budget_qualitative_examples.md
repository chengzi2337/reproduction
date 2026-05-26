# AIME official_budget qualitative examples

## 文档定位

本文档只读整理已有 `AIME official_budget` 逐题评估 artifacts，用来补充分数表不直观的问题。

数据来源：

- `outputs/gepa_aime_official_budget_seed*/.../per_example_eval.jsonl`
- 字段包括 `sample_id`、`prompt_version`、`question`、`prediction`、`gold`、`score`、`error`、`attempt_count`

本文档不调用模型、不调用 GEPA、不运行新实验、不重新判分，也不构成新的 performance claim。

## 先看一个关键现象

seed prompt 本身已经要求固定输出格式，原始 `system_prompt` 为：

```json
{
  "system_prompt": "You are a helpful assistant. Answer the question. Put your final answer in the format '### <answer>'"
}
```

这里的 `### <answer>` 是说明性模板；official evaluator 实际匹配的是类似 `### 70`、`### 588` 的具体 gold 字符串，而不是字面量 `<answer>`。

逐题记录显示，seed prompt 的很多 `score = 0` 并不是因为数学答案一定错，而是因为 seed prompt 虽然已有 `### <answer>` 要求，但该格式约束很短、约束力弱；模型经常沿用数学题常见的 `\boxed{...}` 输出习惯，导致与当前 evaluator 的 strict output protocol 不匹配。

典型模式：

```text
gold: ### 70
seed prediction final: \boxed{70}
seed score: 0
optimized prediction final: ### 70
optimized score: 1
```

因此，5-seed official_budget 的提升里包含一个非常明确的成分：optimized prompt 更稳定地遵守 official output protocol。它不应被简单解释成“数学推理能力全部提升”，也不应被简单解释成“prompt 越长越好”。

## 跨 seed 的直观统计

以下统计只用于理解 artifacts 的形态，不替代正式分数报告。

| seed | prompt_version | rows | score_sum | empty_predictions | zero_score_with_boxed |
|---|---|---:|---:|---:|---:|
| seed0 | seed | 150 | 30 | 9 | 110 |
| seed0 | optimized | 158 | 100 | 9 | 6 |
| seed1 | seed | 150 | 25 | 12 | 113 |
| seed1 | optimized | 150 | 100 | 6 | 0 |
| seed2 | seed | 150 | 34 | 7 | 108 |
| seed2 | optimized | 150 | 139 | 10 | 0 |
| seed3 | seed | 150 | 38 | 12 | 100 |
| seed3 | optimized | 150 | 109 | 7 | 7 |
| seed4 | seed | 150 | 26 | 9 | 115 |
| seed4 | optimized | 150 | 99 | 7 | 1 |

说明：

- `zero_score_with_boxed` 表示 prediction 中包含 `\boxed{...}`，但 score 仍为 `0`。
- 这通常说明格式不符合 official output protocol，但不自动证明数学过程正确。
- seed0 optimized 有 158 行，说明该 artifact 中存在额外记录；正式 performance 结论仍以已归档 summary 为准。

## 代表样例

以下样例来自 seed2，因为 seed2 的 optimized test score 最高，且能覆盖多种直观模式。

### 样例 1：seed 数学答案对，但格式错；optimized 格式正确

- `sample_id`: `test-1`
- 题目摘要：求所有整数进制 `b > 9`，使 `17_b` 整除 `97_b`，并求这些 base 的和。
- `gold`: `### 70`

| prompt_version | score | 预测摘要 |
|---|---:|---|
| seed | 0 | 推出 `b+7` 整除 `56`，得到 `b = 21, 49`，和为 `70`，但最后写成 `\boxed{70}` |
| optimized | 1 | 同样得到 `21 + 49 = 70`，并以 `### 70` 结尾 |

直观解释：这个样例显示 seed prompt 已有格式要求但未被遵守，而 optimized prompt 更好地遵守了 evaluator 需要的最终答案协议。

### 样例 2：seed 和 optimized 都正确

- `sample_id`: `test-2`
- 题目摘要：三角形内点与反射构造的几何面积题，求 heptagon `AFNBCEM` 面积。
- `gold`: `### 588`

| prompt_version | score | 预测摘要 |
|---|---:|---|
| seed | 1 | 通过相似比例和面积分解得到面积 `588`，最终输出 `### 588` |
| optimized | 1 | 用长度和面积关系求出三角形面积 `588`，最终输出 `### 588` |

直观解释：optimized prompt 并不是每题都“修复”seed；有些题 seed 本来就能正确完成。

### 样例 3：seed 组合计数答案对但格式错；optimized 修正格式

- `sample_id`: `test-3`
- 题目摘要：9 名队员选择三种冰淇淋口味，计数满足 `chocolate > vanilla > strawberry` 的分配数模 `1000`。
- `gold`: `### 16`

| prompt_version | score | 预测摘要 |
|---|---:|---|
| seed | 0 | 找到三组计数 `(6,2,1)`、`(5,3,1)`、`(4,3,2)`，算出余数 `16`，但最后写成 `\boxed{16}` |
| optimized | 1 | 同样完成组合计数，并按 `### 16` 输出 |

直观解释：这类题说明不少分数差异来自输出协议遵循，而不是答案数值本身。

### 样例 4：optimized 仍可能失败，甚至为空回答

- `sample_id`: `test-118`
- 题目摘要：有理数递推 `x_{k+1} = (x_k + 1/x_k - 1) / 3`，求 `x_2025 = m/n` 时 `m+n` 模 `1000`。
- `gold`: `### 248`

| prompt_version | score | 预测摘要 |
|---|---:|---|
| seed | 1 | 推导递推变换并最终输出 `### 248` |
| optimized | 0 | artifact 中 prediction 为空 |

直观解释：optimized prompt 总体更好，但不是逐题单调改进；它仍会在少数题上退化。

### 样例 5：两者都失败

- `sample_id`: `test-44`
- 题目摘要：凸五边形边长与角度约束下，最小化五个距离和，求 `m+n+p`。
- `gold`: `### 60`

| prompt_version | score | 预测摘要 |
|---|---:|---|
| seed | 0 | artifact 中 prediction 为空 |
| optimized | 0 | artifact 中 prediction 为空 |

直观解释：还有一部分题不是格式问题，而是两种 prompt 都没有形成有效回答。

## 对分数结果的解释帮助

这些样例说明：

1. official_budget 的提升不仅可能体现在任务行为，也明显体现在最终答案格式遵循上。
2. seed prompt 已要求 `### <answer>`，但该短格式约束经常没有被遵守，模型仍会输出 `\boxed{...}`。
3. optimized prompt 更常输出类似 `### 70` 的具体答案格式，因此更适配当前评估协议。
4. optimized prompt 并不保证逐题不退化，仍存在 seed 对而 optimized 错或空回答的样例。
5. 因此最终结论仍应写成“5 / 5 seeds 上 optimized prompt 优于 seed prompt”，而不是“optimized prompt 在每一道题上都更好”。

answer extractability audit 进一步量化了这个判断：

- seed official score: `0.204`
- optimized official score: `0.722666666667`
- seed relaxed extractable score: `0.922666666667`
- optimized relaxed extractable score: `0.938666666667`
- official score gain: `0.518666666667`
- relaxed extractable score gain: `0.016`
- seed format loss: `539`
- optimized format loss: `162`

因此，5-seed official_budget 结果支持 official evaluator 下的稳定提升；但 observed official-score gain 不能解释为 pure reasoning improvement，相当大比例来自 output-protocol adherence improvement。

## 结论边界

可以写：

- 逐题 artifacts 能解释一部分分数差异；
- 格式遵循是 optimized prompt 收益的重要组成部分；
- answer extractability audit 显示 relaxed extractable score 只提升 `0.016`；
- qualitative examples 支持最终报告更直观地展示复现结果。

不能写：

- 所有提升都来自格式；
- 所有提升都来自推理能力；
- optimized prompt 在每题上都优于 seed prompt；
- 这是新的实验；
- 这是新的性能评估。
