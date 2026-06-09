# IFBench DashScope 后端可行性审计

时间：2026-06-09 08:26:42 +0800

## 快速结论

- 当前仓库对 DashScope Qwen3 的既有适配路径是 `OpenAI-compatible + extra_body(top_k / enable_thinking)`。
- 官方 OpenAI-compatible 文档明确承诺了 `temperature`、`top_p`、`max_tokens`、`stop`，但没有把 `top_k`、`enable_thinking` 写进参数表。
- 官方原生 DashScope 文档明确支持 `top_k`、`enable_thinking`、`thinking_budget` 与 `reasoning_content`，说明原生接口能力更完整，但不能直接推出 compatible-mode 也同等承诺。
- 本轮 live probe 状态：`executed`。
- 阶段门禁：strict reproduction 仍不满足启动条件；仅可继续 backend-adapted 预备审计。

## 本地环境检查

- `QWEN_API_KEY`：present
- `DASHSCOPE_API_KEY`：missing
- `OPENAI_API_KEY`：missing
- 本轮若执行实调，将只使用已存在的环境变量：`QWEN_API_KEY`

## 证据矩阵

| 项目 | strict 目标 | OpenAI-compatible 证据 | 原生 DashScope 证据 | 本地实现 | 判定 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| base_url | 需要通过 OpenAI SDK 指向 DashScope compatible-mode 端点。 | OpenAI SDK 源码支持 `base_url`；阿里云兼容页列出北京端点 `https://dashscope.aliyuncs.com/compatible-mode/v1`。 | 原生 DashScope 另有 `/api/v1` 端点，不等于 compatible-mode。 | `scripts/run_ifbench_qwen3_smoke.py` 默认 `DEFAULT_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1`。 | 文档确认 | 现有 IFBench wrapper 的连接方式与官方兼容页一致。 |
| temperature=0.6 | 论文 / artifact Qwen3 解码参数之一。 | 兼容页参数表明确支持 `temperature`，范围 `[0,2)`。 | 原生 DashScope 参数表也支持 `temperature`。 | `run_ifbench_qwen3_smoke.py` 与现有 AIME Qwen3 配置均使用 `0.6`。 | 文档确认 | 这一项可以作为 backend-adapted 运行的稳定映射项。 |
| top_p=0.95 | 论文 / artifact Qwen3 解码参数之一。 | 兼容页参数表明确支持 `top_p`。 | 原生 DashScope 参数表明确支持 `top_p`，并对 thinking / non-thinking 默认值分模型说明。 | `run_ifbench_qwen3_smoke.py` 与 AIME Qwen3 配置均使用 `0.95`。 | 文档确认 | 与论文协议一致，且兼容页有正式参数说明。 |
| top_k=20 | 论文 / artifact Qwen3 解码参数之一。 | 兼容页参数表未列出 `top_k`；DashScope Python SDK 的 OpenAI-compatible `Completions.create()` 签名显示有 `top_k`。 | 原生 DashScope 参数表明确支持 `top_k`，并给出“所有其他模型默认 20”。 | `run_ifbench_qwen3_smoke.py` 通过 `extra_body.top_k=20` 传递；AIME Qwen3 配置也写死 `top_k: 20`。 | 兼容页未承诺 | 当前仓库在用，但官方兼容页未正式写入参数表；需要实调确认当前后端是否接受。 |
| max_tokens=16384 | 论文 / artifact Qwen3 路径目标上限为 `16384`。 | 兼容页参数表支持 `max_tokens`，但强调“不同模型上限不同”。 | 原生 DashScope 页面也是按模型上限解释，不自动等于论文 Arbor 的 `16384`。 | `run_ifbench_qwen3_smoke.py` 保守使用 `8192`；AIME Qwen3 现有配置也保守使用 `8192`。 | 模型上限未最终确认 | 官方模型列表页面已确认 `qwen3-8b` 可用，但本轮工具未能稳定抽取其 max output 单元格；在真实 probe 前仍应保守维持 `8192`。 |
| stop | 论文未显式依赖，但复现实验需要确认兼容页是否支持停止词。 | 兼容页参数表明确支持 `stop`，可传字符串或数组。 | 原生 DashScope 参数表也支持 `stop`。 | 当前 IFBench wrapper 未主动设置 `stop`。 | 文档确认 | 若后续为收束输出协议增加停止词，这一项有官方兼容页保证。 |
| enable_thinking | 论文没有给出 DashScope thinking 开关，但当前适配必须确认其是否改变 Qwen3 语义。 | 兼容页参数表未列出 `enable_thinking` 或 `thinking_budget`。 | 原生 DashScope 参数表明确支持 `enable_thinking`，并说明返回 `reasoning_content`。 | 当前 IFBench wrapper 默认 `enable_thinking=false`，AIME Qwen3 配置同样固定为 false。 | 仅原生页明确 | 兼容页未正式承诺这一能力；如果 OpenAI-compatible 后端接受该字段，也应视作需要额外实调证明的扩展行为。 |
| reasoning_content / reasoning_tokens | 如果 thinking 被打开，需要确认响应中是否有可观测字段。 | 兼容页响应参数表未列出 `reasoning_content`。 | 原生 DashScope 响应对象明确列出 `reasoning_content` 与 `reasoning_tokens`。 | 当前 IFBench wrapper 关闭 thinking，因此没有依赖这些字段。 | 仅原生页明确 | 这进一步说明 compatible-mode 与原生 API 的可观测面不应直接视为等价。 |

