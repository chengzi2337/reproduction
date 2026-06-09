from __future__ import annotations

import argparse
import importlib.util
import io
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_ifbench_qwen3_smoke.py"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("run_ifbench_qwen3_smoke", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_args(**overrides):
    values = {
        "lm_name": "qwen3-8b-dashscope-smoke",
        "model": "qwen3-8b",
        "optimizer": "Baseline",
        "max_metric_calls": 8,
        "train_size": 2,
        "val_size": 2,
        "test_size": 2,
        "api_key_env": "QWEN_API_KEY",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "seed": 0,
        "split_seed": None,
        "num_threads": 1,
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "max_tokens": 8192,
        "enable_thinking": False,
        "skip_probe": False,
        "request_timeout_seconds": 75,
        "process_timeout_seconds": 240,
        "num_retries": 0,
        "lm_call_sleep_seconds": 0.0,
        "parallel_straggler_timeout_seconds": 0,
        "recover_run_dir": None,
        "recovery_tag": "recovered-final-eval",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_build_lm_config_does_not_embed_api_key() -> None:
    module = load_smoke_module()
    config = module.build_lm_config(make_args())
    assert config["model"] == "openai/qwen3-8b"
    assert "api_key" not in config
    assert config["extra_body"] == {"enable_thinking": False, "top_k": 20}


def test_build_run_dir_uses_artifact_layout() -> None:
    module = load_smoke_module()
    run_dir = module.build_run_dir("qwen3-8b-dashscope-smoke", 0)
    assert run_dir.name == "IFBench_IFBenchCoT2StageProgram_Baseline_qwen3-8b-dashscope-smoke"
    assert "gepa-artifact" in str(run_dir)
    assert "seed_0" in str(run_dir)


def test_gepa_run_path_rejects_windows_max_path(monkeypatch) -> None:
    module = load_smoke_module()
    monkeypatch.setattr(module.os, "name", "nt")
    long_name = "x" * 200
    run_dir = module.build_run_dir(long_name, 0, module.GEPA_TINY_OPTIMIZER_NAME)
    try:
        module.assert_run_path_safe(run_dir, module.GEPA_TINY_OPTIMIZER_NAME)
    except module.SmokeError as exc:
        assert "260 字符限制" in str(exc)
    else:
        raise AssertionError("GEPA 路径超过 Windows 限制时必须在模型调用前拒绝。")


def test_baseline_run_path_does_not_apply_gepa_depth_check(monkeypatch) -> None:
    module = load_smoke_module()
    monkeypatch.setattr(module.os, "name", "nt")
    run_dir = module.build_run_dir("x" * 200, 0, module.BASELINE_OPTIMIZER_NAME)
    module.assert_run_path_safe(run_dir, module.BASELINE_OPTIMIZER_NAME)


def test_split_sizes_default_to_two_for_smoke() -> None:
    module = load_smoke_module()
    args = module.parse_args([])
    assert args.train_size == 2
    assert args.val_size == 2
    assert args.test_size == 2
    assert args.split_seed is None


def test_split_sizes_must_be_positive() -> None:
    module = load_smoke_module()
    assert module.main(["--train-size", "0", "--preflight-only"]) == 2


def test_retry_and_sleep_must_be_non_negative() -> None:
    module = load_smoke_module()
    assert module.main(["--num-retries", "-1", "--preflight-only"]) == 2
    assert module.main(["--lm-call-sleep-seconds", "-0.5", "--preflight-only"]) == 2
    assert module.main(["--split-seed", "-1", "--preflight-only"]) == 2


def test_seeded_split_is_deterministic_and_changes_with_seed() -> None:
    module = load_smoke_module()
    items = list(range(20))
    first_items, first_indices = module.select_split_items(items, 5, 7, "train")
    repeated_items, repeated_indices = module.select_split_items(items, 5, 7, "train")
    other_items, other_indices = module.select_split_items(items, 5, 8, "train")
    assert (first_items, first_indices) == (repeated_items, repeated_indices)
    assert (first_items, first_indices) != (other_items, other_indices)


def test_legacy_split_keeps_prefix_order() -> None:
    module = load_smoke_module()
    selected, indices = module.select_split_items(list("abcdef"), 3, None, "test")
    assert selected == ["a", "b", "c"]
    assert indices == [0, 1, 2]


def test_split_size_cannot_exceed_official_pool() -> None:
    module = load_smoke_module()
    try:
        module.select_split_items([1, 2], 3, 0, "val")
    except module.SmokeError as exc:
        assert "官方池只有 2 条" in str(exc)
    else:
        raise AssertionError("split 大小超过池容量时必须拒绝运行。")


def test_split_seed_isolated_lm_name() -> None:
    module = load_smoke_module()
    args = make_args(split_seed=3)
    assert module.resolve_lm_name(args) == "qwen3-8b-dashscope-smoke-split3"
    args.lm_name = "qwen3-8b-dashscope-smoke-split3"
    assert module.resolve_lm_name(args) == "qwen3-8b-dashscope-smoke-split3"


def test_worker_command_passes_split_sizes() -> None:
    module = load_smoke_module()
    args = make_args(train_size=10, val_size=10, test_size=20)
    command = module.build_worker_command(args)
    assert "--train-size" in command
    assert command[command.index("--train-size") + 1] == "10"
    assert command[command.index("--val-size") + 1] == "10"
    assert command[command.index("--test-size") + 1] == "20"


def test_worker_command_passes_split_seed() -> None:
    module = load_smoke_module()
    command = module.build_worker_command(make_args(split_seed=4))
    assert command[command.index("--split-seed") + 1] == "4"


def test_worker_command_disables_parallel_straggler_resubmit_by_default() -> None:
    module = load_smoke_module()
    command = module.build_worker_command(make_args())
    assert "--parallel-straggler-timeout-seconds" in command
    assert command[command.index("--parallel-straggler-timeout-seconds") + 1] == "0"


def test_worker_command_passes_retry_and_sleep_controls() -> None:
    module = load_smoke_module()
    command = module.build_worker_command(make_args(num_retries=2, lm_call_sleep_seconds=1.5))
    assert "--num-retries" in command
    assert command[command.index("--num-retries") + 1] == "2"
    assert "--lm-call-sleep-seconds" in command
    assert command[command.index("--lm-call-sleep-seconds") + 1] == "1.5"


def test_build_recovery_run_dir_appends_tag_once(tmp_path: Path) -> None:
    module = load_smoke_module()
    source_run_dir = tmp_path / "seed_0" / "example-run"
    recovered = module.build_recovery_run_dir(source_run_dir, "recovered-final-eval")
    assert recovered.name == "example-run-recovered-final-eval"
    assert (
        module.build_recovery_run_dir(recovered, "recovered-final-eval")
        == recovered
    )


def test_select_manifest_items_uses_indices_and_validates_keys() -> None:
    module = load_smoke_module()
    items = [{"key": "a"}, {"key": "b"}, {"key": "c"}]
    selected = module.select_manifest_items(
        items,
        {"pool_indices": [2, 0], "keys": ["c", "a"]},
        "test",
    )
    assert selected == [{"key": "c"}, {"key": "a"}]


def test_build_recovery_worker_command_passes_source_and_runtime_controls(tmp_path: Path) -> None:
    module = load_smoke_module()
    source_run_dir = tmp_path / "source-run"
    command = module.build_recovery_worker_command(
        make_args(
            num_retries=2,
            lm_call_sleep_seconds=1.5,
            parallel_straggler_timeout_seconds=7,
        ),
        source_run_dir,
    )
    assert "--worker-recover" in command
    assert command[command.index("--recover-run-dir") + 1] == str(source_run_dir)
    assert command[command.index("--num-retries") + 1] == "2"
    assert command[command.index("--lm-call-sleep-seconds") + 1] == "1.5"
    assert command[command.index("--parallel-straggler-timeout-seconds") + 1] == "7"


def test_gepa_optimizer_uses_tiny_name_and_reproduction_type() -> None:
    module = load_smoke_module()
    args = make_args(optimizer="GEPA", max_metric_calls=8)
    optimizer_name = module.resolve_optimizer_name(args)
    run_dir = module.build_run_dir("qwen3-8b-dashscope-smoke", 0, optimizer_name)
    assert optimizer_name == "GEPA-Tiny"
    assert run_dir.name == "IFBench_IFBenchCoT2StageProgram_GEPA-Tiny_qwen3-8b-dashscope-smoke"
    assert module.build_reproduction_type(args) == "artifact_ifbench_dashscope_qwen3_adapted_gepa_tiny"
    assert args.max_metric_calls == 8


def test_resolve_worker_python_prefers_current_interpreter_when_supported(monkeypatch) -> None:
    module = load_smoke_module()
    monkeypatch.setattr(module, "current_python_supports_ifbench", lambda: True)
    assert module.resolve_worker_python() == module.sys.executable


def test_resolve_worker_python_falls_back_to_artifact_venv(monkeypatch, tmp_path: Path) -> None:
    module = load_smoke_module()
    artifact_root = tmp_path / "artifact"
    artifact_python = artifact_root / ".venv" / "Scripts" / "python.exe"
    artifact_python.parent.mkdir(parents=True)
    artifact_python.write_text("", encoding="utf-8")
    monkeypatch.setattr(module, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(module, "current_python_supports_ifbench", lambda: False)
    monkeypatch.setattr(module.os, "name", "nt")
    assert module.resolve_worker_python() == str(artifact_python)


def test_split_manifest_records_indices_and_keys(tmp_path: Path) -> None:
    module = load_smoke_module()
    items = [{"key": "a"}, {"key": "b"}]
    entry = module.build_split_entry(items, [1, 0], 10, "source", source_offset=300)
    payload = {"split_seed": 2, "splits": {"train": entry}}
    path = module.write_split_manifest(tmp_path, payload)
    assert path.name == "split_manifest.json"
    text = path.read_text(encoding="utf-8")
    assert '"source_indices": [' in text
    assert "301" in text
    assert '"keys": [' in text


def test_find_secret_leaks_detects_fake_secret(tmp_path: Path) -> None:
    module = load_smoke_module()
    secret = "fake-secret-for-test"
    clean = tmp_path / "clean.txt"
    leaked = tmp_path / "leaked.json"
    clean.write_text("没有密钥\n", encoding="utf-8")
    leaked.write_text(f'{{"token": "{secret}"}}\n', encoding="utf-8")
    assert module.find_secret_leaks(secret, [tmp_path]) == (leaked,)


def test_safe_console_write_falls_back_when_stream_cannot_encode() -> None:
    module = load_smoke_module()

    class FakeStream:
        def __init__(self) -> None:
            self.encoding = "gbk"
            self.buffer = io.BytesIO()

        def write(self, text: str) -> None:
            raise UnicodeEncodeError("gbk", text, 0, 1, "cannot encode")

    stream = FakeStream()
    module.safe_console_write(stream, "完成 ✔")
    encoded = stream.buffer.getvalue()
    assert b"?" in encoded or "完成".encode("gbk", errors="replace") in encoded


def test_assert_run_integrity_rejects_timeout_marker(tmp_path: Path) -> None:
    module = load_smoke_module()
    (tmp_path / "run_log_stderr.txt").write_text("litellm.Timeout: APITimeoutError\n", encoding="utf-8")
    metric_dir = tmp_path / "metric_logs"
    metric_dir.mkdir()
    (metric_dir / "test.jsonl").write_text("{}\n", encoding="utf-8")
    try:
        module.assert_run_integrity(tmp_path, 1)
    except module.SmokeError as exc:
        assert "实验不可比" in str(exc)
    else:
        raise AssertionError("stderr 中出现 timeout 标记时必须拒绝结果。")


def test_assert_run_integrity_rejects_rate_limit_marker(tmp_path: Path) -> None:
    module = load_smoke_module()
    (tmp_path / "run_log_stderr.txt").write_text("RateLimitError\n", encoding="utf-8")
    metric_dir = tmp_path / "metric_logs"
    metric_dir.mkdir()
    (metric_dir / "test.jsonl").write_text("{}\n", encoding="utf-8")
    try:
        module.assert_run_integrity(tmp_path, 1)
    except module.SmokeError as exc:
        assert "实验不可比" in str(exc)
    else:
        raise AssertionError("stderr 中出现 rate limit 标记时必须拒绝结果。")


def test_assert_run_integrity_rejects_incomplete_metric_rows(tmp_path: Path) -> None:
    module = load_smoke_module()
    (tmp_path / "run_log_stderr.txt").write_text("", encoding="utf-8")
    metric_dir = tmp_path / "metric_logs"
    metric_dir.mkdir()
    (metric_dir / "test.jsonl").write_text("{}\n", encoding="utf-8")
    try:
        module.assert_run_integrity(tmp_path, 2)
    except module.SmokeError as exc:
        assert "metric log 行数不完整" in str(exc)
    else:
        raise AssertionError("metric 行数不完整时必须拒绝结果。")


def test_backfill_missing_test_metric_rows_inserts_zero_failure_record(tmp_path: Path) -> None:
    module = load_smoke_module()
    metric_dir = tmp_path / "metric_logs"
    metric_dir.mkdir()
    (metric_dir / "test.jsonl").write_text(
        '{"idx_in_split": 0, "step_counter": 1, "test_counter": 1, "train_counter": 0, "val_counter": 0}\n',
        encoding="utf-8",
    )
    filled = module.backfill_missing_test_metric_rows(
        tmp_path,
        [{"key": "a"}, {"key": "b"}],
    )
    assert filled == 1
    lines = (metric_dir / "test.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert '"idx_in_split": 1' in lines[1]
    assert '"metric_output": 0' in lines[1]
    assert '"example_key": "b"' in lines[1]


def test_parent_preflight_rejects_missing_key(monkeypatch) -> None:
    module = load_smoke_module()
    args = module.parse_args(["--preflight-only", "--api-key-env", "MISSING_QWEN_KEY_FOR_TEST"])
    monkeypatch.delenv("MISSING_QWEN_KEY_FOR_TEST", raising=False)
    try:
        module.run_parent(args)
    except module.SmokeError as exc:
        assert "MISSING_QWEN_KEY_FOR_TEST" in str(exc)
    else:
        raise AssertionError("缺少 key 时必须拒绝运行。")
