# Stage 2A MiMo Strict Default Path Recovery Design and Minimal Diagnosis

## 定位

- 本文档同时记录：
  - `Stage 2A: MiMo strict default path recovery` 的设计边界
  - 当前节点已完成的一次最小真实诊断
- 它不是 `Stage 2C`
- 它不是 GEPA smoke
- 它不是性能结论

## strict default path 的定义

本路径必须同时满足以下条件：

- 数据入口仍然是 `from gepa.examples.aime import init_dataset`
- 优化入口仍然是 `gepa.optimize(...)`
- 模型入口仍然是字符串路径：
  - `task_lm = "openai/<model>"`
  - `reflection_lm = "openai/<model>"`
- 不修改 `DefaultAdapter`
- 不修改 evaluator
- 不引入 callable
- 不显式传入受控生成参数，例如：
  - `thinking.disabled`
  - `max_completion_tokens`

对 MiMo 而言，当前 strict default path 的目标可压缩为一句话：

> 在不传 `thinking.disabled`、不传 `max_completion_tokens`、不改 `DefaultAdapter`、不引入 callable 的条件下，确认 MiMo strict default path 是否能够稳定完成单样本 AIME content 返回。

## 它与 Stage 2B 的区别

`Stage 2B: MiMo controlled-generation diagnostic path` 的特征是：

- 显式使用 `thinking.disabled`
- 显式限制 `max_completion_tokens`
- 只验证 direct SDK 与 LiteLLM 单样本可达

而 `Stage 2A strict default path recovery` 的特征是：

- 不显式施加生成控制
- 只接受 strict default path 自带的默认调用语义
- 目标是恢复 strict path 的可诊断性，而不是证明受控生成路径可行

因此：

- Stage 2B 成功，不能推出 Stage 2A 已成功
- Stage 2A 若失败，也不能否定 Stage 2B 的可用性

## 当前最小真实诊断

本轮最小真实诊断的意图是：

1. 先确认默认 completion 路径对极简单 prompt 是否正常
2. 再确认真实 AIME prompt 在默认 generation 下是否仍然卡住
3. 由此把 blocker 从“路径整体不可用”收缩到“某类 prompt 组合触发”

对应脚本入口为：

- `scripts/stage2a_diagnose_mimo_strict_default_path_blocker.py`

输出 `path_type` 固定为：

- `stage2a_mimo_strict_default_path_blocker`

## 已得最小结论

- `mimo-v2.5-pro` 的默认 direct SDK 与默认 LiteLLM 路径，对简单 `OK` prompt 都能在数秒内正常返回
- 真实 AIME prompt 在默认 generation 下，direct SDK 与 LiteLLM 都出现长时间挂起
- 因此当前 blocker 不是：
  - provider connectivity
  - credential
  - LiteLLM `openai/<model>` 字符串路径本身
  - `init_dataset()` 数据入口
- 当前 blocker 更准确地说是：
  - 真实 AIME prompt 与 MiMo strict default generation 组合下的 completion 层行为

更严谨的表述应为：

> MiMo strict default path 在当前 endpoint、当前代理可达路径、当前模型 `mimo-v2.5-pro`、当前真实 AIME prompt 下尚未闭环。

## 允许做的诊断

路线 A 的前半段只允许以下诊断：

1. 继续使用 `gepa.examples.aime.init_dataset()` 取真实 AIME 单样本
2. 继续使用 README quickstart seed prompt 作为 strict README quickstart 语义参照
3. 继续记录 simple `OK` prompt 与真实 AIME prompt 的差异
4. 继续检查 provider 可达路径是否稳定
5. 继续检查 strict default path 的单样本返回是否产生最终 `content`
6. 继续记录 direct SDK、LiteLLM、strict path 三层之间的现象差异
7. 缩小诊断范围到单样本、最小请求数、最小执行窗口

## 不允许做的诊断

路线 A 的前半段明确禁止以下动作：

1. 不把 `thinking.disabled` 接入 GEPA 路径
2. 不把 `max_completion_tokens` 接入 GEPA 路径
3. 不修改 `DefaultAdapter`
4. 不修改 evaluator
5. 不引入 callable
6. 不手工拼接 `reasoning_content` 到 `content`
7. 不启动 `gepa.optimize()` 的新 smoke / pilot
8. 不把 Stage 2B 的受控生成成功混写成 Stage 2A strict 成功

## 成功标准

只有同时满足以下条件，才可视为路线 A 前半段闭环：

1. strict default path 仍保持官方核心调用语义不变
2. MiMo 在可达路径上可完成真实 AIME 单样本返回
3. 返回的是最终 `content`
4. 该结果能够稳定重复，而不是一次性偶发成功
5. 在此基础上，才允许重新进入 strict execute sanity

## 失败后的分叉

如果路线 A 前半段未闭环，则下一步才允许讨论：

- `Stage 2C: MiMo explicitly controlled-generation GEPA path`

届时必须明确写清：

- 它是非 strict 路径
- 它是工程适配路径
- 它不能和 Stage 1 DeepSeek strict 或 wrapper 结果直接比较
- 它不能写成 original GEPA same-model reproduction

## 当前结论

- 现在还不进入 Stage 2C
- 现在也不运行 MiMo GEPA smoke
- 当前 checkpoint 已足够说明：
  - simple `OK` prompt 默认 completion 可用
  - 真实 AIME prompt 默认 completion 未闭环
- 下一步如果继续路线 A，应先做 prompt complexity decomposition 设计，而不是直接扩大请求规模
