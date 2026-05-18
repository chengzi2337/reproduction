# strict path 与 wrapper path 差异表

## 说明

- `wrapper path` 指当前 `src/gepa_official_runner.py`
- `strict path` 这里优先指 `strict_readme_quickstart_path`
- `official AIME test path` 是另一条单独路径，不应和 README quickstart strict path 混写
- 分类规则：
  - `仅影响审计`
  - `影响实验语义`

## 差异表

| 差异项 | wrapper path 当前状态 | strict path 目标状态 | 影响分类 | 结论 |
| --- | --- | --- | --- | --- |
| `init_dataset` 导入方式 | 先做 `_locate_aime_init_dataset()`，必要时可 introspection fallback | 直接 `from gepa.examples.aime import init_dataset`，失败即退出 | 仅影响审计，严格路径要求 fail closed | 当当前安装包已直接暴露官方入口时，fallback 主要影响路径纯度；但 strict path 不应允许 fallback 命中非预期模块 |
| `gepa.optimize` 调用前探活 | 有 `probe_model_with_openai_client()` | 删除 | 仅影响审计 | 探活只影响启动前阻塞与报错可读性，不改变 `gepa.optimize()` 输入 |
| 配置来源 | `src.config` + YAML + 环境变量 | 环境变量 + 极少量 CLI 参数 | 仅影响审计 | 只要最终 `task_lm / reflection_lm / max_metric_calls / seed` 相同，实验语义不变 |
| `SEED_PROMPT` 来源 | 本地 quickstart 语义等价版本 | 对 `strict_readme_quickstart_path` 固定为 README quickstart exact prompt | 影响实验语义 | prompt 文本本身是优化起点，改变它就改变实验语义 |
| `official AIME test prompt` | wrapper 当前未对齐 | 仅在单独的 `strict_official_aime_test_path` 中使用 `### <final answer>` exact prompt | 影响实验语义 | 这是一条单独官方路径，不应和 README quickstart strict path 混写 |
| `task_lm` 传入形式 | `openai/<task_model>` 字符串 | 相同 | 无实质差异 | 该项应保持不变 |
| `reflection_lm` 传入形式 | `openai/<reflection_model>` 字符串 | 相同 | 无实质差异 | 该项应保持不变 |
| adapter | `adapter=None`，走官方默认路径 | 对 `strict_readme_quickstart_path` 保持相同 | 无实质差异 | strict README quickstart path 不应引入自定义 adapter |
| evaluator | 不自写 evaluator | 相同 | 无实质差异 | strict path 不应引入自定义 evaluator |
| callable | 不使用 callable | 相同 | 无实质差异 | strict path 不应引入 callable |
| `temperature_task / temperature_reflection` | 读取并落盘，但不显式接线 | 不读取、不落盘、不接线 | 仅影响审计 | 前提是它们确实没有接入模型调用路径；在这个前提下，删除记录不会改变实验语义 |
| `saved prompt eval` | 在主流程外另有审计脚本 | strict path 不包含 | 仅影响审计 | 这是后验评估层，不属于 `gepa.optimize()` 主实验语义 |
| `manifest.json` | 写入 | 删除 | 仅影响审计 | 只影响留痕 |
| `config_resolved.yaml` | 写入 | 删除 | 仅影响审计 | 只影响留痕 |
| `notes.md` | 写入 | 删除 | 仅影响审计 | 只影响留痕 |
| `package_versions.txt` | 写入 | 删除 | 仅影响审计 | 只影响留痕 |
| `stdout.log / stderr.log` | 写入 | 删除 | 仅影响审计 | 只影响排障便利性 |
| `raw_result.json / pkl` | 尝试写入 | 删除 | 仅影响审计 | 只影响结果可回放性 |
| `run_dir` | 传入 `gepa.optimize()` 并产生完整目录 | 仍保留，但输出最小化 | 仅影响审计 | 建议保留最小 `run_dir`，方便基本留痕 |
| DeepSeek OpenAI-compatible 环境桥接 | 有，且包在 helper 里 | 保留最小桥接 | 项目身份偏差，不构成 wrapper-vs-strict 差异 | 两边都需要同一桥接；它影响整个项目身份解释，但不是 wrapper 相对 strict 新增出来的差异 |

## 应优先收敛的差异

### 第一优先级：影响实验语义

1. `SEED_PROMPT` 必须从本地语义等价版本切换到可核验 exact prompt
2. 必须先明确自己对齐的是：
   - `strict_readme_quickstart_path`
   - 还是 `strict_official_aime_test_path`

### 第二优先级：只影响审计，但影响“strict”纯度

1. 删除 preflight probe
2. 删除 introspection fallback
3. 删除重审计落盘
4. 删除 config 与 temperature 记录层

## 结论

如果只问“wrapper 有没有改动官方核心输入语义”，当前最关键的一项不是 manifest、notes 或 probe，而是：

- `seed prompt` 还没有切到可核验 exact prompt

更严格地说：

- 在当前 `strict_readme_quickstart_path` 语义下，`seed prompt` 差异是当前唯一明确影响实验语义的 wrapper-vs-strict 差异
- `DeepSeek backend` 是整个项目身份偏差，不是 wrapper-vs-strict 差异

如果只问“strict path 还差多远才算极薄”，当前最该删除的是：

- preflight probe
- introspection fallback
- config 依赖
- 审计落盘层
