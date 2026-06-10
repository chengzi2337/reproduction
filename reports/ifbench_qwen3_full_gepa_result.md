# IFBench Qwen3 DashScope adapted 完整 GEPA 结果

生成时间：2026-06-10

## 结论

本次 `DashScope/Qwen3 paper-adapted cloud-low-concurrency` 路线已经完成一整条 IFBench Baseline 与 GEPA 对比，并通过逐样本完整性门禁。

该结果不支持“GEPA 在本配置下优于 Baseline”的结论：GEPA 最终分数为 `35.88`，Baseline 最终分数为 `36.56`，GEPA 低 `0.68` 分。

该结论只能用于当前 DashScope 云 API 适配路线，不能声明为 strict Arbor 论文运行时复现。

## 结果表

| 项目 | Baseline | GEPA |
| --- | ---: | ---: |
| score | 36.56 | 35.88 |
| metric sum | 107.5 / 294 | 105.5 / 294 |
| test metric rows | 294 / 294 | 294 / 294 |
| unique `idx_in_split` | 294 | 294 |
| missing idx | 0 | 0 |
| duplicate idx | 0 | 0 |
| final input tokens | 172009 | 540487 |
| final output tokens | 194414 | 280884 |
| optimizer input tokens | 不适用 | 3877941 |
| optimizer output tokens | 不适用 | 2480458 |

## 审计补齐

Baseline 与 GEPA 各有 1 条 DSPy evaluation 解析失败导致的 metric row 缺失。两者均按同一套审计逻辑补为 0 分失败样本：

| run | idx | example key | metric output | recovery reason |
| --- | ---: | --- | ---: | --- |
| Baseline | 112 | 112 | 0 | `dspy_evaluate_error_without_metric_row` |
| GEPA | 241 | 241 | 0 | `dspy_evaluate_error_without_metric_row` |

GEPA 补齐前的 metric sum 已经是 `105.5`，补齐后仍为 `105.5`。因此补齐只改变审计完整性，不改变分数含义。

## 错误分类

- Baseline：无 provider rejection 审计文件；最终 test 集完整。
- GEPA：`provider_rejections.json` 记录 `total_events=10`，其中 `program_prediction=9`、`instruction_proposal=1`。这些是 DashScope provider runtime 适配处理的事件，主要发生在优化阶段，不是 test metric 缺失 idx=241 的病因。
- GEPA final test 缺失 idx=241 的病因为 DSPy evaluation 写 metric 前解析失败，已按 0 分审计补齐。
- 日志中未发现实际 `Timeout`、`APITimeout`、`ReadTimeout` 或 `RateLimitError` 硬失败。

## 本地门禁

- 逐样本完整性：Baseline 与 GEPA 均为 `294/294`，无缺失 idx、无重复 idx。
- 分数一致性：Baseline `107.5/294*100=36.56`，GEPA `105.5/294*100=35.88`，均与 `evaluation_result.txt` 对齐。
- 密钥扫描：扫描 `reports`、`scripts`、`tests`、`.codex` 下 4331 个文本类文件，`sk-[A-Za-z0-9]{20,}` 命中 0。

## 与论文读数对比

论文 Figure 9(b) 中 IFBench/Qwen3 的手工读数约为：

| 项目 | 论文读数 | 本次 DashScope adapted |
| --- | ---: | ---: |
| Baseline | 36.9 | 36.56 |
| GEPA | 38.6 | 35.88 |
| GEPA - Baseline | +1.7 | -0.68 |

本次 Baseline 接近论文读数，但 GEPA 没有复现论文中的正向提升。

## 后续建议

下一步应优先做多 seed 和至少一个额外 benchmark，而不是只凭当前单 seed 得出最终研究结论。当前最值得排查的方向是后端差异、云 API 模型版本不可锁定、GEPA 验证集选择与过拟合、以及 DashScope provider rejection adaptation 对优化轨迹的影响。
