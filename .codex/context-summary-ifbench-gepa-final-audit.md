# 项目上下文摘要（IFBench GEPA 最终审计）

生成时间：2026-06-10

## 1. 相似实现分析

- **实现1**：`scripts/run_ifbench_qwen3_smoke.py:663`
  - 模式：`backfill_missing_test_metric_rows()` 读取 test metric JSONL，定位缺失 `idx_in_split`，补 `metric_output=0` 的审计行并按 idx 排序。
  - 可复用：补行字段、`recovery_status`、`recovery_reason`、`example_key`。
  - 需注意：补行只用于 DSPy evaluation 未写 metric row 的失败样本，不能用于 provider、timeout 或 rate-limit 硬失败。
- **实现2**：Baseline run 的 `metric_logs/test.jsonl`
  - 模式：缺失 `idx_in_split=112` 已按同一补行格式记录为 0 分。
  - 可复用：以 `metric_sum` 与 `evaluation_result score` 一致性证明补行不改变分数。
  - 需注意：保留逐样本完整性，不删除、不过滤 IFBench 样本。
- **实现3**：GEPA run 的 `provider_rejections.json`
  - 模式：DashScope provider runtime rejection 单独审计，不混入 test metric 缺失补行。
  - 可复用：`total_events`、`counts_by_scope`、`events` 用于区分 provider rejection 与 DSPy parse failure。
  - 需注意：provider rejection adaptation 不是 strict Arbor 论文运行时。

## 2. 项目约定

- 命名约定：Python 代码使用 snake_case；实验目录沿用 `IFBench_IFBenchCoT2StageProgram_<optimizer>_qwen3-8b-dashscope-paper-adapted`。
- 文件组织：实验产物位于 `.codex/gepa-artifact/experiment_runs_data/experiment_runs/seed_0/`；研究报告位于 `reports/`；操作与验证留痕位于 `.codex/`。
- 代码风格：本轮不改 runner 逻辑，只处理实验产物审计与文档。

## 3. 可复用组件清单

- `backfill_missing_test_metric_rows()`：缺失 metric row 的唯一补齐语义来源。
- `read_example_key()`：补行时读取 IFBench 样本 key。
- `evaluation_results/evaluation_result.txt`：最终 score 与 token 统计来源。
- `metric_logs/test.jsonl`：逐样本 metric 完整性来源。

## 4. 测试策略

- 统计 `test.jsonl` 行数、唯一 idx、缺失 idx、重复 idx。
- 计算 `metric_sum / 294 * 100`，与 `evaluation_result.txt` 中 score 对齐。
- 分开统计 provider rejection、DSPy parse failure、timeout、rate-limit、BadRequest。
- 执行脱敏密钥扫描，不输出任何明文 key。

## 5. 依赖和集成点

- 外部依赖：DashScope 云 API，仅通过环境变量注入 key。
- 内部依赖：IFBench 测试集、DSPy Evaluate、GEPA optimizer、runner 低并发适配。
- 集成方式：不改主入口，不改数据，不改 metric，不改 GEPA budget，只补齐审计产物。

## 6. 技术选型理由

- 使用既有补行语义：保持 Baseline 与 GEPA 的失败样本处理一致。
- 不重启实验：主运行已完成且分数已落盘，重跑会引入云 API 非确定性。
- 不把 provider rejection 与 parse failure 混为一类：两者对实验解释不同，必须分开审计。

## 7. 关键风险点

- 并发问题：低并发改变运行调度，但不改变样本、prompt、metric 或 optimizer budget。
- 边界条件：缺失 metric row 只能补 0，不能伪造 prediction。
- 性能瓶颈：无新增运行成本，仅处理 294 行 JSONL。
- 研究风险：当前只有单 seed、单 benchmark，不能作为论文级最终结论。
