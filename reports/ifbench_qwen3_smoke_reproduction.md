# IFBench Qwen3 小 benchmark 复现记录

时间：2026-06-07 21:24:00 +0800

## 复现口径

- 实验性质：`artifact_ifbench_dashscope_qwen3_adapted_baseline_smoke`。
- 复用对象：官方 GEPA artifact 的 IFBench 数据、两阶段 DSPy 程序、metric 与 `scripts/run_experiments.py`。
- 后端模型：DashScope OpenAI-compatible `qwen3-8b`。
- 默认规模：Baseline optimizer，由 wrapper 显式截断为 train/val/test 各 2 条样本。
- 重要边界：这不是论文 strict 复现。论文 artifact 的 Qwen 配置是本地 Arbor `openai/arbor:qwen/qwen3-8b`，本记录使用 API 适配路径。

## 可重复运行入口

脚本：`scripts/run_ifbench_qwen3_smoke.py`

推荐在 artifact 环境中运行：

```powershell
cd "C:\Users\lin\Documents\New project 2\.codex\gepa-artifact"
$env:PYTHONUTF8 = "1"
$env:QWEN_API_KEY = "<临时 Qwen 或 DashScope API key>"
uv run --no-sync python ..\..\scripts\run_ifbench_qwen3_smoke.py --yes --force
```

如只做环境检查，不启动 benchmark：

```powershell
cd "C:\Users\lin\Documents\New project 2\.codex\gepa-artifact"
$env:PYTHONUTF8 = "1"
$env:QWEN_API_KEY = "<临时 Qwen 或 DashScope API key>"
uv run --no-sync python ..\..\scripts\run_ifbench_qwen3_smoke.py --preflight-only
```

运行 GEPA tiny：

```powershell
cd "C:\Users\lin\Documents\New project 2\.codex\gepa-artifact"
$env:PYTHONUTF8 = "1"
$env:QWEN_API_KEY = "<临时 Qwen 或 DashScope API key>"
uv run --no-sync python ..\..\scripts\run_ifbench_qwen3_smoke.py --optimizer GEPA --max-metric-calls 8 --yes --force
```

运行可比较小 benchmark：

```powershell
cd "C:\Users\lin\Documents\New project 2\.codex\gepa-artifact"
$env:PYTHONUTF8 = "1"
$env:QWEN_API_KEY = "<临时 Qwen 或 DashScope API key>"
uv run --no-sync python ..\..\scripts\run_ifbench_qwen3_smoke.py --yes --force --lm-name qwen3-8b-dashscope-ifbench-t10-v10-e20-t150 --train-size 10 --val-size 10 --test-size 20 --request-timeout-seconds 150 --process-timeout-seconds 1200
uv run --no-sync python ..\..\scripts\run_ifbench_qwen3_smoke.py --yes --force --lm-name qwen3-8b-dashscope-ifbench-t10-v10-e20-t150 --optimizer GEPA --max-metric-calls 30 --train-size 10 --val-size 10 --test-size 20 --request-timeout-seconds 150 --process-timeout-seconds 2400
```

## 防故障机制

- API key 只从环境变量读取，不写入 `lm_config`。
- 默认 `enable_thinking=false`，不启用 streaming。
- 默认 `max_tokens=8192`，匹配当前 `qwen3-8b` API 上限。
- 父进程设置 `--process-timeout-seconds`，worker 超时会被终止并返回错误。
- 运行后扫描输出目录，若发现当前 API key 落盘则失败。
- GEPA tiny 额外适配：`skip_perfect_score=false`、proposer `max_tokens=8192`、W&B 实际禁用。
- wrapper 支持 `--train-size`、`--val-size`、`--test-size`，避免继续被 artifact `--dry_run` 固定为 2 条。

## 当前 smoke 结果

已有结果目录：

`C:\Users\lin\Documents\New project 2\.codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-smoke`

结果摘要（2026-06-07 21:22 复跑）：

