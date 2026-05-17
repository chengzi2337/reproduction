## 编码前检查 - gepa deepseek stage1 全面复用重写

时间：2026-05-16 22:50:00 +0800

□ 已查阅上下文摘要文件：`.codex/context-summary-gepa-deepseek-stage1.md`
□ 将使用以下可复用组件：

- `src/config.py`：继续承担 YAML 与环境变量解析
- `src/logging_utils.py`：继续承担 manifest、版本、run 目录、stdout/stderr 落盘
- `src/gepa_official_runner.py`：继续承担官方 AIME 数据入口与 `gepa.optimize()` 调用骨架
- `src/eval_utils.py`：继续承担保存 prompt 的评估与 JSONL 落盘
- 已安装包 `gepa.examples.aime`：作为官方 AIME 数据入口依据

□ 将遵循命名约定：Python 模块与脚本使用蛇形命名，配置字段使用小写下划线
□ 将遵循代码风格：类型注解、`Path`、UTF-8、最小必要注释
□ 确认不重复造轮子，证明：已检查 `src/`、`scripts/`、`tests/` 与已安装 `gepa` 包，本次只回到官方路径，不新增 provider、optimizer、dataset、metric

## 编码中监控 - 回退到官方字符串模型路径

时间：2026-05-16 22:58:00 +0800

□ 是否使用了摘要中列出的可复用组件？
是：继续复用 `config`、`logging_utils`、`gepa_official_runner`、`eval_utils`

□ 命名是否符合项目约定？
是：统一使用 `deepseek_*`、`gepa_aime_*`、`method_level_reproduction`

□ 代码风格是否一致？
是：保持 `dataclass`、`Path`、JSON/YAML 落盘、pytest 断言风格

本轮关键决策：

- 删除自写 `task_lm` / `reflection_lm` callable 路径
- 改为 `openai/<model>` 字符串模型名
- 通过临时设置 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_API_BASE` 把 DeepSeek 接到 LiteLLM 默认路径
- 保留 `openai.OpenAI(...)` 探活脚本，因为这是模型检查脚本的直接需求

## 编码后声明 - gepa deepseek stage1 全面复用重写

时间：2026-05-16 23:08:00 +0800

### 1. 复用了以下既有组件

- `src/config.py`：继续承担 YAML 与环境变量解析，不改调用方协议
- `src/logging_utils.py`：继续承担 manifest、版本、run 目录、stdout/stderr 落盘
- `src/gepa_official_runner.py`：继续直接调用官方 `gepa.examples.aime.init_dataset()` 与 `gepa.optimize()`
- `src/eval_utils.py`：继续用 GEPA `DefaultAdapter` 做保存 prompt 的评估

### 2. 遵循了以下项目约定

- 命名约定：配置和脚本统一保持 `deepseek_*` / `gepa_aime_*`
- 代码风格：沿用类型注解、`Path`、JSON/YAML 落盘与 pytest 断言风格
- 文件组织：继续保持 `configs/`、`scripts/`、`src/`、`tests/` 分层

### 3. 对比了以下相似实现

- 旧 `src/gepa_official_runner.py`：原先把 `task_lm` / `reflection_lm` 封成 callable，本次改回官方更接近的字符串模型路径
- 旧 `src/eval_utils.py`：原先评估也走 callable，本次改为 `DefaultAdapter(model=build_litellm_model_name(task_model))`
- 官方 `gepa.examples.aime`：继续直接复用 `init_dataset()`，不自写 AIME 数据构造

### 4. 未重复造轮子的证明

- 已检查 `src/`、`scripts/`、`tests/` 与已安装 `gepa` 包，直接复用其配置解析、日志落盘、官方 runner 和默认 evaluator 路径
- 未新增自写 provider、optimizer、AIME dataset、metric、Pareto selection

### 5. 本地验证结果

- `python -m pytest -q`：通过，20 项测试全部成功
- `python -m compileall src scripts`：通过
- `python scripts/00_check_env.py`：当前 Codex 沙箱会话内未注入 `DEEPSEEK_API_KEY` / `TASK_MODEL` / `REFLECTION_MODEL`，按预期失败
- `python scripts/01_check_deepseek_models.py --config configs/deepseek_smoke.yaml`：当前 Codex 沙箱会话内因缺少环境变量而生成新的 `blocked_report.md`

### 6. 差距与后续

- 代码已回到“最大限度复用原版”的实现路径
- 但当前 Codex 沙箱会话没有用户真实环境变量，因此还不能在这里直接完成新的联网 smoke
- 若用户在其终端继续执行 `scripts/02_run_gepa_aime_smoke.py`，现在将走官方字符串模型路径，而不是旧的 callable 串行路径
