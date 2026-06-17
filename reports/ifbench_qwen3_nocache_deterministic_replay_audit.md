# IFBench/Qwen3 no-cache replay pair 审计

## 总览

- replay tag：`nocache-deterministic-t0`
- 门禁通过：`True`
- 判定：`gepa_not_below_baseline_or_gate_failed`
- Baseline score：`36.111111`
- GEPA score：`36.337868`
- GEPA - Baseline：`0.226757`
- GEPA 退化 / 改善 / 持平：`47 / 45 / 202`

## Group Score

| group | count | baseline | gepa | delta |
|---|---:|---:|---:|---:|
| count | 53 | 45.91195 | 45.597484 | -0.314465 |
| custom | 10 | 30.0 | 0.0 | -30.0 |
| format | 91 | 59.70696 | 67.765568 | 8.058608 |
| ratio | 34 | 25.490196 | 18.137255 | -7.352941 |
| repeat | 9 | 0.0 | 3.703704 | 3.703704 |
| sentence | 22 | 21.969697 | 25.757576 | 3.787879 |
| words | 75 | 14.666667 | 11.777778 | -2.888889 |
