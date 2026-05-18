# strict official path 设计方案

## 目标

在不改 `GEPA` 核心算法、不改 evaluator、不碰 `temperature`、不跑 `official_budget` 的前提下，把当前 `scripts/06_minimal_official_path_sanity.py` 继续压薄到接近下面语义：

```python
from gepa.examples.aime import init_dataset
import gepa

trainset, valset, testset = init_dataset()

result = gepa.optimize(...)
```

## 对 `06` 脚本的现状判断

当前 `scripts/06_minimal_official_path_sanity.py` 已经比 wrapper 薄，但仍残留以下 wrapper 成分：

1. 依赖 `src.config.ExperimentConfig`
2. 依赖本地 `src.gepa_official_runner.SEED_PROMPT`
3. 依赖 `load_dataset_via_direct_official_path()` 这一层包装
4. 依赖快照与 notes 落盘逻辑
5. 仍把 `temperature_task / temperature_reflection` 记录进输出

这些东西大多不改变 `gepa.optimize()` 核心输入语义，但它们会让脚本更像“审计工具”，而不是“极薄 strict path”。

## strict official path 应保留什么

### 必须保留

1. `from gepa.examples.aime import init_dataset`
2. `import gepa`
3. 官方 `seed_candidate`
4. `trainset / valset`
5. `task_lm="openai/<task_model>"`
6. `reflection_lm="openai/<reflection_model>"`
7. `max_metric_calls`
8. `seed`
9. `run_dir`
10. DeepSeek 的最小 OpenAI-compatible 环境桥接

### 必须删除

1. preflight probe
2. introspection fallback
3. 自定义 adapter
4. 自定义 evaluator
5. saved prompt eval
6. callable 模型注入
7. `temperature` 接线
8. manifest / package_versions / raw_result / stdout/stderr 等重审计壳层

## strict official path 的建议结构

### 建议输入来源

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_API_BASE`
- `TASK_MODEL`
- `REFLECTION_MODEL`
- CLI 参数：
  - `--max-metric-calls`
  - `--seed`
  - `--run-dir`

理由：

- 这比复用 `src.config` 更薄
- 仍足够支撑 `GEPA method-level reproduction with DeepSeek backend`
- 不会引入新的方法偏差

### 建议脚本骨架

1. 直接导入 `init_dataset`
2. 本地定义 exact seed prompt 常量
3. 读取环境变量和少量 CLI 参数
4. `trainset, valset, testset = init_dataset()`
5. 进入最小环境桥接
6. 直接调用 `gepa.optimize(...)`
7. 只落一个极小结果文件，例如 `strict_result_summary.json`

## 关于 seed prompt 的处理

strict path 不应继续导入：

- `src.gepa_official_runner.SEED_PROMPT`

原因：

- 该常量当前只是 quickstart 语义等价版本
- strict path 的核心任务之一就是摆脱这层本地语义替代

strict path 应改为：

- 直接在脚本内固定“closest exact official AIME optimization test prompt”
- 并在文件头注释中写明来源链接和 commit

## 关于 DeepSeek 环境桥接

strict path 仍然需要 DeepSeek 的 OpenAI-compatible 环境桥接，否则无法保持当前项目身份：

- `GEPA method-level reproduction with DeepSeek backend`

但桥接应收缩为：

- 仅做环境变量注入
- 不做探活
- 不做模型替换
- 不做额外 fallback

## 关于输出

strict path 的目标不是完全无输出，而是：

- 只保留最小可核验输出

建议最小输出：

1. `strict_result_summary.json`
2. 可选 `strict_seed_prompt.json`

不建议在 strict path 中继续保留：

1. `manifest.json`
2. `config_resolved.yaml`
3. `notes.md`
4. `package_versions.txt`
5. `stdout.log`
6. `stderr.log`
7. `raw_result.json`

## 与现有文件的关系

- `src/gepa_official_runner.py`：继续作为 wrapper path 保留
- `scripts/06_minimal_official_path_sanity.py`：继续作为“最小一致性快照/干跑工具”保留
- 新的 strict path：单独存在，用来证明“即便完全去掉外壳，核心官方语义仍能跑通”

## 最终建议

最稳妥的收敛方式不是改写 wrapper，而是：

1. 保留 wrapper path
2. 保留 `06` 号最小一致性校验
3. 单独建立一个真正极薄的 strict official path

这样三者边界清晰：

- wrapper：工程化运行与审计
- minimal sanity：核心 kwargs 对照
- strict：最薄官方语义路径
