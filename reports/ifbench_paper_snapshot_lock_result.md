# IFBench 论文快照锁定与 strict 复现结果

生成时间：2026-06-09 12:54:14 +08:00

## 结论

本轮已经把论文 artifact 路线从当前 DashScope adapted 路线中隔离出来，并锁定到官方公开 artifact 的最早完整快照候选：`gepa-ai/gepa-artifact@5f7edbae7f380bedccce2a670bbeba2deb2fd2a3`。静态协议可以锁定，IFBench/Qwen/GEPA budget 也可以追溯；但 strict runtime 当前不能启动，状态为 `blocked`，不能宣称已经复现完整论文 benchmark。

阻塞点已经被拆清楚：真实 Git LFS 数据包 payload 不可下载、快照自身没有 `uv.lock`、全量 launch command 生成会先被 hover 数据集加载阻塞、本机 Python/Torch 不可见 CUDA，且 artifact 运行代码对 Arbor 路径和入口环境变量还有额外限制。因此本轮正确动作是停在 strict blocked 报告，而不是回退 DashScope 或继续消耗 API。

## 快照锁定

| 项目 | 锁定值 | 本地核验 |
| --- | --- | --- |
| artifact | `5f7edbae7f380bedccce2a670bbeba2deb2fd2a3` | `git rev-parse HEAD` 通过 |
| DSPy fork | `62dc3b634d7dc0c4889abcf905cb4c391ea6b396` | detached HEAD，状态干净 |
| Arbor fork | `113fc35e05acbf2796a5917ec3b45ab44bfacd0b` | detached HEAD，状态干净 |
| 数据包指针 SHA256 | `0C7AC976F926BF08B5BBD75410362F16CDA2D899AF8969965A8FD4630E264535` | `Get-FileHash` 通过 |
| 真实 LFS payload oid | `sha256:0e1db10331bbbdd48701443b0690d5b7b8abef841a73b76882d26853b3f38dd7` | 远端缺对象，无法下载 |
| 真实 LFS payload size | `1931042598` | 来自 LFS 指针内容 |

说明：`.codex/gepa-paper-snapshot` 是新建隔离目录，未修改现有 `.codex/gepa-artifact`。最早完整 artifact 快照没有论文发布日期 tag，因此该 commit 只能称为“官方公开 artifact 最早完整快照候选”，不能称为论文当天 tag。

## 数据包状态

`experiment_runs_data.tar.gz` 在该快照中是 Git LFS 指针文件，不是真实 tar 包。此前普通 checkout 曾因远端缺少真实对象 `0e1db10331bbbdd48701443b0690d5b7b8abef841a73b76882d26853b3f38dd7` 失败，本轮改用 `GIT_LFS_SKIP_SMUDGE=1` 成功检出指针。

曾尝试从当前 `.codex/gepa-artifact/experiment_runs_data` 复用已解压目录，但该目录已经混入当前 DashScope adapted 后续运行结果，例如 `qwen3-8b-dashscope-*` 与 `_backup_*` 目录。为避免污染 strict 快照，本轮没有把这些运行输出保留在 `.codex/gepa-paper-snapshot/experiment_runs_data` 中。快照仓库自带的 IFBench 原始数据文件仍存在：

| 文件 | 状态 | 行数 |
| --- | --- | --- |
| `gepa_artifact/benchmarks/IFBench/data/IFBench_train.jsonl` | 存在 | `14971` |
| `gepa_artifact/benchmarks/IFBench/data/IFBench_test.jsonl` | 存在 | `294` |

## 论文快照配置核对

| 字段 | 论文 artifact 快照 |
| --- | --- |
| LM name | `qwen3-8b` |
| model | `openai/arbor:qwen/qwen3-8b` |
| api_base | `http://localhost:{portnum}/v1/` |
| temperature | `0.6` |
| top_p | `0.95` |
| top_k | `20` |
| MAX_CONTEXT_LENGTH | `8192` |
| IFBench program | `IFBenchCoT2StageProgram` |
| IFBench MIPROv2-Heavy budget | `3593` |
| GEPA budget 来源 | `max_metric_calls_source_opt_name="MIPROv2-Heavy"` |
| IFBench split | `val=train_val_set[:300]`，`train=train_val_set[300:600]`，`test=IFBench_test.jsonl` |

strict 快照的 `scripts` 目录中未命中 `dashscope` 或 `qwen3-8b-dashscope`。

## 与当前 DashScope adapted 路线对比

| 字段 | 论文 artifact strict | 当前 DashScope adapted |
| --- | --- | --- |
| 目的 | 原始 artifact/local Arbor 路线 | 验证 Qwen3 兼容后端可否跑 IFBench smoke |
| 入口 | `scripts.run_experiments` | `scripts/run_ifbench_qwen3_smoke.py` |
| 后端 | local Arbor OpenAI-compatible endpoint | DashScope compatible-mode endpoint |
| model | `openai/arbor:qwen/qwen3-8b` | `openai/qwen3-8b` |
| api_base | `http://localhost:{portnum}/v1/` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| temperature/top_p | `0.6 / 0.95` | `0.6 / 0.95` |
| 数据切分 | artifact 固定前缀切分，seed 非 0 时重排 train/val | wrapper 可截断并支持 `split_seed` manifest |
| optimizer | `Baseline` / `GEPA`，GEPA 追溯 `MIPROv2-Heavy=3593` | `Baseline` / `GEPA-Tiny` smoke 或恢复评测 |
| 当前结果 | 未运行，strict runtime blocked | split1 `+1.0`，split2 `-15.0`，收益不稳 |

