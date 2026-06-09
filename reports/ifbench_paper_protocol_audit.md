# IFBench 论文协议审计

时间：2026-06-08 20:16:43 +08:00

## 审计范围

- 论文：`GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning`（arXiv `2507.19457` / OpenReview ICLR 2026 版本）
- 论文 artifact：`C:\Users\lin\Documents\New project 2\.codex\gepa-artifact`
- 当前上游仓库副本：`C:\Users\lin\Documents\New project 2\.codex\upstream-gepa`
- 当前本地实现与报告：
  - `scripts/run_ifbench_qwen3_smoke.py`
  - `tests/test_ifbench_qwen3_smoke.py`
  - `reports/ifbench_qwen3_smoke_reproduction.md`

## 快速结论

1. **IFBench 确实是论文中使用 Qwen3-8B 的 benchmark。**
   - 论文在 `G.1` 明确介绍 IFBench，并在 `G.2` 指定 Qwen3-8B 是 open-source 实验模型。
   - Qwen3 的 IFBench 最终 test 分数出现在 **Figure 9(b)**，不是表格。
2. **当前本地 artifact 不是可证明的“论文冻结发布版本”。**
   - 本地 `gepa-artifact` 指向 `main` 分支 HEAD `cbefbc1`，提交时间是 **2026-02-07**。
   - 该 HEAD 含一个发布后 bugfix：`Fix aliased list bug corrupting seed program's val subscores`。
   - 仓库本地没有 tag，无法把当前 checkout 直接锚定为“论文发布时 commit”。
3. **最关键的协议冲突是 IFBench 的 train/val 切分。**
   - 论文正文写的是 **150 train / 300 val / 294 test**。
   - artifact loader 实现的是 **300 train / 300 val / 294 test**，而且没找到任何把 300 train 再下采样到 150 的代码。
4. **因此当前不具备启动正式 DashScope API 复现实验的条件。**
   - 在解决 train/val 冲突、artifact 版本冻结和 16384→8192 后端漂移之前，最多只能进入“继续审计”，不能进入正式 paper-benchmark run。

## 协议对照表

