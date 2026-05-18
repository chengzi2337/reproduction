# exact seed prompt 溯源结果

## 结论先行

当前能找到的、与 `AIME` 优化实验**最接近**的 `exact seed prompt`，不是本仓库 `src/gepa_official_runner.py` 里的语义等价版本，而是官方仓库 AIME 优化测试文件中的这条：

```python
{"system_prompt": "You are a helpful assistant. You are given a question and you need to answer it. The answer should be given at the end of your response in exactly the format '### '"}
```

我把它判定为当前最优先的可核验来源，原因是它直接出现在官方 `AIME` prompt optimization 测试上下文里，而不是面向 quickstart 的示例文案。

## 来源分级

### A. 当前官方仓库中最接近 AIME 实验的 exact seed prompt

- 来源：`gepa-ai/gepa`
- 版本/上下文：commit `ff60b615f2c99044a81d626717f56d80e93ce60d`
- 文件：`tests/test_aime_prompt_optimization/test_aime_prompt_optimize.py`
- 证据链接：
  - <https://raw.githubusercontent.com/gepa-ai/gepa/ff60b615f2c99044a81d626717f56d80e93ce60d/tests/test_aime_prompt_optimization/test_aime_prompt_optimize.py>
- 上下文说明：
  - 同一文件中直接出现 `trainset, valset, _ = gepa.examples.aime.init_dataset()`
  - 同一文件中直接调用 `gepa.optimize(...)`
  - 因此它比 README quickstart 更贴近真实 `AIME` 优化测试语义

### B. 历史官方示例中的同一 exact seed prompt

- 来源：`CerebrasResearch/gepa`
- 版本/上下文：commit `38b15abf3b58a09684c16fa2b805d4a4d9f89e5b`
- 文件：`tests/test_aime_prompt_optimization/test_aime_prompt_optimize.py`
- 证据链接：
  - <https://raw.githubusercontent.com/CerebrasResearch/gepa/38b15abf3b58a09684c16fa2b805d4a4d9f89e5b/tests/test_aime_prompt_optimization/test_aime_prompt_optimize.py>
- 结论：
  - 与当前官方测试文件中的 prompt 文本一致
  - 说明该 prompt 不是临时拼接，而是有历史连续性的官方测试示例

### C. 当前官方 quickstart 的 prompt

- 来源：`gepa-ai/gepa`
- 版本/上下文：当前 `main` 的 README quickstart，Context7 指向 `https://github.com/gepa-ai/gepa/blob/main/README.md`
- 证据链接：
  - <https://github.com/gepa-ai/gepa/blob/main/README.md>
- 当前 quickstart 文本：

```python
{"system_prompt": "You are a helpful assistant. Answer the question. Put your final answer in the format '### <answer>'"}
```

- 结论：
  - 这是当前官方文档公开展示的 quickstart seed prompt
  - 但它不是我判定的“最接近 AIME 实验”的最高优先级来源，因为它更像面向文档读者的简化示例

## 与本仓库当前 prompt 的关系

本仓库当前 `src/gepa_official_runner.py` 中的 `SEED_PROMPT` 是：

```python
{"system_prompt": "You are a helpful assistant. Answer the question. Put your final answer in the format '### <answer>'"}
```

因此：

- 它和**当前官方 quickstart**一致
- 它和**当前官方 AIME 测试文件**不一致
- 它更准确地应被标注为：
  - `current official README quickstart prompt`
  - 不是：
  - `current closest exact AIME optimization test prompt`

## 论文与附带材料检索结果

### paper / arXiv

- 检索对象：`arXiv 2507.19457`
- 检索结果：
  - 未找到比官方测试文件更直接的 exact AIME seed prompt 原文

### artifact repo

- 检索对象：`gepa-ai/gepa-artifact`
- 检索结果：
  - 搜到了 `AIME` 数据与实验配置相关文件
  - 未在代码搜索中找到更高优先级的 `seed_prompt` / `system_prompt` 原文

## 最终判定

### 本窗口应采用的 exact seed prompt 结论

- **已找到**当前最接近 `AIME` 优化实验的可核验 exact seed prompt
- 它来自：
  - 当前官方仓库 `gepa-ai/gepa` 的 AIME 优化测试文件
- 它的历史连续性来自：
  - `CerebrasResearch/gepa` 的同名测试文件

### 严格表述

- `README quickstart prompt`：已找到
- `closest exact official AIME optimization test prompt`：已找到
- `paper / artifact 中更高优先级的 exact official seed prompt`：**未找到**
