# DeepSeek Continuation 实验计划书

## 1. 文档定位

本文档用于规划当前仓库在 **不改写 Stage 1 历史结论** 的前提下，继续使用 DeepSeek 推进后续实验。

本文档中的后续实验统一定义为：

- `GEPA method-level reproduction with DeepSeek backend`
- `DeepSeek continuation`

本文档中的后续实验 **不是**：

- `original same-model reproduction`
- `paper-level final conclusion`
- Stage 1 历史结果重写

## 2. 规划依据

### 2.1 论文层面的依据

根据 GEPA 论文公开主来源，GEPA 的核心主张不是“换后端复现论文分数”，而是：

- 使用自然语言反思替代 RL 中的稀疏标量更新
- 在较少 rollout 下，学出更好的 prompt
- 在 AIME 等任务上，相对 RL / MIPROv2 展现更高的优化效率

因此，当前 DeepSeek 路线最有价值的工作，不是追求 same-model 对齐，而是：

- 保持 GEPA 官方核心调用路径
- 用 DeepSeek 作为替代后端
- 验证 prompt evolution 是否在更薄的 official-core path 下仍然成立

### 2.2 仓库现状依据

当前仓库已经具备三类可直接复用的 DeepSeek 资产：

1. Stage 1 wrapper baseline 已封版  
   见：
   - [stage1_final_status.md](C:/Users/lin/Documents/New%20project%202/reports/stage1_final_status.md)
   - [stage1_deepseek_method_reproduction_report.md](C:/Users/lin/Documents/New%20project%202/reports/stage1_deepseek_method_reproduction_report.md)

2. strict README quickstart path 已完成极小预算校验  
   见：
   - [strict_readme_quickstart_sanity_status.md](C:/Users/lin/Documents/New%20project%202/reports/strict_readme_quickstart_sanity_status.md)
   - [07_strict_readme_quickstart_path.py](C:/Users/lin/Documents/New%20project%202/scripts/07_strict_readme_quickstart_path.py)

3. DeepSeek provider / 配置 / runner 仍完整可用  
   见：
   - [config.py](C:/Users/lin/Documents/New%20project%202/src/config.py)
   - [deepseek_utils.py](C:/Users/lin/Documents/New%20project%202/src/deepseek_utils.py)
   - [02_run_gepa_aime_smoke.py](C:/Users/lin/Documents/New%20project%202/scripts/02_run_gepa_aime_smoke.py)
   - [03_run_gepa_aime_pilot.py](C:/Users/lin/Documents/New%20project%202/scripts/03_run_gepa_aime_pilot.py)
   - [04_run_gepa_aime_official_budget.py](C:/Users/lin/Documents/New%20project%202/scripts/04_run_gepa_aime_official_budget.py)

## 3. 当前已知边界

后续所有 DeepSeek continuation 工作必须保持以下边界：

1. 不改写 Stage 1 已封版结果
2. 不把 DeepSeek 结果写成 `same-model reproduction`
3. 不修改 GEPA optimizer
4. 不修改 evaluator
5. 不新增 benchmark
6. 不新增方法
7. 当前不运行 `official_budget`
8. `temperature` 仍按现有结论处理：
   - `not explicitly controlled`
   - 不把 `temperature_task=0.0 / temperature_reflection=0.7` 写成已受控变量

## 4. 推荐轨道定义

后续不要继续把所有 DeepSeek 工作混写成 Stage 1。

建议并列维护以下两条 DeepSeek 轨道：

### 4.1 轨道 A：Stage 1 wrapper baseline

该轨道已经封版。

它的作用是：

- 保留当前仓库最早的 DeepSeek method-level baseline
- 保留已完成的 smoke / pilot / saved prompt eval 证据

它当前不再承担：

- strict 对齐验证
- 新的 continuation 实验

### 4.2 轨道 B：DeepSeek strict-path continuation

该轨道是后续推荐主线。

建议对外命名为：

- `DeepSeek strict-readme continuation`

它的作用是：

- 在更薄的 official-core path 下继续做 DeepSeek 后续实验
- 与 Stage 1 wrapper baseline 分轨记录
- 为未来是否值得进入 `official_budget` 提供更干净的判断依据

## 5. 推荐执行顺序

### Phase 0：冻结旧结论

目标：

- 明确 Stage 1 只保留历史结论，不再回写

产物：

- 不新增实验
- 只在后续文档中保持命名边界

停止条件：

- Stage 1 / strict / continuation 三条身份不再混写

### Phase 1：DeepSeek strict smoke

目标：

- 在 `strict_readme_quickstart_path` 下完成一次真实 `smoke`

建议参数：

- 路径：
  - [07_strict_readme_quickstart_path.py](C:/Users/lin/Documents/New%20project%202/scripts/07_strict_readme_quickstart_path.py)
- provider：
  - `deepseek`
- task_model：
  - `deepseek-v4-flash`
- reflection_model：
  - `deepseek-v4-pro`
- `max_metric_calls = 10`
- `seed = 42`