- `score=0.0`
- `cost=0`
- `input_tokens=1588`
- `output_tokens=1495`
- test metric log：2 条
- worker 评估阶段约 23 秒完成 2 条样本
- 父进程总耗时约 69 秒，包含模型探针、依赖检查和结果扫描
- 模型探针：通过，返回 `OK`
- `config.json` 检查：`lm_config` 不含 `api_key`，`enable_thinking=false`
- 运行后密钥落盘扫描：`secret_scan_matches=0`

解释：

- 该结果证明 IFBench artifact runner、Qwen3 DashScope 后端、结果写出和 metric log 管线可跑通。
- 该结果不证明 GEPA 优化有效，因为它是 Baseline dry-run，不包含 prompt evolution。
- 若要做 GEPA tiny，小实验应另开显式入口，先把 W&B 注入和 `max_metric_calls=3593` 预算改为可控 tiny 配置。

## GEPA tiny 结果

结果目录：

`C:\Users\lin\Documents\New project 2\.codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_GEPA-Tiny_qwen3-8b-dashscope-smoke`

结果摘要（2026-06-07 22:00 复跑）：

- optimizer：`GEPA-Tiny`
- `max_metric_calls=8`
- 模型探针：通过，返回 `OK`
- 编译阶段：执行 1 次有效 proposer 尝试，新 subsample score 为 `2.0`，未优于 seed subsample score `3.0`
- 最终 test score：`0.0`
- test metric log：2 条
- 父进程总耗时约 54 秒
- `config.json` 检查：`lm_config` 不含 `api_key`，`enable_thinking=false`
- 运行后密钥落盘扫描：`secret_scan_matches=0`

修复记录：

- 第一次 GEPA tiny 使用 `max_metric_calls=8` 但保留 `skip_perfect_score=true`，在满分子样本上反复 `No feedback samples`，已中止。
- 第二次改用 `num_iters=2`，但 artifact 的 `num_iters` 实际依赖 `num_full_ds_evals`，候选不进入 full eval 时不会增长，仍会循环，已中止。
- 第三次发现 proposer 内部硬编码 `max_tokens=16384`，被当前 Qwen3 API 拒绝，已改为 wrapper 层 `max_tokens=8192`。
- 最终可运行设置为：`max_metric_calls=8`、`skip_perfect_score=false`、proposer `max_tokens=8192`、W&B 禁用。

解释：

- GEPA tiny 管线已经跑通，但本次没有产生优于 seed 的候选，最终 test 分数仍为 `0.0`。
- 因为这是 2 条样本 dry-run + 8 次 metric 调用级别的微型实验，不能用来判断 GEPA 在 IFBench 上的真实优化能力。

## 10/10/20 小 benchmark 对照结果

共同设置：

- 后端：DashScope OpenAI-compatible `qwen3-8b`。
- split：train=10、val=10、dev=10、test=20。
- seed：0。
- temperature：0.6。
- top_p：0.95。
- top_k：20。
- max_tokens：8192。
- enable_thinking：false。
- streaming：未启用。
- request timeout：150 秒。

Baseline 结果：

- run：`C:\Users\lin\Documents\New project 2\.codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-ifbench-t10-v10-e20-t150`
- score：`20.0`
- metric rows：20。
- input_tokens：`16244`
- output_tokens：`14906`
- duration_seconds：约 `286.167`
- stderr：无 timeout traceback，仅最终 INFO。
- secret_scan_matches：0。

GEPA-Tiny 结果：

- run：`C:\Users\lin\Documents\New project 2\.codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_GEPA-Tiny_qwen3-8b-dashscope-ifbench-t10-v10-e20-t150`
- optimizer：`GEPA-Tiny`
- max_metric_calls：30。
- base full valset score：`65.0`
- proposer 尝试：4 次有效候选尝试，subsample score 分别为 `1.0`、`1.0`、`2.0`、`0.0`，均未优于 seed。
- 接受候选：0 个；`prog_candidates` 只有 seed candidate `0`。
- final test score：`20.0`
- metric rows：20。
- optimizer_input_tokens：`32764`
- optimizer_output_tokens：`21199`
- duration_seconds：约 `207.628`
- stderr：无 timeout traceback，仅 INFO。
- secret_scan_matches：0。

