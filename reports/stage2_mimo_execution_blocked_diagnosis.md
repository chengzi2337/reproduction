# Stage 2 MiMo execution blocked diagnosis

## 定位

- 本文档只讨论 `Stage 2: Xiaomi MiMo backend-substitution experiment`
- 当前项目整体仍然是 `GEPA method-level reproduction`
- 本文档不是 `original same-model reproduction` 结论
- 本文档不是 Stage 1 DeepSeek 历史结果改写

## 当前状态修正

之前的 blocked 诊断里，有两条判断现在需要修正：

1. `401 Invalid API Key` 不能再作为“tp-key 无效”的证据
2. “MiMo completion 普遍不可达”也不能作为总括结论

新的诊断结果表明，当前问题是**路径分裂**，而不是单一的 provider 故障。

## 官方边界

- MiMo 路径仍然只定义为 `Stage 2: Xiaomi MiMo backend-substitution experiment`
- 不修改 `GEPA optimizer`
- 不修改 `gepa.examples.aime.init_dataset()`
- 不修改默认 evaluator
- 不引入自定义 adapter
- 不引入 callable 替代官方字符串模型路径

## 为什么之前会误判 key 无效

你截图对应的是 `Token Plan` 页面，页面明确给出了：

- 专属 API Key
- OpenAI-compatible Base URL：
  - `https://token-plan-cn.xiaomimimo.com/v1`

从本轮复核结果看，之前那次 `401 Invalid API Key` 来自一条构造有问题的 WSL `curl` 命令。那次命令的引号层级有误，导致认证头没有被可靠地送达服务端，因此不能据此推断 key 真无效。

## 新的分诊结果

### 1. Windows / PowerShell 直连路径

对同一个 endpoint 做 `curl -v`：

- DNS 解析成功
- 多个 IPv4 地址都在 `443` 建连阶段失败
- 报错是 `Could not connect to server`

这说明 Windows 当前直连路径的问题是：

- 还没到 TLS
- 还没到 HTTP
- 还没到认证层

而是更早的 TCP 连接建立阶段失败。

### 2. `Ubuntu-22.04-Fresh` / WSL 代理路径

WSL 环境下通过本地代理路径重新做最小 POST 请求，结果是：

- 可以到达 `token-plan-cn.xiaomimimo.com`
- 可以完成 TLS 握手
- 可以拿到真实 HTTP 响应
- 同一把 `tp-...` key 在正确请求下返回 `HTTP 200`

因此可以确认：

- `tp-...` key 是有效的
- MiMo OpenAI-compatible endpoint 不是整体不可用
- 之前的 `401` 不是 key 本身问题

## 受控生成路径的新结果

### 1. WSL direct SDK 最小 probe

在 `Ubuntu-22.04-Fresh` 中，使用最小 completion 请求：

- `model = mimo-v2.5-pro`
- `messages = [{"role":"user","content":"Return exactly: OK"}]`
- `max_completion_tokens = 16`

结果：

- `HTTP 200`
- `finish_reason = length`
- `content = ""`
- `reasoning_content` 非空

这说明默认生成策略下，MiMo 会优先产出 reasoning，而不是立即给出最终 `content`。

### 2. WSL direct SDK AIME 单样本

在同一条可达路径上，使用：

- README quickstart seed prompt
- AIME 第一个 val 样本
- `thinking.disabled`
- `max_completion_tokens = 512`

结果：

- `HTTP 200`
- `content` 非空
- `reasoning_tokens = 0`
- `finish_reason = length`

这说明在受控生成参数下，MiMo 已经可以返回真实 AIME 单样本的正文内容。

### 3. Windows + 本地代理 + LiteLLM

在 Windows Python 中显式设置：

- `HTTPS_PROXY=http://127.0.0.1:10808`
- `HTTP_PROXY=http://127.0.0.1:10808`

然后使用：

- `litellm.completion(model="openai/mimo-v2.5-pro")`
- 最小 `OK` probe
- AIME 单样本，`thinking.disabled + max_completion_tokens=512`

结果：

- 最小 `OK` probe 成功返回 `content = "OK"`
- AIME 单样本成功返回非空 `content`

这说明 `LiteLLM openai/<model>` 路径在代理可达条件下也可以跑通受控生成参数。

## 当前最准确的结论

当前实际上存在两条不同的执行路径：

1. **Windows 直连路径**
   - 到 `token-plan-cn` 的 TCP 连接建立失败
   - 因此在这条路径上，Python SDK / LiteLLM 会表现为 `APIConnectionError`

2. **代理可达路径**
   - endpoint 可达
   - `tp-...` key 有效
   - direct SDK 可跑通受控 AIME 单样本
   - LiteLLM `openai/<model>` 也可跑通受控 AIME 单样本

因此当前不能再写成：

- “MiMo key 无效”
- “MiMo endpoint 整体故障”
- “MiMo 不适合 AIME”

更准确的表述应是：

> The current local environment shows a split-path setup for the MiMo token-plan-cn completion gateway: Windows direct connectivity fails before TCP establishment, but the proxy-backed path is healthy, the tp-key is valid, and both direct SDK and LiteLLM can return content for a controlled AIME single-sample request.

## 对 Stage 2 的含义

### strict default path

- 仍然不能和受控生成路径混写
- 当前还没有在稳定可达路径上完成 strict execute sanity
- 因此 strict default path 仍未完成

### Stage 2B: MiMo controlled-generation diagnostic path

这一条现在已经具备成立条件：

- direct SDK：已通
- LiteLLM `openai/<model>`：已通
- AIME 单样本：已通

但必须明确写清楚：

- 该路径显式传入了 `thinking.disabled`
- 该路径显式限制了 `max_completion_tokens`
- 它不是 strict official path
- 它只能作为诊断性 / 工程适配路径存在

## 当前边界

- 现在不要把这条受控生成路径写成 strict official path
- 现在不要回写 Stage 1 DeepSeek 历史结论
- 现在不要把 MiMo 结果写成 original GEPA same-model reproduction
- 现在不要在 Windows 直连路径上继续做 MiMo GEPA smoke

## 下一步建议

最合理的下一步是二选一：

1. **继续诊断路径**
   - 固化一条 `Stage 2B controlled-generation` 文档与脚本说明
   - 只在代理可达路径上验证 direct SDK / LiteLLM / AIME 单样本

2. **回到 strict 语义问题**
   - 不跑 smoke
   - 先明确：如果必须显式 `thinking.disabled + token cap` 才能跑通，那它就不能再叫 strict default path
