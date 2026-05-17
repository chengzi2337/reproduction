# Temperature Control Audit

## 审计范围

本审计只回答当前安装的 `GEPA` 包在温度控制上的真实行为，不修改实验代码路径，不重跑 `smoke / pilot`，也不运行 `official_budget`。

审计依据仅来自：

- 当前安装包的 `introspection`
- 当前安装包源码检查
- 当前仓库中的现有调用路径

## Stage 1 Context

- 当前项目是 `GEPA method-level reproduction with DeepSeek backend`
- 当前项目不是 `original same-model reproduction`
- 当前项目不是 `paper-level final conclusion`
- `official_budget` 尚未运行
- 当前 Stage 1 采用 `方案 A`：
  - 保持官方字符串路径
  - `temperature not explicitly controlled`
  - Stage 1 当前不因 temperature 问题重跑 `smoke / pilot`
- 下一步仍是 `pilot saved prompt eval`
- 参见：
  - `reports/stage1_deepseek_method_reproduction_report.md`
  - `reports/official_core_path_comparison.md`
  - `reports/stage1_final_status.md`

## 1. 当前安装的 GEPA API 检查结果

### 1.1 `gepa.optimize()` 签名

当前安装包中，`gepa.optimize()` 的签名为：

```python
(seed_candidate: dict[str, str],
 trainset,
 valset=None,
 adapter=None,
 task_lm: str | ChatCompletionCallable | None = None,
 evaluator=None,
 reflection_lm: LanguageModel | str | None = None,
 ...,
 max_metric_calls: int | None = None,
 ...,
 seed: int = 0,
 ...)
```

结论：

- `gepa.optimize()` **没有** `temperature_task`
- `gepa.optimize()` **没有** `temperature_reflection`
- `gepa.optimize()` **没有**通用的 `task_model_kwargs` / `reflection_model_kwargs`
- 因此，当前官方 `optimize()` 默认参数层面**不能直接显式控制温度**

### 1.2 `task_lm` 支持类型

当前安装包中，`task_lm` 的类型为：

```python
str | ChatCompletionCallable | None
```

其中 `ChatCompletionCallable` 协议为：

```python
def __call__(self, messages: Sequence[ChatMessage]) -> str
```

结论：

- `task_lm` 官方支持两类：
  - 字符串模型名
  - 满足 `messages -> str` 协议的 callable
- 当前默认官方路径是：
  - `adapter is None`
  - `task_lm` 为字符串
  - `optimize()` 内部构造 `DefaultAdapter(model=task_lm, evaluator=evaluator)`

### 1.3 `reflection_lm` 支持类型

当前安装包中，`reflection_lm` 的类型为：

```python
LanguageModel | str | None
```

其中 `LanguageModel` 协议为：

```python
def __call__(self, prompt: str) -> str
```

并且当前 `optimize()` 内部在收到字符串 `reflection_lm` 时，会转成：

```python
def _reflection_lm(prompt: str) -> str:
    completion = litellm.completion(
        model=reflection_lm_name,
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content
```

结论：

- `reflection_lm` 官方支持：
  - 字符串模型名
  - 满足 `prompt -> str` 协议的对象 / callable
- 当前字符串默认路径中，`litellm.completion(...)` **没有显式传入 temperature**

### 1.4 是否支持传入 `dspy.LM` 对象

本地 `dspy.LM` 的关键签名是：

```python
LM.__init__(..., temperature: float | None = None, ...)
LM.__call__(self, prompt: str | None = None, messages: list[dict[str, Any]] | None = None, **kwargs) -> list[dict[str, Any] | str]
```

结论：

- `dspy.LM` **不是** `ChatCompletionCallable` 的直接等价实现  
  因为 `ChatCompletionCallable` 期望返回 `str`，而 `dspy.LM.__call__()` 返回的是 `list[...]`
- `dspy.LM` 也**不是** `LanguageModel(prompt: str) -> str` 的直接等价实现  
  因为其返回值不是单个 `str`