解释：

- 这组结果可以比较 Baseline 与 GEPA-Tiny 的最终 IFBench score，因为它们使用同模型、同 seed、同 split、同推理参数，只有 optimizer 与 GEPA 预算不同。
- 本轮 GEPA-Tiny 没有接受任何新候选，因此最终 prompt 等价于 seed，test score 与 Baseline 持平是预期结果，不代表 GEPA 已经有效优化。
- GEPA-Tiny 的 final eval token 统计为 `0/0`，原因是最终程序未变化且 test 调用命中缓存；因此 score 可比，但 final eval token/cost 不能与 Baseline 直接比较。
- 75 秒请求超时诊断版 Baseline 曾出现 1 个单样本 `APITimeoutError`，150 秒对照组没有复现该 timeout，说明 Qwen3 没有 GLM/MiMo 那类长收尾问题，但 IFBench 某些样本在较紧 timeout 下会超时。

## b80 预算阶梯结果

目的：

- 在不扩大 split 的前提下，只把 GEPA-Tiny 的 `max_metric_calls` 从 30 提到 80，判断前一轮未优化是否只是预算不足。

共同设置：

- 后端：DashScope OpenAI-compatible `qwen3-8b`。
- split：train=10、val=10、dev=10、test=20。
- seed：0。
- request timeout：150 秒。
- enable_thinking：false。
- streaming：未启用。
- max_tokens：8192。

结果：

- run：`C:\Users\lin\Documents\New project 2\.codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_GEPA-Tiny_qwen3-8b-dashscope-ifbench-t10-v10-e20-t150-b80`
- max_metric_calls：80。
- base full valset score：`65.0`。
- 候选尝试：10 次。
- 接受候选：2 个，`prog_candidates` 包含 `0`、`1`、`2`。
- 接受点：Iteration 9 和 Iteration 10。
- best valset score：从 `65.0` 提升到 `75.0`。
- final test score：`20.0`。
- metric rows：20。
- final eval input/output tokens：`20703 / 17911`。
- optimizer input/output tokens：`50403 / 24439`。
- duration_seconds：约 `499.633`。
- timeout：未见 timeout traceback。
- secret_scan_matches：0。

解释：

- b80 证明 GEPA 优化循环已经有效工作：预算升高后确实接受了新候选，并把 val score 提高了 10 分。
- b80 仍未提升 test score，说明当前小 split 上出现了 val 改善但 test 未泛化；这更像小样本/验证集过拟合或 IFBench prompt 提案泛化不足，而不是 runner 无效。
- 下一步不应盲目只加预算；更合理的是扩大 split 或多 seed，确认 `val +10` 是否能稳定转化为 test 提升。

## 20/20/50 b120 小 benchmark 对照结果

目的：

- 在 b80 已证明候选接受有效的基础上，扩大 split 到 train=20、val=20、test=50。
- 保持同一个 DashScope Qwen3 后端、seed 与推理参数，比较 Baseline 与 GEPA-Tiny 的最终 test score。
- 继续使用小 benchmark 口径，避免直接进入论文级大预算实验。

共同设置：

- 后端：DashScope OpenAI-compatible `qwen3-8b`。
- split：train=20、val=20、dev=20、test=50。
- seed：0。
- temperature：0.6。
- top_p：0.95。
- top_k：20。
- max_tokens：8192。
- enable_thinking：false。
- streaming：未启用。
- request timeout：240 秒。
- DSPy parallel straggler timeout：0，禁用尾部重提交，避免重复慢请求。

Baseline 结果：

