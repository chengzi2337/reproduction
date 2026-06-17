# IFBench/Qwen3 no-cache replay pair 审计

## 总览

- replay tag：`nocache-exact-t06`
- 门禁通过：`True`
- 判定：`gepa_stably_below_baseline`
- Baseline score：`34.807256`
- GEPA score：`34.637188`
- GEPA - Baseline：`-0.170068`
- GEPA 退化 / 改善 / 持平：`40 / 43 / 211`

## Group Score

| group | count | baseline | gepa | delta |
|---|---:|---:|---:|---:|
| count | 53 | 45.91195 | 41.823899 | -4.08805 |
| custom | 10 | 20.0 | 3.333333 | -16.666667 |
| format | 91 | 58.791209 | 65.750916 | 6.959707 |
| ratio | 34 | 24.019608 | 19.117647 | -4.901961 |
| repeat | 9 | 0.0 | 0.0 | 0.0 |
| sentence | 22 | 21.212121 | 18.181818 | -3.030303 |
| words | 75 | 12.888889 | 12.0 | -0.888889 |