目的：

- 验证在更薄的 official-core path 下，DeepSeek 仍能跑完整个 smoke 闭环

验收条件：

- `execute_optimize = true`
- 有独立 `run_dir`
- 有独立结果摘要
- 不把结果回写成 Stage 1 baseline

停止规则：

- 若 strict smoke 无法闭环，先排查路径语义，不进入 pilot

### Phase 2：DeepSeek strict pilot

目标：

- 在 strict path 下完成一次 pilot

建议参数：

- 同 Phase 1 路径
- `max_metric_calls = 50`

目的：

- 观察 DeepSeek 在更薄路径下是否仍有稳定 prompt evolution

验收条件：

- `optimized_prompt` 生成成功
- `best_score` 有记录
- 不发生路径身份污染

停止规则：

- 若 strict pilot 没有形成有效 prompt evolution，则先做 failure-mode audit，不进入 `official_budget`

### Phase 3：strict pilot saved prompt eval

目标：

- 对 strict pilot 产物做独立 saved prompt eval

目的：

- 判断更薄路径下的 optimized prompt 是否仍优于对应的 strict seed prompt

验收条件：

- 单独形成 strict continuation 的 saved prompt eval 报告
- 命名上明确区分：
  - `strict continuation seed/test or val score`
  - `stage1_wrapper_saved_prompt_seed_test_score`

停止规则：

- 如果 strict 路径 saved prompt eval 没有改善，不进入 `official_budget`

### Phase 4：是否进入 DeepSeek official budget 评估

只有在以下条件全部满足时，才允许讨论 `official_budget`：

1. strict smoke 完成
2. strict pilot 完成
3. strict pilot saved prompt eval 完成
4. strict continuation 路径下没有新的高风险协议问题

当前不建议直接进入：

- [04_run_gepa_aime_official_budget.py](C:/Users/lin/Documents/New%20project%202/scripts/04_run_gepa_aime_official_budget.py)

## 6. 为什么当前不建议直接运行 official_budget

原因有四个：

1. Stage 1 wrapper path 与 strict path 仍是两条不同轨道
2. 论文主张关注“预算内优化效率”，不是“先大预算再倒推协议问题”
3. 当前最有价值的问题，是 DeepSeek 在 strict path 下是否仍保留 Stage 1 观察到的 prompt evolution
4. `official_budget` 会放大当前未解的解释风险

## 7. 推荐 runner 与用途

### 保留但不优先继续使用

- [02_run_gepa_aime_smoke.py](C:/Users/lin/Documents/New%20project%202/scripts/02_run_gepa_aime_smoke.py)
- [03_run_gepa_aime_pilot.py](C:/Users/lin/Documents/New%20project%202/scripts/03_run_gepa_aime_pilot.py)

用途：

- 这些脚本代表 Stage 1 wrapper path 的历史入口
- 适合保留，不适合继续作为主线 continuation

### 推荐主入口

- [07_strict_readme_quickstart_path.py](C:/Users/lin/Documents/New%20project%202/scripts/07_strict_readme_quickstart_path.py)

用途：

- 作为后续 DeepSeek continuation 的统一入口
- 先做 strict smoke，再做 strict pilot

## 8. 文档与命名规则

后续 DeepSeek continuation 文档建议单独命名，不回写 Stage 1：

- `reports/deepseek_strict_continuation_smoke_result.md`
- `reports/deepseek_strict_continuation_pilot_result.md`
- `reports/deepseek_strict_continuation_saved_prompt_eval.md`
- `reports/deepseek_official_budget_readiness.md`

必须避免的写法：

- `Stage 1 updated baseline`
- `same-model reproduction`
- `official reproduction completed`

推荐写法：

- `DeepSeek strict-readme continuation`
- `DeepSeek method-level continuation under official-core path`

## 9. 风险清单

### 风险 1：继续混用 Stage 1 wrapper 与 strict continuation

风险：

- 后续结论无法解释

处理：

- 分轨命名
- 分轨报告

### 风险 2：temperature 被误写成受控变量

风险：

- 结论失真

处理：

- 继续沿用：
  - `temperature not explicitly controlled`

### 风险 3：过早运行 official_budget

风险：

- 放大解释噪声

处理：

- 只有 strict smoke / pilot / saved prompt eval 都稳定后再评估

## 10. 当前结论

当前最推荐的继续路线不是：

- 重跑 Stage 1 wrapper
- 直接运行 `official_budget`
- 继续围绕 MiMo 主线扩实验

当前最推荐的继续路线是：

1. 冻结 Stage 1 不动
2. 把 DeepSeek 后续实验迁移到 strict-readme continuation
3. 先做 strict smoke
4. 再做 strict pilot
5. 再做 strict saved prompt eval
6. 最后才决定是否讨论 `official_budget`

一句话总结：

> DeepSeek 现在仍然是仓库里最适合继续推进的主实验后端，但后续必须以 `strict official-core continuation` 的形式推进，而不是回头修改 Stage 1，也不是直接冲 `official_budget`。