| 字段 | 论文口径 | artifact / 本地代码证据 | 状态 | 审计结论 |
| --- | --- | --- | --- | --- |
| benchmark 名称 | IFBench | `ifbench_data.py`、`ifbench_program.py`、`ifbench_metric.py` 都位于 `benchmarks/IFBench/` | 一致 | benchmark 名称一致。 |
| benchmark 版本 | 论文写的是 IFBench（Pyatkin et al., 2025b），未给出 commit / dataset revision | artifact 只提供本地 `IFBench_train.jsonl` / `IFBench_test.jsonl`，无 tag / dataset revision | 未找到 | 只能把当前 artifact 视为“打包快照”，不能说出精确版本号。 |
| 数据来源 | 论文：`IF-RLVR Train` 用于 train/val，`IFBench` 用于 test，目的是避免优化器访问 IFBench 的新约束 | `ifbench_data.py:18-24` 从本地 `IFBench_train.jsonl` / `IFBench_test.jsonl` 加载；其中 `IFBench_test.jsonl` 为 294 条，`IFBench_train.jsonl` 为 14971 条（本地行数统计） | 部分一致 | test 来源一致；train/val 只知来自本地 train 文件，但其与论文所称 `IF-RLVR Train` 的映射关系没有单独元数据。 |
| train / val / dev / test 数量 | 论文正文：`150 / 300 / 未提 dev / 294`（OpenReview p.21, `L1231-L1236`） | `ifbench_data.py:23-24` 明确实现为 `300 / 300 / 无 dev_set / 294` | **冲突** | 这是当前最严重的 strict reproduction 阻断项。 |
| 数据切分方法 | 论文：把 `IF-RLVR Train` 划成 train/val，并用 OOD 的 `IFBench` 做 test（OpenReview p.21, `L1231-L1236`） | `ifbench_data.py:23-24` 直接取 `train_val_set[:300]` 做 val，`train_val_set[300:600]` 做 train；未见 shuffle | **冲突** | artifact 实现不是论文文字里显式描述的 `150/300`，而是前 600 条固定切片。 |
| dev 集 | 论文 IFBench 段未提 | `ifbench_data.py` 没有定义 `dev_set` | 未找到 | IFBench 正式协议里看起来没有 dev；artifact `dry_run` 才会假设 `dev_set` 存在。 |
| seed | 论文正文未给出 IFBench 专门的 seed 描述 | `generate_launch_commands.py:9` 固定 `SEEDS = [0]`；`run_experiments.py:166-173` 只有 `seed != 0` 时才打乱 train+val | 部分一致 | 当前能确认 artifact 官方命令生成器默认只跑 `seed=0`。 |
| task model | 论文：Qwen3-8B 是 open-source 实验模型（OpenReview p.22, `L1266-L1268`） | `experiment_configs.py:37-45` 把 Qwen 路线写成 `name=qwen3-8b`、`model=openai/arbor:qwen/qwen3-8b` | 一致 | 论文口径的 task model 是本地 Arbor 托管的 Qwen3-8B，不是远端 DashScope API。 |
| reflection model | 论文 `G.2` 只说“系统模块”共用同一模型，没有单独点名 IFBench 的 reflection LM | `run_experiments.py:374-377` 把 `lm_for_optimizer` 设为当前 Qwen LM；`gepa.py:542` 让 proposer 默认回退到 `dspy` 当前 LM / `curr_prog.get_lm()` | 推断 | **推断为与 task model 相同**，但论文没有单独写成“reflection model = Qwen3-8B”。 |
| 初始 prompt | 论文未给出 IFBench 静态 seed prompt 文本 | `ifbench_program.py:4-24` 只定义两个 DSPy `Signature` 和两段类 docstring；未见单独 prompt 文件 | 未找到 | 初始 prompt 是 DSPy `ChainOfThought` 的隐式组合，不是仓库里单独可引用的纯文本 seed prompt。 |
| DSPy program / signature | 论文：两阶段系统，先回答，再按约束改写（OpenReview p.21, `L1233-L1235`） | `ifbench_program.py:17-24` 是 `GenerateResponse -> EnsureCorrectResponse` 两阶段 `ChainOfThought` | 一致 | 本地 artifact 与论文的系统结构一致。 |
| metric 定义 | 论文：反馈模块返回满足与未满足的约束说明（OpenReview p.21, `L1234-L1236`） | `ifbench_metric.py:8-94` 对每条指令检查 `instruction.check_following`，返回 `score=sum(is_following_list)/len(is_following_list)` 和文本反馈 | 一致 | 每样本分数是“满足约束比例”；反馈文本列出满足/不满足的约束。 |
| 分数聚合方式 | 论文最终结果是百分制 test score（Figure 9） | `run_experiments.py:423-435` 使用 `dspy.Evaluate` 汇总 test 集；每样本 metric 是 0-1 比例 | 推断 | **推断** 最终分数是 test 集样本均值再映射成百分制；这与 Figure 9 的 36.9 / 38.6 数值形态一致。 |
| GEPA 版本 | 论文指向单独 artifact 仓库 | `gepa-artifact/pyproject.toml:1-4` 版本号是 `0.0.1` | 部分一致 | 可把论文 artifact 代码记为 `gepa_artifact 0.0.1`，但这不是上游 `gepa` 包版本。 |
| GEPA 总预算 | 论文：GEPA 预算按 benchmark 与 MIPROv2 对齐（OpenReview p.23, `L1322-L1334`） | `experiment_configs.py:191-198` 把 IFBench + MIPROv2-Heavy 预算写死为 `3593`；GEPA 配置通过 `add_max_metric_calls` 读取这条预算 | 一致 | IFBench 的 GEPA 预算目标是 `3593` 次 metric calls / rollouts 对齐口径。 |
| minibatch / subsample 大小 | 论文：所有 GEPA run 的 minibatch size 为 `3`（OpenReview p.23, `L1325-L1326`） | `gepa.py:56` 默认 `num_dspy_examples_per_gepa_step=3` | 一致 | IFBench GEPA 的每步反思批量大小是 3。 |
| 候选选择规则 | 论文：GEPA 使用 Pareto-based sampling；`SelectBestCandidate` 是 ablation（OpenReview p.23, `L1322-L1326`） | `experiment_configs.py:124` 的 `GEPA` 用 `run_linearized_gepa=False`；`experiment_configs.py:140` 的 ablation 才是 `run_linearized_gepa=True` | 一致 | 正式 GEPA 不是线性“选当前最好”，而是 Pareto 路线。 |
| merge 策略 | 论文：GEPA+Merge 是单独变体，merge 最多 5 次（OpenReview p.23, `L1325-L1326`） | `experiment_configs.py:108` 的 `GEPA-MERGE` 开启 `use_merge=True`；`gepa.py:54-55` 默认 `max_merge_invocations=5` | 一致 | merge 不是默认 GEPA，而是单独配置。 |
| 最大迭代 / 停止条件 | 论文：不是固定 `num_iters`，而是按对齐后的 rollout budget 截断（OpenReview p.23, `L1330-L1334`） | `gepa.py:61-65` / `369` 允许三种停止条件，官方 GEPA 路径用的是 `max_metric_calls` | 一致 | IFBench 官方 GEPA 应按 `max_metric_calls=3593` 停止。 |
| temperature / top-p / top-k | 论文：Qwen3-8B 训练和推理都用 `temperature=0.6`、`top-p=0.95`、`top-k=20`（OpenReview p.22, `L1266-L1268`） | `experiment_configs.py:37-45` 完全相同 | 一致 | 这组解码参数可以作为 strict 目标协议。 |
| max_tokens / context window | 论文：推理允许最高 `16384` token（OpenReview p.22, `L1265`） | `run_experiments.py:59-63` 在 `create_lm()` 里硬编码 `max_tokens=16384` | 一致 | 论文 / artifact 目标口径是 16384；这与当前 DashScope 8192 上限构成确定性漂移。 |
| thinking / reasoning | 论文没有单独给出 Qwen3 的 `enable_thinking` 或 reasoning 开关 | artifact Qwen/Arbor 路线没有 `enable_thinking` 字段 | 未找到 | strict 协议里没有可直接映射到 DashScope `enable_thinking` 的纸面字段。 |
| 并发数 | 论文正文未给出 IFBench 专门线程数 | `generate_launch_commands.py:20` 默认 `num_threads = ... or 32` | 部分一致 | 当前只能确认 artifact 命令生成器默认用 32 线程。 |
| timeout / retry | 论文正文未给出 IFBench 超时设定 | `run_experiments.py:59-63` 把 `num_retries=0` 写死；未在 Qwen config 里看到显式 timeout | 部分一致 | retry 可确认为 0；timeout 未找到。 |
| 缓存行为 | 论文正文未描述缓存 | `experiment_configs.py:99/115` 设置 `use_cache_from_opt`；`run_experiments.py:111-135` 建立 `DSPY_CACHEDIR` 并允许从 Baseline / MIPRO 复制 cache | 部分一致 | artifact 明确有缓存与 cache reuse；论文正文没有说明。 |
| 论文报告的 Baseline / GEPA 分数 | Figure 9(b) 手工读数：Baseline `36.9`，GEPA `38.6` | 同图还能读到 MIPROv2 `36.2`、GRPO `35.9`、GEPA+Merge `28.2` | 一致 | IFBench/Qwen3 的论文主比较值是 **36.9 vs 38.6**，GEPA 提升 **+1.7**。 |
| 重复次数 / 均值 / 标准差 / 置信区间 | 论文正文和图注都未给出 | artifact 命令生成器默认 `SEEDS=[0]`；未见均值 / 方差统计代码 | 未找到 | 当前最稳妥的解读是**单 seed 单次运行**，而不是多次均值。 |