- run：`C:\Users\lin\Documents\New project 2\.codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-ifbench-t20-v20-e50-t240-b120`
- score：`35.0`。
- metric rows：50。
- input/output tokens：`42729 / 41927`。
- duration_seconds：约 `711.151`。
- stderr：仅 INFO；未见 timeout 或 rate-limit。
- secret_scan_matches：0。

GEPA-Tiny 结果：

- run：`C:\Users\lin\Documents\New project 2\.codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_GEPA-Tiny_qwen3-8b-dashscope-ifbench-t20-v20-e50-t240-b120`
- optimizer：`GEPA-Tiny`。
- max_metric_calls：120。
- base full valset score：`67.5`。
- 接受候选：2 个，`prog_candidates` 包含 `0`、`1`、`2`。
- 接受点：Iteration 2 和 Iteration 11。
- best valset score：`82.5`。
- final test score：`44.0`。
- metric rows：50。
- final eval input/output tokens：`43643 / 29191`。
- optimizer input/output tokens：`67391 / 33444`。
- stderr：有 1 次 DSPy signature 解析失败 traceback；未见 timeout 或 rate-limit。该 traceback 来自候选/样本输出格式不匹配，被评估流程作为失败样本处理，不是 API 层硬失败。
- secret_scan_matches：0。

解释：

- 这组 Baseline 与 GEPA-Tiny final score 可比较：同模型、同 seed、同 split、同采样参数、同 request timeout，区别只在 optimizer 和 GEPA 预算。
- GEPA-Tiny 在更大的 20/20/50 split 上观察到 test 提升：`35.0 -> 44.0`，提升 `+9.0` 分。
- 优化阶段也不是空跑：GEPA 接受了 2 个新候选，best valset score 达到 `82.5`。
- 该结果支持继续做小 benchmark 复现；但它仍是 DashScope Qwen3 adapted IFBench 结果，不等同于论文 strict Arbor Qwen 复现。

## 20/20/50 b120 多 seed 复核结果

目的：

- 复核 seed0 的正向提升是否只是单次随机性。
- 保持同一个 DashScope Qwen3 adapted IFBench 协议，串行运行 seed=1 和 seed=2。
- 每个 run 必须通过结果文件、metric 行数、硬失败标记、密钥形态扫描和残留进程门禁。

共同设置：

- 后端：DashScope OpenAI-compatible `qwen3-8b`。
- lm_name：`qwen3-8b-dashscope-ifbench-t20-v20-e50-t240-b120`。
- split：train=20、val=20、dev=20、test=50。
- max_metric_calls：120。
- request timeout：240 秒。
- parallel straggler timeout：0，禁用尾部重提交。
- enable_thinking：false。
- streaming：未启用。
- GEPA 额外：`--num-retries 2`、`--lm-call-sleep-seconds 2.0`。

结果表：

| seed | Baseline test | GEPA-Tiny test | delta | GEPA base val | GEPA best val | 接受候选 | 候选目录 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 0 | 35.0 | 44.0 | +9.0 | 67.5 | 82.5 | 2 | `0,1,2` |
| 1 | 35.0 | 43.0 | +8.0 | 60.0 | 87.5 | 3 | `0,1,2,3` |
| 2 | 35.0 | 43.0 | +8.0 | 48.33 | 75.83 | 2 | `0,1,2` |

汇总：

- Baseline 均值：`35.0`。
- GEPA-Tiny 均值：`43.33`。
- 平均 delta：`+8.33`。
- delta 总体标准差：约 `0.47`。
- 三个 seed 的方向一致，均为正向提升。

门禁检查：

- 三个 seed 的 Baseline 和 GEPA-Tiny `metric_logs/test.jsonl` 均为 50 行。
- 三个 seed 的 `run_log_stderr.txt` 均未命中硬失败标记：`litellm.Timeout`、`APITimeoutError`、`ReadTimeout`、`RateLimitError`、`exceeded your current request limit`。
- 三个 seed 的 b120 run 目录密钥形态扫描均为 0 命中。
- 最终 `list_sessions`：无残留实验进程。
- seed1 和 seed2 的 Baseline 命中缓存，因此 score 可比，token/cost 不应与未缓存 Baseline 直接比较。

