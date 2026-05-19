# Stage 2 Current Status

## 当前事实

- MiMo Token Plan key 有效
- `MIMO_API_BASE` 当前应使用：
  - `https://token-plan-cn.xiaomimimo.com/v1`
- Windows 直连 `token-plan-cn.xiaomimimo.com:443` 当前不稳定或失败
- 代理可达路径当前可用

## 已完成验证

- raw OpenAI SDK 最小 `OK` probe：成功
- raw OpenAI SDK + 真实 AIME 单样本 + `thinking.disabled` + `max_completion_tokens=512`：成功，且 `content` 非空
- LiteLLM `openai/mimo-v2.5-pro` + 同样受控生成条件：成功，且 `content` 非空

## 当前解释边界

- 这些结果属于 `Stage 2B: MiMo controlled-generation diagnostic path`
- 它不是 strict path
- 它不是 GEPA smoke
- 它不是性能结论
- 它不改写 Stage 1 历史结论

## 下一步约束

- 当前不运行 `gepa.optimize()`
- 当前不运行 MiMo smoke / pilot

## 已选路线

- 当前选择 `路线 A 的前半段`
- 含义：优先尝试恢复和稳定 MiMo 的 strict default path，再回到 strict execute sanity
- 当前不进入 `Stage 2C: MiMo explicitly controlled-generation GEPA path`

## 路线 A 的下一步

1. 继续限制在 strict default path 语义范围内排查执行阻塞
2. 不引入 `thinking.disabled` 或 `max_completion_tokens` 到 GEPA 路径
3. 只有 strict default path 未来能稳定返回时，才重新进入 strict execute sanity
4. 在路线 A 未闭环前，不启动 MiMo GEPA smoke / pilot

## 路线 A 最新观察

- `scripts/stage2a_diagnose_mimo_strict_default_path_blocker.py` 已完成首次真实阻塞诊断
- `init_dataset()` 本地缓存回放正常，首个 `val` 样本加载约 2.75 秒完成
- 在代理可达路径下，`mimo-v2.5-pro` 的 strict default path 单样本调用仍然卡住
- `direct OpenAI SDK` 默认调用在 180 秒外层窗口内未返回
- 即使把请求级 `timeout` 压到 30 秒，`direct OpenAI SDK` 默认调用仍未在 90 秒外层窗口内干净返回异常
- `LiteLLM openai/mimo-v2.5-pro` 默认调用也出现相同现象

## 当前收敛结论

- 当前 blocker 不在数据集层
- 默认 completion 路径本身不是全坏的
- 在同一代理路径下，`mimo-v2.5-pro` 对简单 `OK` prompt 的默认 direct SDK 与默认 LiteLLM 调用都能在数秒内返回
- 当前 blocker 已进一步收敛到：
  - 真实 AIME prompt 与 MiMo strict default generation 组合下的 completion 调用层
- Stage 2B 的受控生成成功，仍然不能推出 strict default path 已恢复