## 论文结果定位

- **IFBench 是否确实是论文中使用 Qwen3-8B 的 benchmark？**
  - 是。OpenReview `G.1` 明确列出 IFBench；`G.2` 明确说 open-source 路线使用 Qwen3-8B；Figure 9(b)、Figure 12、Figure 21 都出现 `IFBench, Qwen3 8B`。
- **论文分数在表还是图？**
  - IFBench/Qwen3 的最终 test score 在 **Figure 9(b)**，不是表格。
- **论文报告分数如何读取？**
  - Figure 9(b) 手工读数为：
    - Baseline：`36.9`
    - MIPROv2：`36.2`
    - GRPO（24000 rollouts）：`35.9`
    - GEPA：`38.6`
    - GEPA+Merge：`28.2`

## artifact 是否就是论文发布时版本

### 本地 git 证据

- `git rev-parse HEAD`：`cbefbc1aa0f43dd39874ec4bf42211365dbda42e`
- `git remote -v`：`https://github.com/gepa-ai/gepa-artifact`
- `git branch -vv`：当前在 `main`，跟踪 `origin/main`
- `git tag --list`：空
- `git log --reverse -n 5`：
  - 最早本地提交时间为 **2025-08-30**
  - 最新本地提交时间为 **2026-02-07**

### 已确认的发布后变更