- 所以：**不能安全地把 `dspy.LM` 直接塞进当前 `task_lm` / `reflection_lm` 默认路径里，除非再包一层自定义适配**

### 1.5 如果传对象，是否仍然使用 `DefaultAdapter` 和 batch evaluate

`DefaultAdapter.evaluate()` 的关键逻辑是：

```python
if isinstance(self.model, str):
    responses = self.litellm.batch_completion(...)
else:
    responses = [self.model(messages) for messages in litellm_requests]
```

结论：

- 只有 `model` 为字符串时，`DefaultAdapter` 才走官方 `litellm.batch_completion(...)` 批量路径
- 如果传的是 callable / 对象，则会退化成：

```python
[self.model(messages) for messages in litellm_requests]
```

- 这意味着：
  - 仍然是 `DefaultAdapter`
  - 但**不再是字符串模型路径下的官方 batch 路径**
  - 因而会重新引入我们之前已经修掉的“自写 callable / 串行路径偏差”

### 1.6 官方 AIME example 是否显式设置 temperature

当前安装包中的 `gepa.examples.aime` 只包含：

- `load_dataset(...)`
- `random.Random(0).shuffle(train_split)`
- `trainset / valset / testset` 切分

没有任何：

- `temperature=...`
- `LM(...)`
- `DefaultAdapter(..., litellm_batch_completion_kwargs=...)`

结论：

- **官方 AIME example 没有显式设置 temperature**

## 2. 当前配置中的 temperature 是否真实生效

当前仓库中：

- [src/config.py](C:/Users/lin/Documents/New project 2/src/config.py) 会读取
  - `temperature_task`
  - `temperature_reflection`
- [src/gepa_official_runner.py](C:/Users/lin/Documents/New project 2/src/gepa_official_runner.py) 会把它们写入 `config_resolved.yaml`

但当前实际调用路径中：

- `task_lm` 是字符串模型名
- `reflection_lm` 是字符串模型名
- `gepa.optimize()` 默认创建 `DefaultAdapter(model=task_lm, evaluator=evaluator)`
- 没有任何地方把 `temperature_task / temperature_reflection` 传入 `DefaultAdapter` 或 `litellm.completion(...)`

结论：

> 当前 `temperature_task / temperature_reflection` **没有被显式接入模型调用路径，因此不能认为它们当前真实生效。**

更谨慎地说：

> Stage 1 当前 `temperature is not explicitly controlled unless GEPA default path applies it internally`。

而基于当前安装包源码检查：

- 对 `task_lm` 默认字符串路径，没有看到温度被内部显式注入
- 对 `reflection_lm` 默认字符串路径，也没有看到温度被内部显式注入

因此当前最合理的工程判断是：

> **当前 temperature 未被显式控制。**

## 3. 如果 temperature 不生效，会影响什么

会影响两类东西：

### 3.1 对实验结论的影响

- 当前不能声称：
  - `temperature_task=0.0` 已被严格控制
  - `temperature_reflection=0.7` 已被严格控制
- 因而不能把当前 `smoke / pilot` 结果解释成“在这些温度条件下”的严格结论

### 3.2 对可复现性的影响

- 其他人按照当前 README / config 直觉，可能会误以为温度已经受控
- 但实际上当前结果更接近：
  - `temperature recorded in config, but not explicitly wired into current GEPA default path`

## 4. 这是否偏离 GEPA 官方默认行为

需要区分两个层次：

### 4.1 相对官方 AIME example

- **不算偏离**  
因为官方 AIME example 本身也没有显式设置 temperature

### 4.2 相对“我们自己的配置声明”

- **算偏离**

因为当前仓库对外暴露了：

- `temperature_task`
- `temperature_reflection`

这会让读者自然理解为：

- 这两个配置会控制实验

但实际没有接入当前调用路径，所以这和当前配置语义不一致。