解释：

- 这组多 seed 复核支持“当前 Qwen3 adapted IFBench 小 benchmark 中，GEPA-Tiny 的 test 提升不是 seed0 偶然结果”。
- 这不是论文 strict Arbor Qwen 复现。论文 artifact 的 Qwen 路线是本地 Arbor `openai/arbor:qwen/qwen3-8b`，本报告使用 DashScope OpenAI-compatible API 后端。
- 当前 seed 主要改变优化过程随机性和 run 目录，不是重新抽取不同 train/val/test 内容；更严格的稳健性复核应增加不同 split 抽样或扩大测试集。
- 与 GLM/MiMo 长收尾问题相比，Qwen3 本轮没有出现 timeout、rate-limit 或长尾无限挂起。seed2 final test 最慢样本约 45 秒，仍在 240 秒请求 timeout 内完成。

本地验证：

- `python -m pytest tests/test_ifbench_qwen3_smoke.py -q --basetemp ".codex\tmp\pytest-basetemp" -p no:cacheprovider`：14 passed。
- `python -m compileall scripts/run_ifbench_qwen3_smoke.py tests/test_ifbench_qwen3_smoke.py`：通过，退出码 0。
- 独立密钥形态扫描：扫描 134 个文本文件，0 matches。
- `list_sessions`：无残留实验进程。

## 跨数据 split=1 复核结果

目的：

- 修正此前多 seed 只改变优化随机性、没有改变 train/val/test 内容的协议边界。
- 固定 optimizer seed=0，只改变 `split_seed=1`，检验 `+8/+9` 提升是否能迁移到另一组样本。
- 保持官方 IFBench 池边界：训练文件 `0:300` 为 val 池、`300:600` 为 train 池，test 使用独立的 294 条测试文件。

实现与可比性：

- wrapper 新增可选 `--split-seed`；未提供时继续使用原有前缀截断，避免改变历史实验。
- 提供 split seed 时，train、val、test 分别使用 SHA-256 派生的独立随机种子确定性打乱，再截取 20/20/50 条。
- 每个 run 写入 `split_manifest.json`，记录池大小、原始索引和样本键。
- Baseline 与成功 GEPA run 的 train/val/test 原始索引和样本键逐项完全一致。
- GEPA 使用短 `lm_name=q3-ifb-x1`，仅用于规避 Windows 260 字符路径限制；实际传给 `dspy.LM` 的模型、API base、采样参数和超时设置均未改变，因此 final score 仍可与 Baseline 比较。

共同设置：

- 后端：DashScope OpenAI-compatible `qwen3-8b`
- optimizer seed：`0`
- split seed：`1`
- split：train=20、val=20、dev=20、test=50
- `max_metric_calls=120`
- request timeout：240 秒
- parallel straggler timeout：0
- `enable_thinking=false`
- streaming：未启用

结果：

| 项目 | Baseline | GEPA-Tiny |
| --- | ---: | ---: |
| final test score | 36.0 | 37.0 |
| test metric rows | 50 | 50 |
| base val score | - | 53.33 |
| best val score | - | 88.33 |
| 接受候选 | - | 1 |

- test delta：`+1.0`
- GEPA final eval input/output tokens：`42009 / 31322`
- GEPA optimizer input/output tokens：`106453 / 90660`
- GEPA 运行时间：约 `2025.704` 秒
- 两个正式 run 的 timeout、rate-limit、request-limit 硬失败命中均为 0。
- GEPA stderr 有 3 组 DSPy traceback，来源是候选或样本输出无法满足 DSPy signature；它们是输出格式质量信号，不是 API 传输故障。

Windows 长路径诊断：

