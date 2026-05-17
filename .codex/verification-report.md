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
