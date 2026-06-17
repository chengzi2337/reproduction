# IFEval prompt-transfer preflight 说明

## 任务目的

本任务搭建 IFEval prompt-transfer 迁移实验框架和 dry-run/preflight，不产生真实 API 实验证据。

核心研究问题是：P2/MHC 是否可迁移为 hard instruction-following constraint-priority principle，而不是只属于 IFBench trick。

## 目录结构

- `configs/ifeval_prompt_transfer_variants.json`：6 个 prompt variant 的结构化定义。
- `scripts/ifeval_prompt_transfer_preflight.py`：只做本地 preflight，不调用模型。
- `scripts/run_ifeval_prompt_transfer.py`：后续真实 runner stub，默认 dry-run。
- `reports/ifeval_prompt_transfer_preflight.json`：preflight 结构化输出。
- `reports/ifeval_prompt_transfer_preflight.md`：preflight 人读报告。
- `tests/test_ifeval_prompt_transfer_preflight.py`：本地验证测试。

## IFEval sample schema

- `prompt`：字符串，IFEval 原始用户指令。
- `instruction_id_list`：字符串列表，rule checker 使用的约束标识。
- `kwargs`：列表或对象，每条约束的参数。
- `metadata`：对象，可选，用于记录本地来源、索引和原始字段。

## Prompt variant schema

每个 variant 必须包含：

- `variant_id`
- `display_name`
- `source`
- `intended_hypothesis`
- `prompt_delta`
- `risk_notes`

`prompt_delta` 是结构化对象，真实 runner 应直接读取配置，不应把 prompt 文本散落硬编码到 runner 中。

## Preflight 使用方式

```powershell
python scripts/ifeval_prompt_transfer_preflight.py
```

如果本地没有 IFEval 数据，preflight 会输出 `dataset_status: dataset_missing`，不会崩溃，也不会下载数据。

如需指定本地数据文件：

```powershell
python scripts/ifeval_prompt_transfer_preflight.py --dataset-path path\\to\\ifeval.jsonl
```

## 后续真实 API run 入口

后续真实运行必须通过单独入口显式启动：

```powershell
python scripts/run_ifeval_prompt_transfer.py --enable-api-run --dataset-path path\\to\\ifeval.jsonl
```

当前 runner 只是 stub。即使传入 `--enable-api-run`，在真实调用未实现前也会返回 `blocked`，不会静默 fallback 到任何云调用。

## Rule checker 口径

IFEval 必须使用 rule checker，不使用 LLM judge。当前 preflight 只检查 checker 模块是否可导入，并在不可用时输出 `checker_status: checker_unavailable` 和修复建议。

## 当前 caveats

- 本任务没有调用真实 API。
- 本任务没有启动 full-budget GEPA。
- 本任务没有下载 IFEval 数据。
- 本任务没有读取 `.codex/gepa-artifact`。
- 本任务不是实验证据，只是迁移实验框架和 preflight。
