# IFBench/Qwen3 官方 GEPA 框架对照 Preflight

## 实验边界

本对照属于 `DashScope/Qwen3 paper-adapted cloud-low-concurrency`，不是 Arbor/local Qwen
strict paper reproduction。唯一计划改变的核心变量是 GEPA 实现框架：

- 当前复现：论文 artifact 内置 GEPA + DSPy 2.6.23
- 框架对照：官方 `dspy.GEPA` + DSPy 3.2.1

以下内容保持一致：

- `IFBenchCoT2StageProgram`
- artifact 原始 `IFBench_train.jsonl` 与 `IFBench_test.jsonl`
- train/val/test：300/300/294
- artifact `metric_with_feedback`
- task LM 与 reflection LM 均为同一个 DashScope Qwen3
- `temperature=0.6`
- `top_p=0.95`
- `top_k=20`
- `max_tokens=8192`
- `max_metric_calls=3593`
- `num_threads=1`
- provider 内容拒绝时按 0 分或保持当前 instruction 的既有适配语义

## 实现选择

使用官方 `dspy.GEPA`，不使用字符串型默认 adapter。原因是 IFBench program 包含两个
DSPy predictor，必须保留两阶段 trace 和 predictor 级 feedback。

官方 GEPA 要求 metric 接受五个参数。新增包装仅完成协议转换：

1. program 总分仍由 artifact `metric_with_feedback` 计算。
2. predictor feedback 仍分别检查 `response` 与 `final_response`。
3. 返回给 GEPA 的 score 仍是 program 总分。
4. 不改变 IFBench instruction checker。

## Preflight 结果

- 状态：通过
- API 调用：0
- Python：3.13.5
- DSPy：3.2.1
- 官方入口：`dspy.GEPA`
- program：`IFBenchCoT2StageProgram`
- predictor：
  - `generate_response_module.predict`
  - `ensure_correct_response_module.predict`
- 数据池：300/300/294
- 五参数 metric：通过
- 两阶段 program 离线真实执行：通过
- 单元测试：8/8 通过
- replay、分析和框架相关联合测试：60/60 通过

## 运行顺序

为保持低并发和避免云端负载相互影响，不与 full-budget seed 1/2 并发：

1. 等待 artifact GEPA seed 1 完成。
2. 完成 artifact GEPA seed 2。
3. 先执行官方框架小预算真实 API sanity。
4. sanity 无协议错误后，再决定是否执行官方框架完整 3593 budget。

## 尚未满足

- preflight 只证明框架、数据和 metric 能正确连接，不证明优化结果等价。
- 官方框架真实 API run 尚未启动。
- 两个 DSPy 版本的内部 trace、解析和候选接受行为可能不同，这正是框架对照需要测量的变量。
- finish reason 已按 `optimization` 与 `test` phase 隔离，避免把优化调用混入最终 sample-level 统计。