- 首次 GEPA 使用完整长标签时，在写入 `generated_best_outputs_valset/task_0/iter_0_prog_0.json` 阶段失败。
- 失败目标路径长度为 266，超过 Windows 传统 `MAX_PATH=260`；历史成功 run 的对应最深路径为 248。
- wrapper 已增加 GEPA 路径长度预检，在任何 API 调用前拒绝危险路径，并提示缩短 `--lm-name`。
- 使用短标签重跑后完整生成结果、50 条 test metric、优化程序和 split manifest。

结论：

- GEPA 在新数据内容上仍未低于 seed prompt，但提升从固定前缀协议的平均 `+8.33` 缩小到 `+1.0`。
- val 从 `53.33` 提升到 `88.33`，test 只提升 `1.0`，存在明显的验证集到测试集泛化缺口。
- 这证明 wrapper 和优化循环不是无效改动，同时削弱了“GEPA 在当前小 benchmark 上稳定大幅提升”的结论。
- 下一步应先运行 `split_seed=2` 的同规模复核；在至少两个独立数据 split 都得到正向结果前，不应增加预算或宣称稳定复现论文收益。
- 实验仍属于 DashScope Qwen3 adapted IFBench 小 benchmark，不是论文 strict Arbor Qwen 复现。

最终本地门禁：

- `python -m pytest tests/test_ifbench_qwen3_smoke.py -q --basetemp .codex\tmp\pytest-split-seed-final -p no:cacheprovider`：`22 passed`
- `python -m compileall scripts/run_ifbench_qwen3_smoke.py tests/test_ifbench_qwen3_smoke.py`：通过
- 独立密钥形态扫描：60 个相关文件，0 命中
- `list_sessions`：无活跃实验会话

## 跨数据 split=2 复核结果（恢复后）

目的：

- 在 `split_seed=2` 上完成与 `split_seed=1` 同口径的 20/20/50 复核。
- 对已经完成优化、但 final test eval 缺 1 条 metric row 的 GEPA run 做本地恢复。
- 明确区分“优化阶段有效”和“最终可比结果是否完整”。

共同设置：

- 后端：DashScope OpenAI-compatible `qwen3-8b`
- optimizer seed：`0`
- split seed：`2`
- split：train=20、val=20、dev=20、test=50
- `max_metric_calls=120`
- request timeout：240 秒
- `enable_thinking=false`
- `top_k=20`
- `max_tokens=8192`
- GEPA 额外控制：`--num-retries 2`、`--lm-call-sleep-seconds 2.0`

Baseline：

- run：`C:\Users\lin\Documents\New project 2\.codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_Baseline_q3-ifb-x2-split2`
- final test score：`39.0`
- test metric rows：`50/50`
- input/output tokens：`38057 / 52958`
- 无 timeout、rate-limit、request-limit 硬失败标记

GEPA-Tiny 原始 run：

- source run：`C:\Users\lin\Documents\New project 2\.codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_GEPA-Tiny_q3-ifb-x2-split2`
- base val score：`70.0`
- best val score：`92.5`
- 原始 `evaluation_result.txt`：`24.0`
- 原始 `metric_logs/test.jsonl`：`49/50`
- 缺失样本：`idx_in_split=19`，`example_key=219`
- 原始 stderr 证据：DSPy parse error，而不是 transport timeout / rate-limit

GEPA-Tiny 恢复 final eval：

- recovery run：`C:\Users\lin\Documents\New project 2\.codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_GEPA-Tiny_q3-ifb-x2-split2-recovered-final-eval`
- 恢复方式：直接加载 source run 的 `evaluation_results/optimized_program`，不重跑 GEPA 优化阶段，只重做 final test eval
- 恢复结果：`score=24.0`
- test metric rows：`50/50`
- `recovery_metadata.backfilled_metric_rows=1`
- 回填记录：对 `idx_in_split=19 / example_key=219` 显式补写 `metric_output=0`
- 说明：原始 DSPy `Average Metric: 12.0 / 50 (24.0%)` 已经把该失败样本按 0 分计入总分，因此回填只补全日志行数，不改变分数
- 恢复 run 的 final eval `input/output tokens = 0 / 0`
- 解释：恢复阶段命中缓存，因此 token/cost 不能与未命中缓存的 Baseline 直接比较

