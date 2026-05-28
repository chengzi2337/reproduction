# Stage 4 MiMo Pro vs GLM-4.7 机制诊断计划

## 定位

本文档定义新的 `Stage 4`，只面向：

- MiMo Pro
- GLM-4.7

在当前 AIME fixed-prompt diagnostic 语境下的机制边界排查。

它不是：

- 原论文复现
- DeepSeek `official_budget` continuation
- 5-seed 扩展
- GEPA 优化实验
- 模型排行榜
- 最终性能比较

## 当前已知前提

- DeepSeek AIME `official_budget` 5-seed 已完成。
- `5 / 5` seeds 上 `optimized prompt > seed prompt`。
- `answer extractability audit` 已显示：
  - `official score gain` 很大；
  - `relaxed extractable score gain` 很小；
  - observed official-score gain 很大程度来自 output-protocol adherence，而不是 pure reasoning improvement。
- `format-controlled seed baseline smoke` 已显示：
  - `original_seed_prompt`: `official = 0.233333333333`, `relaxed = 0.933333333333`, `format_loss = 21 / 30`
  - `strong_format_seed_prompt`: `official = 0.866666666667`, `relaxed = 0.866666666667`, `format_loss = 0 / 30`

因此，后续任何新模型诊断都不能只看 `official score`，必须并列看：

- `relaxed extractable score`
- `format loss`
- `timeout`
- `empty output`
- `finish_reason`
- 原始输出片段

## Stage 4 总体拆分

### Stage 4A：Provider Probe

目标：

- 只验证 MiMo Pro 和 GLM-4.7 的 provider connectivity
- 只验证 raw SDK 与 LiteLLM 双路径的一致性
- 只验证最小 prompt 的 content / timeout / finish_reason 行为

不做：

- AIME 评估
- GEPA
- `official_budget`
- `pilot`
- 5-seed

### Stage 4B：AIME fixed-prompt 30-sample baseline

只有在 Stage 4A 中：

- MiMo 至少有一条可用调用路径
- GLM 至少有一条可用调用路径

才允许进入 Stage 4B。

若任一 provider 不可用，必须停在 Stage 4A，写清 blocker，不允许绕过。

## 当前立即任务

当前只做 Stage 4A：

1. 确认当前分支。
2. 新增 Stage 4 总计划与 Stage 4A 设计。
3. 新增 Stage 4A provider probe 脚本与测试。
4. 默认 dry-run，不调用模型。
5. 运行 `python -m compileall src scripts tests`。
6. 运行 `pytest -q`。
7. 不进入 Stage 4B。
8. 不运行 GEPA。

## 结果边界

当前阶段允许写：

- provider reachable / not reachable
- key valid / invalid / unknown
- model supported / unsupported / unknown
- content returned / empty
- timeout / no timeout
- raw SDK 与 LiteLLM 是否一致

当前阶段不允许写：

- MiMo Pro 比 GLM-4.7 强
- GLM-4.7 比 MiMo Pro 强
- 哪个模型数学能力更强
- 哪个模型更适合 `official_budget`
- 哪个模型已经完成 GEPA 复现
- 哪个模型可以直接进入 GEPA sanity

## 提交顺序

第一提交只覆盖 Stage 4A 脚手架与设计：

- `reports/stage4_mimopro_glm47_comparison_plan.md`
- `reports/stage4a_provider_probe_design.md`
- `scripts/stage4a_probe_mimopro_glm47.py`
- `tests/test_stage4a_probe_mimopro_glm47.py`
- `reports/stage4a_provider_probe_result.md`

第二提交才允许进入 Stage 4B 设计与 runner。
