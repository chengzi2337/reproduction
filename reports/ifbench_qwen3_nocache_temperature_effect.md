# IFBench/Qwen3 no-cache 温度效应审计

- 判定：`deterministic_reverses_stochastic_degradation`
- stochastic GEPA - Baseline：`-0.170068`
- deterministic GEPA - Baseline：`0.226757`
- delta shift：`0.396825`

| 设置 | Baseline | GEPA | GEPA - Baseline |
|---|---:|---:|---:|
| temperature=0.6 | 34.807256 | 34.637188 | -0.170068 |
| temperature=0 | 36.111111 | 36.337868 | 0.226757 |