- `2026-02-07` 的提交 `29220ba` / `cbefbc1` 修复了：
  - `Fix aliased list bug corrupting seed program's val subscores`
  - 变更文件：`gepa_artifact/gepa/gepa_utils.py`
  - 影响描述来自提交信息：修复 seed program 的 val subscores 与 pareto front 共用同一 list 对象的问题

### 判定

- **结论：不能把当前本地 artifact 直接视为“论文发布时冻结版本”。**
- 更准确的表述应是：
  - 当前本地 artifact 是 `gepa-ai/gepa-artifact` 的 **后续维护 HEAD 快照**
  - 它仍然是论文官方 artifact 仓库，但**不保证**与论文最初跑分时的 commit 完全一致
- 这意味着后续若要做 strict reproduction，需要先明确：
  1. 是以当前 HEAD `cbefbc1` 为基准
  2. 还是回退到更接近最初发布时的 commit

## 当前上游代码相对论文 artifact 的漂移

| 维度 | 论文 artifact | 当前 upstream-gepa | 审计结论 |
| --- | --- | --- | --- |
| 仓库角色 | 研究复现仓库，目标是跑论文 benchmark（`README.md:5`） | 通用库仓库，目标是 `pip install gepa` 和 `optimize_anything`（`README.md:55`、`111`） | 不是同一个产品层；不能做逐文件替代。 |
| 版本号 | `gepa_artifact 0.0.1`（`pyproject.toml:1-4`） | `gepa 0.1.1`（`pyproject.toml:11`） | 版本代际已发生变化。 |
| benchmark 支持 | 内置 IFBench 数据、程序、metric 和 `scripts/run_experiments.py` | README 只展示 AIME 示例；仓库里没有 IFBench benchmark harness | upstream 不能直接承担 strict IFBench 论文复现。 |
| 运行入口 | `scripts/generate_launch_commands.py` + `scripts/run_experiments.py` | `gepa.optimize` / `gepa.optimize_anything` / adapters | API 面完全不同。 |
| 依赖结构 | 依赖修改版 DSPy 和 Arbor，本地 inference / GRPO 需要 Arbor，GEPA 路径默认带 W&B | `dependencies = []`，以可选 extras 扩展；不再内置 Arbor 路径 | 后端、环境和部署模型都发生漂移。 |
| 反思默认值 | artifact `GEPA` 默认 `skip_perfect_score=True`、`num_dspy_examples_per_gepa_step=3` | upstream `ReflectionConfig.skip_perfect_score=False`，`reflection_minibatch_size` 动态决定 | 默认优化行为存在漂移。 |
| `max_tokens` 处理 | runner 里硬编码 `16384`（`run_experiments.py:59`） | upstream `optimize_anything` 不把 16384 写死在仓库顶层入口 | 当前 DashScope 8192 适配必须经 wrapper 层单独处理。 |
| artifact 引用 | 无 | upstream README 反向把 `gepa-artifact` 当作单独“Experiment reproduction artifact”链接出去（`README.md:364`） | upstream 自己也承认论文复现应回到 artifact 仓库。 |

