# IFBench/Qwen3 结果索引

本索引用于说明当前应优先引用哪些报告，以及哪些旧报告已经被后续 no-cache audit 或更完整的 multiseed 审计覆盖。所有结论均限定在 `DashScope/Qwen3 paper-adapted cloud-low-concurrency` 路线内，不能写成 strict Arbor/local Qwen 论文复现。

## Canonical current reports

| 报告 | JSON | 用途 |
| --- | --- | --- |
| `reports/ifbench_qwen3_nocache_exact_replay_audit.md` | `reports/ifbench_qwen3_nocache_exact_replay_audit.json` | 当前 exact temperature=0.6 no-cache replay 主证据。Baseline=`34.807256`，GEPA=`34.637188`，GEPA-Baseline=`-0.170068`。 |
| `reports/ifbench_qwen3_nocache_deterministic_replay_audit.md` | `reports/ifbench_qwen3_nocache_deterministic_replay_audit.json` | 当前 deterministic temperature=0 no-cache replay 主证据。Baseline=`36.111111`，GEPA=`36.337868`，GEPA-Baseline=`0.226757`。 |
| `reports/ifbench_qwen3_nocache_constraint_priority_audit.md` | `reports/ifbench_qwen3_nocache_constraint_priority_audit.json` | 当前 hard-constraint priority 改写主证据。Baseline+MHC=`38.435374`，相对 deterministic Baseline 提升 `2.324263`；GEPA+P2=`38.605442`，相对 deterministic GEPA 提升 `2.267574`。 |
| `reports/ifbench_qwen3_full_budget_multiseed.md` | `reports/ifbench_qwen3_full_budget_multiseed.json` | full-budget GEPA seed0/1/2 完整性和分数审计。三 seed 均值=`35.82333333333333`，三 seed 均已 complete。 |
| `reports/ifbench_qwen3_finish_reason_by_group.md` | `reports/ifbench_qwen3_finish_reason_by_group.json` | finish_reason 按 instruction group 的审计，特别用于检查 P2/MHC 的 `length` 事件分布和低分共现情况。 |

## Historical / superseded reports

| 报告 | 状态 | 原因 |
| --- | --- | --- |
| `reports/ifbench_qwen3_exact_replay_comparison.md` | historical / superseded | 旧 comparison 可能使用 cache 或旧 runner。当前引用应使用 no-cache exact replay audit。 |
| `reports/ifbench_qwen3_deterministic_replay_comparison.md` | historical / superseded | 旧 comparison 可能使用 cache 或旧 runner。当前引用应使用 no-cache deterministic replay audit。 |
| `reports/ifbench_qwen3_prompt_surgery_result.md` | historical / superseded | 这是 prompt surgery single-run 结果，后续 no-cache constraint-priority audit 和 followup 报告已经覆盖其主要证据。旧正文不再作为当前结论入口。 |
| `reports/ifbench_qwen3_missing_baselines_result.md` | historical / caveated | 该报告涉及 cached baseline backfill，不能与 no-cache replay 混为同一证据类型。 |
| `reports/ifbench_qwen3_missing_baseline_nocache_result.md` | supporting | 仅作为补齐 missing Baseline no-cache 运行的辅助记录，不替代 canonical no-cache audit。 |

## Current interpretation

当前证据不能写成“GEPA 论文失败”。更准确的表述是：在 DashScope/Qwen3 cloud-adapted 条件下，原始 GEPA final prompt 的 aggregate gain 不稳定；exact no-cache replay 中 GEPA 略低于 Baseline，deterministic no-cache replay 中 GEPA 略高于 Baseline，但幅度很小；full-budget GEPA 三 seed 均值也没有显示稳定优势。

更有研究价值的现象是 hard-constraint groups 的退化和可修复性：显式 hard-constraint priority 同时改善 Baseline 和 GEPA，且 no-cache constraint-priority audit 显示 MHC/P2 都能带来约 2.3 分提升。这说明当前研究重点应放在约束优先级、反思提示对硬约束任务的副作用、以及 cloud API 后端漂移对 GEPA prompt 搜索结论的影响。

当前 canonical numbers 来自 no-cache audit 和刷新后的 full-budget multiseed summary，不应继续引用旧 comparison 报告作为主证据。

## Known caveats

- 这不是 strict Arbor/local reproduction；原论文 Qwen 路线的 Arbor/local Qwen 服务在当前环境不可用。
- 云 API 模型版本无法像本地权重一样锁定，因此同一 prompt 在不同时间可能存在后端漂移。
- 当前 runner 存在 provider rejection adaptation；它只处理 provider 内容拒绝，不应扩展解释为算法本身的一部分。
- cache 与 no-cache 报告不可混用；cached baseline backfill 只能作为审计补齐记录，不能作为完全独立 API replay 证据。
- finish_reason 的 `length` 事件需要单独审计；当前 P2 length 事件与低分样本存在共现，但不能单独证明截断是低分因果原因。
- stdout/stderr 原始日志、worker logs、pytest 临时目录和 `.codex/gepa-artifact` 原始大目录未上传；仓库只保留 summary/audit 文件。
