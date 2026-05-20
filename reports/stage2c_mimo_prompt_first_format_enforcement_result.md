# Stage 2C MiMo Prompt-First / Format-Enforcement Diagnostic Result

## 定位

本结果只属于：

- `Stage 2C prompt-first / format-enforcement diagnostic`
- `non-strict`
- `not baseline`
- `not performance claim`
- `not directly comparable to prior Stage 2C smoke`

本轮：

- 不调用 `gepa.optimize()`
- 不进入 smoke rerun
- 不进入 pilot

## 运行范围

- provider：`mimo`
- model：`mimo-v2.5-pro`
- api_base：`https://token-plan-cn.xiaomimimo.com/v1`
- thinking：`disabled`
- max_completion_tokens：`2048`
- timeout：`120`
- sample_count：`3`
- 诊断链路：
  - direct OpenAI SDK
  - LiteLLM `openai/mimo-v2.5-pro`

## Prompt 变体

- Variant A：`answer-only`
- Variant B：`first-line final answer`
- Variant C：`current README quickstart prompt`

## 本地输出

- 输出目录：
  - `outputs/stage2c_mimo_prompt_first_format_enforcement_diagnostic/20260520T185238+0800/`
- 关键文件：
  - `stage2c_prompt_first_input_snapshot.json`
  - `stage2c_prompt_first_results.json`

## 结果摘要

### Variant A：answer-only

- direct SDK：
  - 精确 `### <integer>`：`1 / 3`
  - 首行精确 `### <integer>`：`0 / 3`
  - `### Step 1` 类中间标题：`2 / 3`
  - `finish_reason = length`：`2 / 3`
- LiteLLM：
  - 精确 `### <integer>`：`2 / 3`
  - 首行精确 `### <integer>`：`0 / 3`
  - `### Step 1` 类中间标题：`0 / 3`
  - `finish_reason = length`：`0 / 3`

### Variant B：first-line final answer

- direct SDK：
  - 精确 `### <integer>`：`1 / 3`
  - 首行精确 `### <integer>`：`0 / 3`
  - `### Step 1` 类中间标题：`0 / 3`
  - `finish_reason = length`：`0 / 3`
- LiteLLM：
  - 精确 `### <integer>`：`0 / 3`
  - 首行精确 `### <integer>`：`0 / 3`
  - `### Step 1` 类中间标题：`1 / 3`
  - `finish_reason = length`：`2 / 3`

### Variant C：README quickstart 对照

- direct SDK：
  - 精确 `### <integer>`：`0 / 3`
  - 首行精确 `### <integer>`：`0 / 3`
  - `### Step 1` 类中间标题：`1 / 3`
  - `finish_reason = length`：`3 / 3`
- LiteLLM：
  - 精确 `### <integer>`：`1 / 3`
  - 首行精确 `### <integer>`：`0 / 3`
  - `### Step 1` 类中间标题：`1 / 3`
  - `finish_reason = length`：`2 / 3`

## 关键观察

1. `2048` 相比 `512` 已明显缓解硬截断，但没有解决最终答案格式可达性。
2. 三个 prompt 变体都没有达到“`3/3` 样本稳定输出首行精确 `### <integer>`”的通过标准。
3. Variant A 在 LiteLLM 路径上最接近目标，但仍然出现：
   - 结果不是首行最终答案
   - direct SDK 仍有 `length`
   - direct SDK 仍把 `###` 用成中间标题
4. Variant B 会出现新的格式漂移：
   - `### <answer>` 被当成 XML 风格包装或模板提示的一部分
   - 并没有稳定转成 evaluator 需要的精确 `### <integer>`
5. Variant C 仍然是最弱对照，说明当前 README quickstart prompt 在 Stage 2C 条件下不适合作为 format-enforced rerun 的直接基础。

## 结论

当前最准确的结论是：

> Stage 2C 当前已经从“能不能跑完”推进到“输出能不能被 evaluator 正确计分”。  
> 在 `thinking.disabled + max_completion_tokens = 2048` 的 controlled-generation 条件下，MiMo 可以产生非空正文，但三种 prompt 变体都还不能稳定满足 evaluator 需要的精确 `### <integer>`。  
> 因此当前主 blocker 仍然是 `format_missing`，而不是单纯的 `truncated_before_final`。

## 当前不应做的事

- 不进入 pilot
- 不直接重跑 format-enforced smoke
- 不把本轮结果写成 baseline 或性能结论
- 不把任一 prompt 变体写成“已经稳定可用于 evaluator”

## 下一步建议

- 先封存本结果 checkpoint
- 再设计下一轮更强约束的格式诊断，而不是直接进入 Stage 2C smoke rerun
