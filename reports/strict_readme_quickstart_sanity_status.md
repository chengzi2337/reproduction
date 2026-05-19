# strict README quickstart sanity status

## 当前定位

- 当前项目是 `GEPA method-level reproduction with DeepSeek backend`
- 本文档记录的是 `strict_readme_quickstart_path` 的极小预算 sanity run
- 本文档 **不是** `original same-model reproduction` 结论
- 本文档 **不是** Stage 1 封版结果的改写

## 运行路径

- 脚本：[07_strict_readme_quickstart_path.py](C:/Users/lin/Documents/New%20project%202/scripts/07_strict_readme_quickstart_path.py)
- 数据集入口：`from gepa.examples.aime import init_dataset`
- 优化入口：`gepa.optimize(...)`
- seed prompt 来源：official `README` quickstart exact prompt
- seed prompt 原文：

```python
{
    "system_prompt": "You are a helpful assistant. Answer the question. Put your final answer in the format '### <answer>'"
}
```

## 本次 sanity run

- 运行目录：
  - [20260519T003536+0800](</C:/Users/lin/Documents/New project 2/outputs/strict_readme_quickstart_path/20260519T003536+0800>)
- 输入快照：
  - [strict_input_snapshot.json](C:/Users/lin/Documents/New%20project%202/outputs/strict_readme_quickstart_path/20260519T003536+0800/strict_input_snapshot.json)
- 结果摘要：
  - [strict_result_summary.json](C:/Users/lin/Documents/New%20project%202/outputs/strict_readme_quickstart_path/20260519T003536+0800/strict_result_summary.json)

### 输入语义确认

- `path_type = strict_readme_quickstart_path`
- `dataset_source = /mnt/c/Users/lin/Documents/New project 2/.venv-wsl/lib/python3.10/site-packages/gepa/examples/aime.py:5`
- `task_lm = openai/deepseek-v4-flash`
- `reflection_lm = openai/deepseek-v4-pro`
- `max_metric_calls = 1`
- `seed = 42`
- `trainset_size = 45`
- `valset_size = 45`
- `testset_size = 150`
- `execute_optimize = true`

### 运行结果

- `strict_readme_quickstart_seed_val_score = 0.15555555555555556`
- `total_metric_calls = 45`
- `num_candidates = 1`
- `num_val_instances = 45`
- `num_full_val_evals = 1`

## 与 Stage 1 wrapper 结果的关系

- 当前 strict sanity run 结果：
  - `strict_readme_quickstart_seed_val_score = 0.15555555555555556`
- 当前 Stage 1 已封版 saved prompt eval 中的 seed 结果：
  - `stage1_wrapper_saved_prompt_seed_test_score = 0.25333333333333335`

这两个值不能写成同一条 baseline，对应关系必须分开：

- 一个是 `strict_readme_quickstart_path` 下的 `seed val score`
- 一个是 `stage1 wrapper + saved prompt eval` 下的 `seed test score`

它们至少有三层差异：

1. 路径不同
   - 一个是极薄 strict README quickstart path
   - 一个是 Stage 1 wrapper path
2. 评估位置不同
   - 一个是本次 sanity run 直接产出的 `val score`
   - 一个是 Stage 1 saved prompt eval 产出的 `test score`
3. 运行目的不同
   - 一个用于验证 strict path 是否真正打通
   - 一个用于 Stage 1 封版结论

## 当前结论

- `strict_readme_quickstart_path` 已经完成真实模型调用，不再只是 dry-run
- 本次 run 说明 strict README quickstart 语义路径是可执行的
- 本次结果足以证明：
  - strict path 与 wrapper path 不能混写
  - strict 路径下应单独记录自己的 seed 指标

## 当前建议

- 不要把 `strict_readme_quickstart_seed_val_score` 回写成 Stage 1 baseline
- 不要把 `stage1_wrapper_saved_prompt_seed_test_score` 改名成 strict 结果
- 如果后续继续推进，更合理的做法是并列维护两条轨道：
  - `Stage 1 wrapper baseline`
  - `strict_readme_quickstart baseline`

## 本文档边界

- 本文档不新增 benchmark
- 本文档不新增方法
- 本文档不修改 GEPA 核心算法
- 本文档不修改 evaluator
- 本文档不涉及 `temperature` 接线
- 本文档不提交完整 `outputs/`
