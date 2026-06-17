# IFBench Qwen3 deterministic replay 对比报告

## 总览

- 路线：`DashScope/Qwen3 paper-adapted cloud-low-concurrency`
- replay 参数：`temperature=0`，`top_p=0.95`
- Baseline deterministic replay：1 次，`294/294`
- GEPA deterministic replay：1 次，`294/294`
- Baseline deterministic score：`34.353741`
- GEPA deterministic score：`35.204082`
- GEPA - Baseline：`0.85034`
- GEPA 退化 / 改善 / 持平：`23 / 29 / 242`
- finish_reason 捕获状态：`not_captured_by_current_runner`

## Group Score

| group | count | baseline | gepa | delta |
| --- | ---: | ---: | ---: | ---: |
| count | 53 | 45.283019 | 40.566038 | -4.716981 |
| custom | 10 | 40 | 0 | -40 |
| format | 91 | 56.043956 | 66.483516 | 10.43956 |
| ratio | 34 | 27.941176 | 20.588235 | -7.352941 |
| repeat | 9 | 0 | 0 | 0 |
| sentence | 22 | 18.181818 | 29.545455 | 11.363636 |
| words | 75 | 11.333333 | 10.666667 | -0.666667 |

## 与 exact replay 的关系

- Exact replay 下：Baseline `36.56`，GEPA `34.013605`，GEPA - Baseline `-2.546395`。
- Deterministic replay 下：Baseline `34.353741`，GEPA `35.204082`，GEPA - Baseline `0.85034`。
- 这说明采样随机性会显著影响 IFBench 结果；但 GEPA 在 deterministic 下的绝对分数仍低于论文读数和 stochastic Baseline。

## 解释边界

- 本报告不是 strict Arbor 论文复现。
- 当前 runner 未捕获 provider 原始 finish_reason。
