# IFBench/Qwen3 full-budget seed 1 中期 Prompt 审计

## 状态

- 路线：DashScope/Qwen3 paper-adapted cloud-low-concurrency。
- optimizer：GEPA。
- budget：3593。
- 本报告是运行中审计，不是最终结果，不纳入多 seed 分数统计。
- 最近观测：`train=43`、`val=890`、`test=0`，尚无 `evaluation_result.txt`。

## 候选演化

### 候选 0

- 第一阶段：`Respond to the query`
- 第二阶段：原始“确保响应正确并遵守约束”指令。
- 未检测到重复请求、长回答倾向或 hard-constraint priority。

### 候选 1

- 第一阶段保持原始指令。
- 第二阶段被改写为先逐字重复 query，再回答。
- 还加入“清晰简洁”“准确且最新”“完整代码”“markdown 列表”“显式描述策略”等泛化要求。
- 未加入 hard-constraint priority。

### 候选 2

- 第一阶段也被改写为先完整重复 query，再回答。
- 第二阶段沿用候选 1 的重复请求指令。
- 对 plain text、分隔符、准确性、领域知识等又增加了通用要求。
- 未加入 hard-constraint priority。

## 中期判断

1. seed 1 已独立复现“先重复请求”的 prompt bias。
2. 该偏置此前也出现在 small-budget seeds 0/1/2 和 full-budget seed 0，因此不是单个 seed 的偶发现象。
3. GEPA 正在把一个局部验证集上可能有利的策略从第二阶段扩散到两个 predictor，而不是学出 P2 实验已验证有效的 hard-constraint priority。
4. 这支持“优化目标或反思反馈更容易奖励表面通用策略，而不能稳定识别 IFBench 的硬约束优先级”这一研究假设。
5. 由于 seed 1 尚未完成，当前只能证明搜索轨迹偏置，不能确定最终选中的 program 或最终 test 分数。