## launch command 结果

原生命令：

```powershell
Set-Location .codex/gepa-paper-snapshot
uv run python -m scripts.generate_launch_commands
```

结果：失败。失败发生在全 benchmark 枚举阶段，脚本先实例化 hover，并在 HuggingFace `hover` 数据集加载处报 `HfUriError`。这说明全量 launch command 生成依赖外部数据集状态，不是 IFBench/Qwen 静态配置错误。

随后复刻 `generate_launch_commands.py` 的命令模板，只筛选 IFBench/Qwen/Baseline/GEPA，得到两条目标命令。为保持报告可读性，下方省略了 `train_kwargs` 的长 JSON；实际 filtered 输出包含完整 `train_kwargs`，与 `scripts/experiment_configs.py` 一致。

```bash
uv run python -m scripts.run_experiments --bm_idx 3 --benchmark_name "IFBench" --num_threads 32 --program_idx 0 --prog_name "IFBenchCoT2StageProgram" --opt_idx 0 --optim_name "Baseline" --lm_config '{"name": "qwen3-8b", "model": "openai/arbor:qwen/qwen3-8b", "api_key": "API_KEY", "api_base": "http://localhost:{portnum}/v1/", "temperature": 0.6, "top_p": 0.95, "top_k": 20, "launch_kwargs": {"max_context_length": 8192}}' --seed 0
```

```bash
uv run python -m scripts.run_experiments --bm_idx 3 --benchmark_name "IFBench" --num_threads 32 --program_idx 0 --prog_name "IFBenchCoT2StageProgram" --opt_idx 3 --optim_name "GEPA" --lm_config '{"name": "qwen3-8b", "model": "openai/arbor:qwen/qwen3-8b", "api_key": "API_KEY", "api_base": "http://localhost:{portnum}/v1/", "temperature": 0.6, "top_p": 0.95, "top_k": 20, "launch_kwargs": {"max_context_length": 8192}}' --seed 0 --use_cache_from_opt MIPROv2-Heavy
```

## strict runtime 判定

状态：`blocked_arbor_or_gpu_unavailable`

| 检查项 | 结果 |
| --- | --- |
| `nvidia-smi` | 仅 1 张 NVIDIA GeForce RTX 4060 Laptop GPU，显存约 8GB |
| Python/Torch CUDA | `cuda_available=False`，`cuda_device_count=0` |
| artifact 非 GRPO Arbor 逻辑 | 只接受 `torch.cuda.device_count()` 为 `2` 或 `4` |
| Arbor yaml 路径 | 文件在 `gepa_artifact/utils/arbor`，但 `run_experiments.py` 查找 `utils/arbor/*.yaml` |
| 入口环境变量 | `run_experiments.py` 主入口强制要求 `OPENAI_API_KEY` 与 `WANDB_API_KEY` |
| `uv.lock` | 目标快照不存在 `uv.lock`，计划假设与实际快照不一致 |

因此，本机当前不能按 strict/local Arbor 路线启动 IFBench sanity。按计划，本轮不回退 DashScope，不启动真实模型调用。

## 本地验证

| 验证项 | 结果 |
| --- | --- |
| artifact HEAD | `5f7edbae7f380bedccce2a670bbeba2deb2fd2a3` |
| DSPy HEAD | `62dc3b634d7dc0c4889abcf905cb4c391ea6b396` |
| Arbor HEAD | `113fc35e05acbf2796a5917ec3b45ab44bfacd0b` |
| 数据包指针 SHA256 | `0C7AC976F926BF08B5BBD75410362F16CDA2D899AF8969965A8FD4630E264535` |
| strict 配置静态检查 | 通过 |
| strict 快照 DashScope 搜索 | `0` 命中 |
| 密钥扫描 | `0` 命中 |
| 空白检查 | 退出码 `0`，仅有既有 LF/CRLF warning |

## 下一步建议

如果要继续 strict 复现，应先补齐资源，而不是继续改后端：

1. 获取真实 `experiment_runs_data.tar.gz` LFS payload，或从官方/作者处拿到可校验的等价数据包。
2. 在 Linux 或 WSL/CUDA 环境准备 2 或 4 张可被 PyTorch 识别的 GPU，并确认 Qwen3-8B 权重路径与 Arbor yaml 可用。
3. 处理快照代码的路径一致性问题时必须记录补丁，区分“论文快照原样”与“本地可运行补丁”。
4. strict sanity 成功后再扩大到 IFBench 原始 budget；当前不应把 DashScope adapted 结果当作论文 strict 复现结果。