可比性说明：

- Baseline 与 recovery run 共享同一 `split_manifest.json`、同一模型后端、同一采样参数、同一 `max_tokens=8192`、同一超时设置。
- GEPA-Tiny 的 optimizer token 仍沿用 source run：`118620 / 48977`。
- final eval 的唯一恢复性处理，是把 DSPy 丢失的 parse-error 样本显式记为 0 分失败行，以补齐 `50/50` metric rows。

结果表：

| 项目 | Baseline | GEPA-Tiny（recovered final eval） |
| --- | ---: | ---: |
| final test score | 39.0 | 24.0 |
| test metric rows | 50 | 50 |
| base val score | - | 70.0 |
| best val score | - | 92.5 |
| test delta | - | `-15.0` |

结论：

- `split_seed=2` 的 Baseline 完整有效。
- `split_seed=2` 的 GEPA-Tiny 经过恢复后也形成了完整 `50/50` final eval，但结果明显低于 Baseline：`39.0 -> 24.0`。
- 这说明此前固定前缀 / 多 optimizer seed 口径下观察到的正向提升，并没有稳定迁移到新的数据 split。
- 结合 `split_seed=1` 仅 `+1.0` 的结果，当前更准确的结论应是：在 DashScope Qwen3 adapted IFBench 小 benchmark 上，GEPA 的收益对数据内容高度敏感，尚不能宣称稳健复现论文中的正向收益。

本地验证：

- `python -m pytest tests/test_ifbench_qwen3_smoke.py -q --basetemp .codex\tmp\pytest-ifbench-recovery-2 -p no:cacheprovider`：`29 passed`
- `python -m compileall scripts/run_ifbench_qwen3_smoke.py tests/test_ifbench_qwen3_smoke.py`：通过
- `python scripts\run_ifbench_qwen3_smoke.py --yes --skip-probe --force --recover-run-dir .codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_GEPA-Tiny_q3-ifb-x2-split2 --num-threads 1 --max-tokens 8192 --request-timeout-seconds 240 --process-timeout-seconds 10800 --num-retries 2 --lm-call-sleep-seconds 2.0 --parallel-straggler-timeout-seconds 0`：恢复成功
- 密钥形态扫描：`rg -n "sk-[A-Za-z0-9]{20,}" reports scripts tests .codex`：`0` 命中


## 跨数据 split=3 复核结果（恢复后）

目的：

- 继续使用云 API adapted 路线，验证 GEPA-Tiny 在第三个独立数据 split 上是否仍优于 Baseline。
- 保持 `split_seed=3`、optimizer seed=0、train=20、val=20、test=50、`max_metric_calls=120`。
- 对 GEPA source run 中缺失的 1 条 final eval metric row 做 recovery，形成完整 `50/50` 审计链。

共同设置：

- 后端：DashScope OpenAI-compatible `qwen3-8b`
- optimizer seed：`0`
- split seed：`3`
- split：train=20、val=20、dev=20、test=50
- `max_metric_calls=120`
- request timeout：240 秒
- `enable_thinking=false`
- `top_k=20`
- `max_tokens=8192`
- GEPA 额外控制：`--num-retries 2`、`--lm-call-sleep-seconds 2.0`

Baseline：

- run：`C:\Users\lin\Documents\New project 2\.codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_Baseline_q3-ifb-x3-split3`
- final test score：`49.0`
- test metric rows：`50/50`
- input/output tokens：`32701 / 33019`
- 无 timeout、rate-limit、request-limit 硬失败标记

GEPA-Tiny 原始 run：

