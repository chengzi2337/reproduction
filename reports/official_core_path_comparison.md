# 原版核心路径对照表

## 定位声明

当前项目的准确定位是：

- `GEPA method-level reproduction with DeepSeek backend`
- 不是 `original same-model reproduction`
- 不是最终论文级结论

更严格地说，应表述为：

> 在当前 `GEPA` Python 包暴露的 `AIME example / optimize / DefaultAdapter` 接口范围内，核心调用路径已基本回到官方路径。

不应表述为：

> 已经严格对齐原版 GEPA 论文实验。

## 关联报告与 Stage 1 范围

- 当前项目是 `GEPA method-level reproduction with DeepSeek backend`
- 当前项目不是 `original same-model reproduction`
- 当前项目不是 `paper-level final conclusion`
- `official_budget` 尚未运行
- `temperature` 当前采用 `方案 A`：
  - `not explicitly controlled`
  - Stage 1 当前不因该问题重跑 `smoke / pilot`
- 下一步仍是 `pilot saved prompt eval`
- 参见：
  - `reports/stage1_deepseek_method_reproduction_report.md`
  - `reports/temperature_control_audit.md`
  - `reports/stage1_final_status.md`

## 偏差风险分级

- `Low`：只影响审计和工程可用性，不改变核心实验语义
- `Medium`：可能影响可复现性或结论解释
- `High`：直接影响严格复现身份，或可能直接影响实验结果

## 对照表

| 模块 / 文件 | 是否属于 GEPA 官方核心 | 是否自定义 | 是否可能影响实验结果 | 当前处理方式 | 偏差风险等级 | 是否需要进一步收敛 |
| --- | --- | --- | --- | --- | --- | --- |
| `gepa.examples.aime.init_dataset()` | 是 | 否 | 是 | 当前通过官方接口直接加载；返回 `trainset / valset / testset` | Low | 否 |
| `gepa.optimize()` | 是 | 否 | 是 | 当前通过官方接口直接调用 | Low | 否 |
| `DefaultAdapter` | 是 | 否 | 是 | 当前主路径和 saved prompt eval 都复用官方 `DefaultAdapter` | Low | 否 |
| `seed prompt` | 否 | 是 | 是 | 当前使用“官方 quick start 语义等价 prompt”，不是已确认的官方字面字符串 | Medium | 是 |
| `task_lm` / `reflection_lm` 传入形式 | 否 | 是 | 是 | 当前传入 `openai/<model>` 字符串，复用官方字符串模型路径 | Medium | 是 |
| DeepSeek backend | 否 | 是 | 是 | 通过 OpenAI-compatible bridge 接到 LiteLLM | High | 否，方法级复现可接受；严格复现不可消除 |
| `temporary_openai_compatible_env()` | 否 | 是 | 否 | 仅注入 `OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_API_BASE` 给 LiteLLM | Low | 否 |
| `temperature_task` | 否 | 是 | 是 | 当前只被配置读取与落盘，未真正接入 `DefaultAdapter` / LiteLLM 批量调用 | High | 是 |
| `temperature_reflection` | 否 | 是 | 是 | 当前只被配置读取与落盘，未真正接入反思模型调用路径 | High | 是 |
| `max_metric_calls` | 否 | 是 | 是 | 当前显式传给 `gepa.optimize()` | Low | 否 |
| `seed` | 否 | 是 | 是 | 当前显式传给 `gepa.optimize()` | Low | 否 |
| `trainset / valset / testset` split | 是 | 否 | 是 | 当前依赖官方 `init_dataset()` 返回；saved prompt eval 若无 test split 则明确写 `validation sanity check only` | Low | 否 |
| `metric` / `evaluator` | 是 | 否 | 是 | 当前未自写 AIME evaluator，沿用官方 `DefaultAdapter` 默认 evaluator | Low | 否 |
| `saved prompt eval` | 否 | 是 | 是 | 当前是自定义审计脚本，但已改为复用官方 `DefaultAdapter.evaluate(batch, ...)` | Medium | 是 |
| `config.py` | 否 | 是 | 否 | 负责读取 YAML 和环境变量，不直接改变 GEPA 核心输入语义 | Low | 否 |
| `check_env.py` / `check_deepseek_models.py` | 否 | 是 | 否 | 仅做启动前校验，不进入 GEPA 核心优化逻辑 | Low | 否 |
| `manifest.json` / `notes.md` / `report` | 否 | 是 | 否 | 仅做审计落盘，不应改变 `trainset / valset / seed_candidate / metric / optimizer / model call` | Low | 否 |
| `src/gepa_official_runner.py` 外围封装 | 否 | 是 | 是 | 包含启动前探活、落盘、异常记录；核心调用仍是官方 `init_dataset()` + `optimize()` | Medium | 是 |
| `scripts/06_minimal_official_path_sanity.py` | 否 | 是 | 否 | 用于导出最小核心参数快照，证明外壳未改变核心调用语义 | Low | 否 |

## 当前最重要的偏差结论

### 可接受的工程外壳偏差

以下偏差不属于核心问题，可以保留：

- `config.py`
- `check_env.py`
- `check_deepseek_models.py`
- `logging_utils.py`
- `manifest.json`
- `notes.md`
- `reports/`

前提是它们不改变：

- `trainset`
- `valset`
- `seed_candidate`
- `metric / evaluator`
- `optimizer`
- `model call`

### 会影响严格复现身份的偏差

以下偏差使得当前项目不能被称为“原论文 same-model 严格复现”：

- DeepSeek backend
- `openai/<model>` bridge
- OpenAI-compatible 环境变量桥接

因此当前项目只能写成：

- `GEPA method-level reproduction with DeepSeek backend`

### 会影响实验结果的偏差

当前最需要继续收敛的高风险项是：

1. `temperature_task` 当前未接入实际 task model 调用路径
2. `temperature_reflection` 当前未接入实际 reflection model 调用路径
3. `seed prompt` 当前是语义等价版本，不是已确认的官方字面字符串
4. `saved prompt eval` 虽已回到官方批量接口，但仍属于自定义审计层

## 结论

当前项目已经具备：

- 官方 `AIME example`
- 官方 `gepa.optimize()`
- 官方 `DefaultAdapter`
- DeepSeek 后端下的 Stage 1 `smoke / pilot` 方法级复现能力

但它仍然不是：

- 原论文 `same-model` 严格复现
- 可直接对标原论文分数的同构实验
- 可直接支撑论文最终结论的完整实验体系

当前最稳妥的结论是：

> 这是一个以 GEPA 官方核心接口为基础、使用 DeepSeek 作为替代后端的 Stage 1 方法级复现基线；外壳偏差可接受，但仍需持续压缩会改变实验语义的高风险偏差。