## 当前最关键的阻断项

### 1. train / val 协议冲突未解决

- 论文：`150 train / 300 val / 294 test`
- artifact：`300 train / 300 val / 294 test`
- 影响：
  - 这不是小漂移，而是**训练数据规模翻倍**
  - 会直接影响 MIPRO rollout 数、GEPA budget、验证集泛化与最终 test 分数
- 在这个问题解决前：
  - **不能**把基于 artifact 当前 loader 的 DashScope run 称为 strict reproduction

### 2. artifact 不是冻结版本

- 当前 checkout 是 2026-02-07 的维护版 HEAD。
- 需要先决定：
  - 以当前 HEAD 为准，做 **artifact-head backend-adapted reproduction**
  - 还是回退到更早 commit，做 **paper-era snapshot reproduction**

### 3. 后端能力存在确定性不一致

- 论文 / artifact：Arbor 本地 Qwen3-8B，`max_tokens=16384`
- 当前计划：DashScope OpenAI-compatible Qwen3-8B，已知上限 `8192`
- 即便其他项都一致，**这也至少是 backend drift**，不能默认叫 strict reproduction

### 4. 缺少论文原始正式 run 产物

- 当前本地 `experiment_runs_data/experiment_runs` 里只看到了我们自己的 adapted IFBench 目录。
- 没有看到可直接比对的论文 IFBench/Qwen3 正式 run 目录、`config.json`、`evaluation_result.txt` 或 `metric_logs/test.jsonl`。
- 因此很多字段只能从论文正文 + 代码推断，不能从“历史官方 run manifest”二次确认。

## 阶段门禁结论

### strict reproduction

- **当前结论：不满足启动条件**
- 原因：
  1. `150/300/294` vs `300/300/294` 冲突未解决
  2. artifact 版本未冻结
  3. `16384` vs `8192` 后端漂移未分类完成

### backend-adapted reproduction

- **当前结论：可以继续准备，但还不该正式开跑**
- 先决条件：
  1. 明确采用哪个 artifact commit
  2. 明确是否接受“以当前 artifact loader 为准”的数据协议
  3. 完成 DashScope API 可行性审计，把 8192 / thinking / top_k / stop / retry / timeout 一项项归类

### method-level reproduction

- **当前结论：已经具备基本可行性**
- 说明：
  - 现有 smoke / 小 benchmark 已经证明 DashScope Qwen3 + IFBench wrapper 管线可跑通
  - 但那条线只能支撑“方法级、后端适配过的局部验证”，不能替代论文 benchmark 复现

## 最小下一步

1. **先冻结实验基线**
   - 选定 `cbefbc1` 还是更早 commit 作为后续全部 IFBench 复现实验的唯一代码基线。
2. **优先解决数据协议冲突**
   - 继续查论文附录、仓库 issue / commit、或作者说明，确认 `150 train` 是否是正文笔误、早期脚本逻辑，还是当前 artifact 漂移。
3. **再做 DashScope 后端可行性审计**
   - 逐项核对：模型版本、tokenizer / chat template、`enable_thinking`、`max_tokens`、`top_k`、stop、structured output、timeout / retry / 并发 / 缓存。
4. **在上述三步完成前，不启动正式 Baseline / GEPA 大预算 run**
   - 否则得到的结果最多只能写成“未冻结协议下的 adapted run”，不具备严格可比性。