- source run：`C:\Users\lin\Documents\New project 2\.codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_GEPA-Tiny_q3-ifb-x3-split3`
- base val score：`55.0`
- best accepted program val score：`67.5`
- 接受候选：2 个，`prog_candidates` 包含 `0`、`1`、`2`
- 接受点：Iteration 3 和 Iteration 6
- 原始 `evaluation_result.txt`：`40.0`
- 原始 `metric_logs/test.jsonl`：`49/50`
- 原始 stderr 证据：DSPy signature parse error，而不是 transport timeout / rate-limit

GEPA-Tiny 恢复 final eval：

- recovery run：`C:\Users\lin\Documents\New project 2\.codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_GEPA-Tiny_q3-ifb-x3-split3-recovered-final-eval`
- 恢复方式：直接加载 source run 的 `evaluation_results/optimized_program`，不重跑 GEPA 优化阶段，只重做 final test eval
- 恢复结果：`score=40.0`
- test metric rows：`50/50`
- `recovery_metadata.backfilled_metric_rows=1`
- 说明：原始 DSPy `Average Metric: 20.0 / 50 (40.0%)` 已经把失败样本按 0 分计入总分，因此 recovery 补齐日志行数，不改变分数
- 恢复 run 的 final eval `input/output tokens = 0 / 0`
- 解释：恢复阶段命中缓存，因此 token/cost 不能与未命中缓存的 Baseline 直接比较

结果表：

| 项目 | Baseline | GEPA-Tiny（recovered final eval） |
| --- | ---: | ---: |
| final test score | 49.0 | 40.0 |
| test metric rows | 50 | 50 |
| base val score | - | 55.0 |
| best accepted program val score | - | 67.5 |
| test delta | - | `-9.0` |

跨 split 汇总：

| split seed | Baseline test | GEPA-Tiny test | delta | GEPA base val | GEPA best val |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 36.0 | 37.0 | +1.0 | 53.33 | 88.33 |
| 2 | 39.0 | 24.0 | -15.0 | 70.0 | 92.5 |
| 3 | 49.0 | 40.0 | -9.0 | 55.0 | 67.5 |

跨 split 均值：

- Baseline test 均值：`41.33`
- GEPA-Tiny test 均值：`33.67`
- 平均 delta：`-7.67`

结论：

- `split_seed=3` 的 GEPA 优化阶段确实有效发生：接受了 2 个候选，并把 accepted-program val score 从 `55.0` 提升到 `67.5`。
- 但恢复后的 final test 低于 Baseline：`49.0 -> 40.0`，delta 为 `-9.0`。
- 结合 `split_seed=1` 的 `+1.0` 与 `split_seed=2` 的 `-15.0`，当前最准确结论是：在 DashScope Qwen3 adapted IFBench 20/20/50 小 benchmark 上，GEPA 能优化验证集，但 test 收益对数据 split 很敏感，尚不能宣称“云 API 路线下 GEPA 在 IFBench 上稳健有效”。
- 这不否定 GEPA 方法本身，也不等同论文 strict 复现失败；它说明当前 adapted 小样本设置还不足以复现论文中稳定正向收益。

本地验证：

- `python scripts\run_ifbench_qwen3_smoke.py --yes --skip-probe --force --recover-run-dir .codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_GEPA-Tiny_q3-ifb-x3-split3 --num-threads 1 --max-tokens 8192 --request-timeout-seconds 240 --process-timeout-seconds 10800 --num-retries 2 --lm-call-sleep-seconds 2.0 --parallel-straggler-timeout-seconds 0 --recovery-tag recovered-final-eval`：恢复成功
- recovery summary：`metric_rows=50`、`score=40.0`、`backfilled_metric_rows=1`
- 密钥形态扫描：`rg -n "sk-[A-Za-z0-9]{20,}" reports scripts tests .codex`：`0` 命中（`rg` 退出码 1，无输出）
- `git diff --check`：退出码 `0`；仅有既有 LF/CRLF warning，无新增空白错误
