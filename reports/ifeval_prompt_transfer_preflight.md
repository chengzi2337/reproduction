# IFEval prompt-transfer preflight

## 当前定位

- 当前没有调用真实 API。
- 当前只是 IFEval prompt-transfer 实验框架和 dry-run/preflight。
- IFEval 评估口径必须使用 rule checker，不使用 LLM judge。
- 后续真实运行必须通过单独入口 `scripts/run_ifeval_prompt_transfer.py` 显式启动。
- 当前实验要回答的问题是：P2/MHC 是否可迁移为 hard instruction-following constraint-priority principle。
- 本报告不是实验证据，不包含 IFEval 真实 API 运行结果。

## 结构化状态

- status：`blocked`
- api_call_enabled：`false`
- full_budget_gepa_enabled：`false`
- dataset_status：`dataset_missing`
- checker_status：`checker_unavailable`
- variant_count：`6`
- sample_count_detected：`0`

## Prompt variants

- `baseline` / Baseline：不加入 IFBench 约束优先级提示时，作为后续真实运行的对照组。
- `baseline_mhc` / Baseline + MHC：手工强调硬约束优先级可能改善 IFEval 的格式、计数和禁止项遵循，但这是待验证迁移假设。
- `verbose_helpfulness` / Verbose/helpfulness：偏向解释性和充分性的话术可能在硬格式或禁止项上引入额外文本，作为迁移研究的对照。
- `mhc_concise` / MHC + concise：硬约束优先级叠加简洁输出可能减少额外文本，从而降低违反格式、计数和禁止项的风险。
- `ifbench_gepa_prompt_transfer` / IFBench GEPA prompt transfer：IFBench 优化出的约束遵循提示可能携带可迁移结构，但不能假定其适配 IFEval。
- `gepa_p2_transfer` / GEPA + P2 transfer：GEPA prompt 的学习结构叠加 P2 硬约束优先级，可能比单独 GEPA prompt 更能迁移到 IFEval hard instruction-following。

## IFEval sample schema

- `prompt`：`string`；required=`true`；IFEval 原始用户指令文本。
- `instruction_id_list`：`list[string]`；required=`true`；rule checker 使用的 IFEval 指令约束标识列表。
- `kwargs`：`list[dict] | dict`；required=`true`；每条 instruction 对应的规则参数。
- `metadata`：`dict`；required=`false`；本地样本来源、索引和原始字段等审计信息。

## 阻断原因

- `dataset_missing`
- `checker_unavailable`

## 修复建议

- dataset：请把本地 IFEval JSONL/JSON 文件放入候选路径，或通过 --dataset-path 显式指定。
- checker：请安装或接入本地 IFEval rule checker，并暴露可导入的规则评估模块；不要改成 LLM judge。

## 后续入口

- `python scripts/run_ifeval_prompt_transfer.py --enable-api-run --dataset-path <本地 IFEval 文件>`