## 最小实调结果

| probe | 目的 | 结果 | finish_reason | reasoning_content | 错误 |
| --- | --- | --- | --- | --- | --- |
| baseline_ok | 最小成功请求，验证 compatible-mode 基础链路。 | 成功 | stop | - | - |
| top_k_extra_body | 按当前 IFBench wrapper 的做法，经 `extra_body.top_k=20` 传入。 | 成功 | stop | - | - |
| stop_string | 验证 compatible-mode 是否接受 `stop` 字符串。 | 成功 | stop | - | - |
| enable_thinking_extra_body | 经 `extra_body.enable_thinking=true` 传入，观察是否报错或返回 reasoning 字段。 | 失败 | - | - | BadRequestError: Error code: 400 - {'error': {'message': 'parameter.enable_thinking only support stream call', 'type': 'invalid_request_error', 'param': None, 'code': 'invalid_parameter_error'}, 'id': 'chatcmpl-7584d7fd-349b-90dc-9785-332361d7ec60', 'request_id': '7584d7fd-349b-90dc-9785-332361d7ec60'} |
| max_tokens_16384_acceptance | 只检查服务端是否接受 `max_tokens=16384` 这个参数值，不把成功误写成真实上限已证实。 | 失败 | - | - | BadRequestError: Error code: 400 - {'error': {'message': '<400> InternalError.Algo.InvalidParameter: Range of max_tokens should be [1, 8192]', 'type': 'invalid_request_error', 'param': None, 'code': 'invalid_parameter_error'}, 'id': 'chatcmpl-449c1b1a-62f8-9353-9156-dc39db866e63', 'request_id': '449c1b1a-62f8-9353-9156-dc39db866e63'} |

补充说明：
- `baseline_ok` 返回内容：`OK`
- `baseline_ok` usage：`{"completion_tokens":1,"prompt_tokens":16,"total_tokens":17,"completion_tokens_details":null,"prompt_tokens_details":null}`
- `top_k_extra_body` 返回内容：`OK`
- `top_k_extra_body` usage：`{"completion_tokens":1,"prompt_tokens":16,"total_tokens":17,"completion_tokens_details":null,"prompt_tokens_details":null}`
- `stop_string` 返回内容：`OK`
- `stop_string` usage：`{"completion_tokens":2,"prompt_tokens":18,"total_tokens":20,"completion_tokens_details":null,"prompt_tokens_details":null}`

## 当前判定

- `temperature=0.6`、`top_p=0.95`、`stop`：可视为有官方 compatible-mode 文档支撑的映射项。
- `top_k=20`：当前仓库在用，但更接近“SDK/原生页暗示可用，兼容页未正式承诺”。
- `enable_thinking`：当前应继续默认关闭；若未来要打开，必须以实调结果而非推断为准。
- `max_tokens=16384`：论文 strict 目标仍未闭环。当前仓库继续保守使用 `8192` 是合理防御性选择。

## 下一步建议

1. 先在本机安全设置环境变量，例如 `setx QWEN_API_KEY <value>` 或仅在当前 shell 临时导出，然后运行：

```powershell
python scripts/probe_ifbench_dashscope_compatibility.py --execute
```

2. 如果 `top_k_extra_body` 或 `enable_thinking_extra_body` 失败，应把 IFBench wrapper 明确降级为“只依赖兼容页正式参数”的实现。
3. 如果 `max_tokens_16384_acceptance` 失败，则论文 strict reproduction 在当前 DashScope 路径上可直接判定为后端不等价。
4. 在真实 probe 完成前，不启动正式 IFBench Baseline / GEPA 大预算 run。

## 资料来源

- OpenAI Python SDK：[https://github.com/openai/openai-python/blob/main/src/openai/resources/chat/completions/completions.py](https://github.com/openai/openai-python/blob/main/src/openai/resources/chat/completions/completions.py)
- 阿里云 OpenAI-compatible 文档：[https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)
- 阿里云 DashScope 原生文档：[https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-dashscope](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-dashscope)
- 阿里云模型列表：[https://www.alibabacloud.com/help/en/model-studio/models](https://www.alibabacloud.com/help/en/model-studio/models)
