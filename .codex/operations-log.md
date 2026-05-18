## 编码前检查 - exact seed prompt 修正与 strict 路径拆分

时间：2026-05-18 21:05:00 +08:00

□ 已查阅上下文摘要文件：`.codex/context-summary-strict-official-path.md`
□ 将使用以下可复用组件：

- `src.deepseek_utils.build_litellm_model_name`：生成官方字符串模型路径
- `src.deepseek_utils.temporary_openai_compatible_env`：最小环境桥接
- `scripts/06_minimal_official_path_sanity.py::build_core_optimize_kwargs`：当前核心参数集合

□ 将遵循命名约定：Python `snake_case`、常量大写、报告文件使用中文标题和明确小节
□ 将遵循代码风格：不改 GEPA 核心算法，不新增 adapter/evaluator/callable，不扩实验
□ 确认不重复造轮子，证明：已检查 `src/gepa_official_runner.py`、`scripts/06_minimal_official_path_sanity.py`、`tests/test_minimal_official_path_sanity.py`

## 操作记录

时间：2026-05-18 21:05:00 +08:00

1. 复核用户指出的 exact 文本问题：
   - `reports/exact_seed_prompt_trace.md`
   - `reports/strict_official_path_design.md`
   - `reports/strict_vs_wrapper_path_diff.md`
2. 外部复核重点：
   - 当前官方 `README.md` quickstart 使用 `### <answer>`
   - 官方 AIME 测试上下文应按 `### <final answer>` 记录
3. 修正方向：
   - 把 README quickstart path 与 official AIME test path 拆成两条
   - 把 strict 路径标题改成 DeepSeek backend 下的 minimal official-core path
   - 收紧 fallback 与 temperature 的差异分类表述

## 编码后声明 - exact seed prompt 修正与 strict 路径拆分

时间：2026-05-18 21:05:00 +08:00

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
- 官方 `README.md`：当前公开 quickstart 路径
- 官方 `tests/test_aime_prompt_optimization/test_aime_prompt_optimize.py`：单独的官方 AIME 测试路径

### 4. 未重复造轮子的证明

- 已检查 `src/`、`scripts/`、`tests/` 和现有 `reports/`
- 本次新增内容仅为审计与设计文档，不新增实验方法、不改 GEPA 核心路径
