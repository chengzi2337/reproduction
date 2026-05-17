## 项目上下文摘要（gepa-deepseek-stage1）

生成时间：2026-05-16 23:05:00 +0800

### 1. 相似实现分析

- **实现1**: [src/config.py](C:/Users/lin/Documents/New project 2/src/config.py)
  - 模式：`dataclass + YAML + 环境变量覆盖` 的配置解析
  - 可复用：`_resolve_env_reference`、`_pick_config_or_env`、`load_experiment_config`
  - 需注意：模型名必须来自 YAML 或环境变量，且 `allow_model_substitution=false`
- **实现2**: [src/gepa_official_runner.py](C:/Users/lin/Documents/New project 2/src/gepa_official_runner.py)
  - 模式：官方 AIME 数据入口发现、run 目录初始化、manifest 落盘、官方 `gepa.optimize()` 调用
  - 可复用：`SEED_PROMPT`、`load_official_aime_dataset`、run artifact 写入流程
  - 需注意：现在必须直接传字符串模型名给 `task_lm` / `reflection_lm`，不能再传自写 callable
- **实现3**: [src/eval_utils.py](C:/Users/lin/Documents/New project 2/src/eval_utils.py)
  - 模式：读取保存的 prompt，然后用 GEPA `DefaultAdapter` 做逐样本评估并落盘 JSONL
  - 可复用：`load_prompt_candidate`、`evaluate_candidate`、`write_jsonl`
  - 需注意：评估也必须沿用 `DefaultAdapter(model=字符串模型名)` 的官方路径
- **实现4**: 已安装包 `gepa.examples.aime`
  - 模式：官方 AIME 数据入口 `init_dataset()`
  - 可复用：直接调用 `trainset, valset, testset = init_dataset()`
  - 需注意：如果未来 GEPA 版本改动入口，需要保留 introspection 回退定位，而不是改 GEPA 源码

### 2. 项目约定

- **命名约定**：Python 模块与脚本采用蛇形命名；配置字段使用小写下划线
- **文件组织**：`configs/` 放实验 YAML，`scripts/` 放 CLI，`src/` 放实现，`tests/` 放 pytest
- **导入顺序**：标准库、第三方、本地模块三段式
- **代码风格**：`Path`、类型注解、UTF-8、少量高价值注释、JSON/YAML 落盘

### 3. 可复用组件清单

- [src/config.py](C:/Users/lin/Documents/New project 2/src/config.py)：YAML 解析、环境变量展开、输出目录解析
- [src/logging_utils.py](C:/Users/lin/Documents/New project 2/src/logging_utils.py)：manifest、package versions、stdout/stderr 捕获、run 目录
- [src/gepa_official_runner.py](C:/Users/lin/Documents/New project 2/src/gepa_official_runner.py)：官方 AIME 数据入口与优化运行骨架
- [src/eval_utils.py](C:/Users/lin/Documents/New project 2/src/eval_utils.py)：保存 prompt 的读取、评估与 JSONL 落盘
- [src/deepseek_utils.py](C:/Users/lin/Documents/New project 2/src/deepseek_utils.py)：OpenAI SDK 探活、LiteLLM 字符串模型名构造、OpenAI-compatible 环境桥接

### 4. 测试策略

- **测试框架**：pytest
- **测试模式**：配置加载、防泄漏、模型配置化约束、官方字符串模型路径约束
- **参考文件**：[tests/test_config.py](C:/Users/lin/Documents/New project 2/tests/test_config.py)、[tests/test_model_configurable.py](C:/Users/lin/Documents/New project 2/tests/test_model_configurable.py)、[tests/test_no_secret_leak.py](C:/Users/lin/Documents/New project 2/tests/test_no_secret_leak.py)
- **覆盖要求**：正常配置加载、环境变量解析、禁止自动替换模型、输出无密钥泄露、禁止回退到 callable 路径

### 5. 依赖和集成点

- **外部依赖**：`gepa`、`dspy`、`litellm`、`openai`、`datasets`
- **内部依赖**：`scripts/* -> src/config.py -> src/deepseek_utils.py / src/gepa_official_runner.py / src/eval_utils.py`
- **集成方式**：
  - 模型探活：`openai.OpenAI(base_url=..., api_key=...)`
  - GEPA 优化：`gepa.optimize(...)`
  - 任务/反思模型：`openai/<model>` 字符串模型名 + LiteLLM 默认路径
- **配置来源**：`configs/*.yaml` + `DEEPSEEK_API_KEY` / `DEEPSEEK_API_BASE` / `TASK_MODEL` / `REFLECTION_MODEL`

### 6. 技术选型理由

- **为什么用这个方案**：用户要求“尽量对齐 GEPA 原版，只替换大模型后端”，因此优先复用官方 AIME 数据入口、官方 optimize API、官方默认适配器语义
- **优势**：不改 GEPA 源码；模型名完全配置化；恢复更接近原版的 LiteLLM 字符串模型路径；减少自写适配层
- **劣势和风险**：真实 smoke/pilot 仍依赖 Hugging Face 数据集访问、DeepSeek 账户权限和 API 成本

### 7. 关键风险点

- **接口变化**：`gepa.examples.aime` 或 `gepa.optimize` 未来版本可能变动，需要 introspection 适配
- **边界条件**：缺失 `TASK_MODEL`/`REFLECTION_MODEL`/`DEEPSEEK_API_KEY` 时必须明确失败；不允许猜测替代模型
- **性能/成本**：`max_metric_calls=150` 会有明显 API 成本，必须 `--yes`
- **运行环境**：当前 Codex 沙箱会话默认没有用户环境变量，因此无法直接复现用户终端中的联网 smoke
