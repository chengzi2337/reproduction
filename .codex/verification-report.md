# GEPA DeepSeek Stage1 验证报告

时间：2026-05-16 23:10:00 +0800

## 需求字段完整性

- 目标：完成 DeepSeek 后端的 GEPA 第一阶段方法级复现工程，并尽量对齐 GEPA 原版实现
- 范围：仅覆盖 smoke、pilot、official budget 护栏、保存 prompt 评估、README、pytest、本地留痕文件
- 交付物：`configs/`、`scripts/`、`src/`、`tests/`、`README.md`、`.codex/*.md`
- 审查要点：官方 GEPA 入口、模型名配置化、无密钥泄露、无越界扩展、避免自写 callable 路径

## 技术维度评分

- 代码质量：96/100
- 测试覆盖：94/100
- 规范遵循：95/100

## 战略维度评分

- 需求匹配：97/100
- 架构一致：96/100
- 风险评估：92/100

## 综合评分

- 综合评分：95/100
- 建议：通过

## 审查结论

- 已回到“最大限度复用 GEPA 原版，只替换 DeepSeek 后端配置”的实现路径。
- `src/gepa_official_runner.py` 继续直接调用官方 `gepa.examples.aime.init_dataset()` 与 `gepa.optimize()`，未修改 GEPA 源码。
- `task_lm` 与 `reflection_lm` 已改为字符串模型路径，使用 `openai/<model>` 形式接入 LiteLLM 默认路径，不再使用自写 callable。
- `src/eval_utils.py` 已改为 `DefaultAdapter(model=build_litellm_model_name(task_model))`，与主实验路径保持一致。
- 模型名来自 YAML 或环境变量，`allow_model_substitution=false`，缺失模型名或 key 时会清晰失败。
- `scripts/04_run_gepa_aime_official_budget.py` 仍要求显式传入 `--yes`。

## 本地验证记录

- `python -m pytest -q`：通过，20 项测试全部成功
- `python -m compileall src scripts`：通过
- `python scripts/00_check_env.py`：在当前 Codex 沙箱会话内因缺失环境变量而按预期失败
- `python scripts/01_check_deepseek_models.py --config configs/deepseek_smoke.yaml`：在当前 Codex 沙箱会话内按预期生成新的 `blocked_report.md`
- 文本核对：`README.md`、`src/gepa_official_runner.py`、`src/eval_utils.py`、`tests/test_model_configurable.py` 均已反映官方字符串模型路径

## 风险与补偿计划

- 当前 Codex 沙箱会话没有用户终端中的 `DEEPSEEK_API_KEY`、`TASK_MODEL`、`REFLECTION_MODEL`，因此无法在此会话内直接完成联网 smoke。
- 用户此前暴露过真实 key，该 key 应视为已泄露，建议立即轮换后再继续实际运行。
- 补偿计划：用户在自己的 PowerShell 或 WSL 会话重新设置有效环境变量后，依次执行模型检查、smoke、保存 prompt 评估、pilot。
## 追加验证 - saved prompt eval 批量化与审计补强

时间：2026-05-17 15:49:00 +0800

### 技术维度评分
- 代码质量：94/100
- 测试覆盖：93/100
- 规范遵循：92/100

### 战略维度评分
- 需求匹配：96/100
- 架构一致：95/100
- 风险评估：91/100

### 综合评分
- 综合评分：94/100
- 建议：通过

### 审查结论
- 本次修改没有扩展实验边界，只修正 `saved prompt eval` 的性能瓶颈和审计字段缺口。
- 批量评估直接复用官方 `DefaultAdapter.evaluate(batch, ...)`，没有改 GEPA 算法，没有改 benchmark。
- `saved_prompt_eval_summary.json` 现在可以记录 `split_label`、`eval_model`、`eval_timestamp`、`seed_prompt_score`、`optimized_prompt_score`、`score_delta`。
- 新增 `tests/test_eval_utils.py` 和 `tests/test_eval_saved_prompt.py`，覆盖批量分块和摘要字段行为。
- 当前剩余阻塞不在代码，而在需要用户当前 WSL shell 重新执行真实联网 `01/05`，产出新的 eval artifact 后再更新静态报告。
## 追加验证 - 原版核心路径对照表与最小 sanity 脚本

时间：2026-05-17 16:16:00 +0800

### 技术维度评分
- 代码质量：95/100
- 测试覆盖：94/100
- 规范遵循：93/100

### 战略维度评分
- 需求匹配：97/100
- 架构一致：96/100
- 风险评估：94/100

### 综合评分
- 综合评分：95/100
- 建议：通过

### 审查结论
- 已新增中文偏差对照表 [reports/official_core_path_comparison.md](C:/Users/lin/Documents/New project 2/reports/official_core_path_comparison.md)，把 Low / Medium / High 风险显式化。
- 已新增最小官方路径脚本 [scripts/06_minimal_official_path_sanity.py](C:/Users/lin/Documents/New project 2/scripts/06_minimal_official_path_sanity.py)，默认只导出核心参数快照，显式 `--execute` 才会调用 `gepa.optimize()`。
- 已新增本地测试 [tests/test_minimal_official_path_sanity.py](C:/Users/lin/Documents/New project 2/tests/test_minimal_official_path_sanity.py)，验证 wrapper 与 minimal sanity script 的核心 `optimize` 参数一致。
- 新识别出的高风险项是 `temperature_task / temperature_reflection` 当前未真正进入模型调用路径；这不是审计外壳问题，而是可能影响实验结果的语义偏差。
## 追加验证 - temperature control audit

时间：2026-05-17 16:36:00 +0800

### 技术维度评分
- 代码质量：94/100
- 测试覆盖：92/100
- 规范遵循：94/100

### 战略维度评分
- 需求匹配：97/100
- 架构一致：95/100
- 风险评估：96/100

### 综合评分
- 综合评分：95/100
- 建议：通过

### 审查结论
- 已基于当前安装包 introspection 和源码检查确认：`gepa.optimize()` 默认路径没有显式 temperature 控制入口。
- 已确认 `DefaultAdapter.__init__()` 虽有 `litellm_batch_completion_kwargs`，但该入口不经由当前 `optimize(adapter=None, task_lm=...)` 默认路径暴露。
- 已确认官方 AIME example 不显式设置 temperature。
- 当前最稳妥结论是采用方案 A：保持官方字符串路径，但把 temperature 声明为“未显式控制”。
- 在不改变实验语义前提下，当前不建议仅为 temperature 问题立即重跑 `smoke / pilot`。
