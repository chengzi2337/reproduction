## 编码前检查 - strict official path 与 exact seed prompt

时间：2026-05-18 20:25:02 +08:00

□ 已查阅上下文摘要文件：`.codex/context-summary-strict-official-path.md`
□ 将使用以下可复用组件：

- `src.deepseek_utils.build_litellm_model_name`：生成官方字符串模型路径
- `src.deepseek_utils.temporary_openai_compatible_env`：最小环境桥接
- `scripts/06_minimal_official_path_sanity.py::build_core_optimize_kwargs`：当前核心参数集合

□ 将遵循命名约定：Python `snake_case`、常量大写、报告文件使用中文标题和明确小节
□ 将遵循代码风格：不改 GEPA 核心算法，不新增 adapter/evaluator/callable，不扩实验
□ 确认不重复造轮子，证明：已检查 `src/gepa_official_runner.py`、`scripts/06_minimal_official_path_sanity.py`、`tests/test_minimal_official_path_sanity.py`

## 操作记录

时间：2026-05-18 20:25:02 +08:00

1. 读取用户指定文件：
   - `reports/project_summary_and_next_plan.md`
   - `reports/stage1_final_status.md`
   - `reports/official_core_path_comparison.md`
   - `reports/temperature_control_audit.md`
   - `src/gepa_official_runner.py`
   - `scripts/06_minimal_official_path_sanity.py`
2. 补充读取与模式确认：
   - `tests/test_gepa_official_runner.py`
   - `tests/test_minimal_official_path_sanity.py`
   - `tests/test_eval_saved_prompt.py`
   - `README.md`
   - `requirements.txt`
   - `src/config.py`
3. 外部可核验来源检索：
   - 当前官方仓库 `gepa-ai/gepa`
   - 历史仓库 `CerebrasResearch/gepa`
   - `gepa-ai/gepa-artifact`
   - arXiv `2507.19457`
4. 结论：
   - 当前本地 `SEED_PROMPT` 仅为语义等价版本
   - 当前官方 README quickstart 与官方 AIME 测试文件存在不同 prompt 文本
   - 最贴近 AIME 优化实验的 exact seed prompt 来自官方测试文件而非本地 wrapper

## 编码后声明 - strict official path 与 exact seed prompt

时间：2026-05-18 20:25:02 +08:00

### 1. 复用了以下既有组件

- `src.deepseek_utils.build_litellm_model_name`：仅作为 strict path 设计中的建议复用项
- `src.deepseek_utils.temporary_openai_compatible_env`：仅作为 strict path 设计中的建议复用项

### 2. 遵循了以下项目约定

- 命名约定：报告文件与字段名称延续现有 `strict / wrapper / seed prompt / Stage 1` 术语
- 代码风格：本次不改实验代码，仅新增留痕与报告文件
- 文件组织：正式输出写入 `reports/`，过程留痕写入项目本地 `.codex/`

### 3. 对比了以下相似实现

- `src/gepa_official_runner.py`：当前主 wrapper path，差异在于其包含探活、落盘和语义等价 seed prompt
- `scripts/06_minimal_official_path_sanity.py`：当前最小一致性快照路径，差异在于其仍保留 config 与 notes/snapshot 外壳
- 官方 `tests/test_aime_prompt_optimization/test_aime_prompt_optimize.py`：最接近 AIME 优化实验语义的可核验官方例子

### 4. 未重复造轮子的证明

- 已检查 `src/`、`scripts/`、`tests/` 和现有 `reports/`
- 本次新增内容仅为审计与设计文档，不新增实验方法、不改 GEPA 核心路径
