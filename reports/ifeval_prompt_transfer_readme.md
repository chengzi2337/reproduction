# IFEval prompt-transfer preflight 说明

## 任务目的

本任务搭建 IFEval prompt-transfer 迁移实验框架和 dry-run/preflight，不产生真实 API 实验证据。

核心研究问题是：P2/MHC 是否可迁移为 hard instruction-following constraint-priority principle，而不是只属于 IFBench trick。

## 目录结构

- `configs/ifeval_prompt_transfer_variants.json`：6 个 prompt variant 的结构化定义。
- `scripts/ifeval_prompt_transfer_preflight.py`：只做本地 preflight，不调用模型。
- `scripts/run_ifeval_prompt_transfer.py`：后续真实 runner stub，默认 dry-run。
- `src/ifeval_official_adapter.py`：官方 IFEval 数据和 rule checker 的轻量本地 adapter。
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

如果本地没有 IFEval assets，preflight 会输出 `status: blocked`、`dataset_status: dataset_missing` 或 `checker_status: checker_unavailable`，不会崩溃，也不会下载数据。

推荐准备方式是把 `google-research` 仓库放在当前 repo 外部或未纳入提交的 `external/` 目录中：

```powershell
git clone https://github.com/google-research/google-research.git external\\google-research

python scripts/ifeval_prompt_transfer_preflight.py `
  --ifeval-root external\\google-research\\instruction_following_eval
```

也可以使用 sparse checkout，只取官方 IFEval 目录；但本脚本不会自动执行下载。

如需显式指定本地数据文件：

```powershell
python scripts/ifeval_prompt_transfer_preflight.py `
  --ifeval-root external\\google-research\\instruction_following_eval `
  --dataset-path external\\google-research\\instruction_following_eval\\data\\input_data.jsonl
```

路径解析优先级为：显式 `--dataset-path`、`--ifeval-root\\data\\input_data.jsonl`、环境变量 `IFEVAL_ROOT`、默认候选路径。

## 后续真实 API run 入口

后续真实运行必须通过单独入口显式启动：

```powershell
python scripts/run_ifeval_prompt_transfer.py `
  --enable-api-run `
  --ifeval-root external\\google-research\\instruction_following_eval
```

当前 runner 只是 stub。即使传入 `--enable-api-run`，在真实调用未实现前也会返回 `blocked`，不会静默 fallback 到任何云调用。

## Rule checker 口径

IFEval 必须使用官方 rule checker，不使用 LLM judge。当前 preflight 会检查以下模块是否可导入：

- `instruction_following_eval.evaluation_lib`
- `instruction_following_eval.instructions`
- `instruction_following_eval.instructions_registry`
- `instruction_following_eval.instructions_util`

当 checker 可用时，preflight 会从本地 `input_data.jsonl` 读取 1 到 3 条样本，构造 fake response，并调用官方 `evaluation_lib.test_instruction_following_strict()` 与 `test_instruction_following_loose()` 做本地 smoke test。fake response 不要求得高分，只证明 checker 能执行并返回结构化结果。

preflight ready 只表示官方数据和 checker 已接入，不是 IFEval prompt-transfer 实验结果。下一阶段才会显式运行 prompt-transfer API 评测。

## 外部源码与 license 说明

- 当前仓库不 vendoring Google Research 源码。
- 不要把完整 `google-research` 仓库提交进当前 repo。
- 如果将来要 vendoring 官方 IFEval 文件，必须先确认 license，并保留来源说明。

## 当前 caveats

- 本任务没有调用真实 API。
- 本任务没有启动 full-budget GEPA。
- 本任务没有下载 IFEval 数据。
- 本任务没有读取 `.codex/gepa-artifact`。
- 本任务不是实验证据，只是迁移实验框架、官方 IFEval 数据和 rule checker 接入 preflight。