## 5. 官方兼容的修法有哪些

### 方案 A：保持官方字符串路径，明确声明 temperature uncontrolled

做法：

- 保持当前：
  - `task_lm = "openai/<model>"`
  - `reflection_lm = "openai/<model>"`
  - `adapter is None`
  - `gepa.optimize()` 默认创建 `DefaultAdapter`
- 只修正文档表述，明确说明：
  - 当前 Stage 1 `temperature is not explicitly controlled`

优点：

- 最接近当前官方默认调用路径
- 不重新引入 callable 偏差
- 不需要立刻重跑 `smoke / pilot`

缺点：

- 无法把 Stage 1 结果解释为温度受控实验

### 方案 B：接入 temperature，并重跑 smoke / pilot

如果要真正控制温度，需要至少分别处理 task 和 reflection 两侧：

#### B1. task 侧

官方兼容做法是：

- 不依赖 `optimize(adapter=None, task_lm=...)` 默认创建的 `DefaultAdapter`
- 改为**显式实例化官方 `DefaultAdapter`**

例如理论上可行的方向是：

```python
DefaultAdapter(
    model="openai/<task_model>",
    evaluator=...,
    litellm_batch_completion_kwargs={"temperature": temperature_task},
)
```

然后把这个 adapter 传给 `gepa.optimize(adapter=...)`

优点：

- 仍然使用官方 `DefaultAdapter`
- task 侧仍可保持 batch evaluate

代价：

- 不再是 `optimize(adapter=None, task_lm=...)` 的最默认路径

#### B2. reflection 侧

当前 `reflection_lm` 的字符串默认路径没有显式 temperature 参数。

若要控制 reflection temperature，通常必须传：

- 自定义 `LanguageModel` 对象 / callable

例如内部再调 `litellm.completion(..., temperature=...)`

代价：

- 这会重新引入**自定义 callable 偏差**

## 6. 哪些修法会重新引入自写 callable 偏差

以下修法会重新引入偏差：

1. 把 `task_lm` 改成自写 callable
   - 会让 `DefaultAdapter` 从字符串 batch 路径退回到逐调用路径

2. 把 `reflection_lm` 改成自写 callable / 自定义 `LanguageModel`
   - 虽然 GEPA 官方类型允许这样做
   - 但它不再是官方字符串默认路径

3. 直接把 `dspy.LM` 塞进 `task_lm` / `reflection_lm`
   - 当前不属于安全直连路径
   - 仍需要额外包装层

## 7. 推荐方案

当前我建议采用：

## 方案 A

即：

> 保持当前官方字符串路径，但明确声明 `temperature uncontrolled`。

原因：

1. 当前 Stage 1 目标还是方法级基线，不是论文最终实验
2. 方案 A 不会重新引入 callable 偏差
3. 方案 B 一旦要真正控制 reflection temperature，几乎必然要引入新的自定义对象路径
4. 在没有先明确设计“如何控制温度且仍尽量贴近官方路径”之前，贸然改调用更容易污染对照基线

## 8. 是否需要重跑 smoke / pilot

### 如果采用方案 A

- **当前不需要重跑** `smoke / pilot`
- 只需要修正文档，明确：
  - 当前温度未显式受控

### 如果采用方案 B

- **必须重跑** `smoke / pilot`

因为：

- task / reflection 的调用语义将发生变化
- 这已经不再是和当前 Stage 1 结果同一条件下的实验

## 9. 最终结论

- 当前 `temperature_task / temperature_reflection` **未被显式接入 GEPA 当前默认调用路径**
- 这**不偏离**官方 AIME example 的默认行为
- 但它**偏离了我们当前配置字段给人的直觉语义**
- 当前最稳妥的做法是：
  - 采用 **方案 A**
  - 明确写出 `temperature is not explicitly controlled`
  - 暂不重跑 `smoke / pilot`
  - 先把 Stage 1 基线的偏差声明写清楚
