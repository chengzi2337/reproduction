from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = PROJECT_ROOT / ".codex" / "gepa-artifact"
DEFAULT_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3-8b"
DEFAULT_LM_NAME = "qwen3-8b-dashscope-smoke"
BENCHMARK_NAME = "IFBench"
PROGRAM_NAME = "IFBenchCoT2StageProgram"
BASELINE_OPTIMIZER_NAME = "Baseline"
GEPA_TINY_OPTIMIZER_NAME = "GEPA-Tiny"
TEXT_EXTENSIONS = {".json", ".jsonl", ".log", ".md", ".txt", ".yaml", ".yml"}
RUN_ERROR_MARKERS = (
    "litellm.Timeout",
    "APITimeoutError",
    "ReadTimeout",
    "RateLimitError",
    "exceeded your current request limit",
)
WINDOWS_MAX_PATH = 260
GEPA_DEEPEST_RELATIVE_PATH = Path(
    "generated_best_outputs_valset/task_0/iter_0_prog_0.json"
)


class SmokeError(RuntimeError):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="运行官方 GEPA artifact 的 IFBench + Qwen3 DashScope adapted Baseline/GEPA-Tiny smoke。"
    )
    parser.add_argument("--api-key-env", default="QWEN_API_KEY")
    parser.add_argument("--api-base", default=os.getenv("QWEN_API_BASE", DEFAULT_API_BASE))
    parser.add_argument("--model", default=os.getenv("QWEN_MODEL", DEFAULT_MODEL))
    parser.add_argument("--lm-name", default=DEFAULT_LM_NAME)
    parser.add_argument("--optimizer", choices=["Baseline", "GEPA"], default="Baseline")
    parser.add_argument("--max-metric-calls", type=int, default=8)
    parser.add_argument("--train-size", type=int, default=2)
    parser.add_argument("--val-size", type=int, default=2)
    parser.add_argument("--test-size", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--split-seed",
        type=int,
        default=None,
        help="在官方 train/val/test 池内确定性打乱后截断；未提供时保留前缀截断。",
    )
    parser.add_argument("--num-threads", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=0.6)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--request-timeout-seconds", type=int, default=75)
    parser.add_argument("--process-timeout-seconds", type=int, default=240)
    parser.add_argument("--num-retries", type=int, default=0)
    parser.add_argument("--lm-call-sleep-seconds", type=float, default=0.0)
    parser.add_argument(
        "--parallel-straggler-timeout-seconds",
        type=int,
        default=0,
        help="传给 DSPy ParallelExecutor 的 straggler 重提交阈值；0 表示禁用重提交。",
    )
    parser.add_argument("--enable-thinking", action="store_true")
    parser.add_argument("--skip-probe", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--force", action="store_true", help="将已有同名 run 目录移动到带时间戳的备份目录。")
    parser.add_argument("--yes", action="store_true", help="确认调用真实模型并产生 API 成本。")
    parser.add_argument(
        "--recover-run-dir",
        default=None,
        help="对已完成优化但最终 test eval 不完整的 run，基于已保存 optimized_program 单独恢复最终评测。",
    )
    parser.add_argument(
        "--recovery-tag",
        default="recovered-final-eval",
        help="恢复评测输出目录后缀。",
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--worker-recover", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    for field_name in ("train_size", "val_size", "test_size"):
        if getattr(args, field_name) < 1:
            cli_name = field_name.replace("_", "-")
            raise SmokeError(f"`--{cli_name}` 必须是正整数。")
    if args.num_retries < 0:
        raise SmokeError("`--num-retries` 不能为负数。")
    if args.lm_call_sleep_seconds < 0:
        raise SmokeError("`--lm-call-sleep-seconds` 不能为负数。")
    if args.split_seed is not None and args.split_seed < 0:
        raise SmokeError("`--split-seed` 不能为负数。")
    return args


def normalize_dspy_model(model: str) -> str:
    normalized = model.strip()
    if not normalized:
        raise SmokeError("模型名不能为空。")
    if normalized.startswith("openai/"):
        return normalized
    return f"openai/{normalized}"


def normalize_provider_model(model: str) -> str:
    normalized = model.strip()
    if normalized.startswith("openai/"):
        return normalized[len("openai/") :]
    return normalized


def resolve_optimizer_name(args: argparse.Namespace) -> str:
    if args.optimizer == "Baseline":
        return BASELINE_OPTIMIZER_NAME
    return GEPA_TINY_OPTIMIZER_NAME


def resolve_lm_name(args: argparse.Namespace) -> str:
    if args.split_seed is None:
        return args.lm_name
    suffix = f"-split{args.split_seed}"
    if args.lm_name.endswith(suffix):
        return args.lm_name
    return f"{args.lm_name}{suffix}"


def build_reproduction_type(args: argparse.Namespace) -> str:
    if args.optimizer == "Baseline":
        return "artifact_ifbench_dashscope_qwen3_adapted_baseline_smoke"
    return "artifact_ifbench_dashscope_qwen3_adapted_gepa_tiny"


def build_lm_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "name": resolve_lm_name(args),
        "model": normalize_dspy_model(args.model),
        "api_base": args.api_base,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "timeout": args.request_timeout_seconds,
        "extra_body": {
            "enable_thinking": bool(args.enable_thinking),
            "top_k": args.top_k,
        },
    }


def derive_split_seed(split_seed: int, split_name: str) -> int:
    payload = f"ifbench:{split_seed}:{split_name}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def select_split_items(
    items: list[Any],
    size: int,
    split_seed: int | None,
    split_name: str,
) -> tuple[list[Any], list[int]]:
    if size > len(items):
        raise SmokeError(f"{split_name} 请求 {size} 条，但官方池只有 {len(items)} 条。")
    indices = list(range(len(items)))
    if split_seed is not None:
        random.Random(derive_split_seed(split_seed, split_name)).shuffle(indices)
    selected_indices = indices[:size]
    return [items[index] for index in selected_indices], selected_indices


def read_example_key(example: Any) -> str | None:
    if isinstance(example, dict):
        value = example.get("key")
    else:
        try:
            value = example["key"]
        except (KeyError, TypeError):
            value = getattr(example, "key", None)
    return None if value is None else str(value)


def build_split_entry(
    selected_items: list[Any],
    selected_indices: list[int],
    pool_size: int,
    source_name: str,
    source_offset: int = 0,
) -> dict[str, Any]:
    return {
        "source": source_name,
        "pool_size": pool_size,
        "pool_indices": selected_indices,
        "source_indices": [source_offset + index for index in selected_indices],
        "keys": [read_example_key(item) for item in selected_items],
    }


def select_manifest_items(items: list[Any], manifest_entry: dict[str, Any], split_name: str) -> list[Any]:
    raw_indices = manifest_entry.get("pool_indices")
    if not isinstance(raw_indices, list) or not raw_indices:
        raise SmokeError(f"{split_name} split manifest 缺少有效的 pool_indices。")
    indices: list[int] = []
    for raw_index in raw_indices:
        if not isinstance(raw_index, int):
            raise SmokeError(f"{split_name} split manifest 的 pool_indices 必须全为整数。")
        if raw_index < 0 or raw_index >= len(items):
            raise SmokeError(
                f"{split_name} split manifest 索引越界：{raw_index}，官方池大小为 {len(items)}。"
            )
        indices.append(raw_index)
    selected = [items[index] for index in indices]
    expected_keys = manifest_entry.get("keys")
    if isinstance(expected_keys, list):
        actual_keys = [read_example_key(item) for item in selected]
        if actual_keys != expected_keys:
            raise SmokeError(
                f"{split_name} split manifest 与当前 artifact 数据集键不一致，拒绝恢复评测。"
            )
    return selected


def write_split_manifest(run_dir: Path, payload: dict[str, Any]) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "split_manifest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_run_dir(lm_name: str, seed: int, optimizer_name: str = BASELINE_OPTIMIZER_NAME) -> Path:
    run_name = f"{BENCHMARK_NAME}_{PROGRAM_NAME}_{optimizer_name}_{lm_name}"
    return (
        ARTIFACT_ROOT
        / "experiment_runs_data"
        / "experiment_runs"
        / f"seed_{seed}"
        / run_name
    )


def assert_run_path_safe(run_dir: Path, optimizer_name: str) -> None:
    if os.name != "nt" or optimizer_name != GEPA_TINY_OPTIMIZER_NAME:
        return
    deepest_path = run_dir / GEPA_DEEPEST_RELATIVE_PATH
    if len(str(deepest_path)) >= WINDOWS_MAX_PATH:
        raise SmokeError(
            "GEPA run 路径超过 Windows 传统 260 字符限制，"
            f"请缩短 `--lm-name`；当前最深路径长度为 {len(str(deepest_path))}。"
        )


def assert_artifact_ready() -> None:
    required = [
        ARTIFACT_ROOT / "scripts" / "run_experiments.py",
        ARTIFACT_ROOT / "gepa_artifact" / "benchmarks" / "IFBench" / "ifbench_data.py",
        ARTIFACT_ROOT / "gepa_artifact" / "benchmarks" / "IFBench" / "ifbench_program.py",
        ARTIFACT_ROOT / "gepa_artifact" / "benchmarks" / "IFBench" / "ifbench_metric.py",
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        joined = "\n".join(str(path) for path in missing)
        raise SmokeError(f"artifact 文件缺失，无法运行 IFBench smoke：\n{joined}")


def redact_text(text: str, secret: str) -> str:
    if not secret:
        return text
    return text.replace(secret, "***REDACTED***")


def safe_console_write(stream: Any, text: str) -> None:
    try:
        stream.write(text)
        return
    except UnicodeEncodeError:
        pass
    buffer = getattr(stream, "buffer", None)
    encoding = getattr(stream, "encoding", None) or "utf-8"
    if buffer is not None:
        buffer.write(text.encode(encoding, errors="replace"))
        return
    stream.write(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def probe_model(args: argparse.Namespace, api_key: str) -> dict[str, Any]:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from src.deepseek_utils import probe_model_with_openai_client

    result = probe_model_with_openai_client(
        api_key=api_key,
        api_base=args.api_base,
        model_name=normalize_provider_model(args.model),
        extra_body={
            "enable_thinking": bool(args.enable_thinking),
            "top_k": args.top_k,
        },
        extra_kwargs={"timeout": args.request_timeout_seconds},
    )
    return {
        "ok": result.ok,
        "model": result.model,
        "response_text": redact_text(result.response_text, api_key),
        "error_type": result.error_type,
        "error_message": redact_text(result.error_message or "", api_key),
        "status_code": result.status_code,
    }


def move_existing_run_dir(run_dir: Path) -> Path | None:
    if not run_dir.exists():
        return None
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = run_dir.with_name(f"{run_dir.name}_backup_{timestamp}")
    shutil.move(str(run_dir), str(backup_dir))
    return backup_dir


def build_recovery_run_dir(source_run_dir: Path, recovery_tag: str) -> Path:
    tag = recovery_tag.strip()
    if not tag:
        raise SmokeError("恢复评测目录后缀不能为空。")
    suffix = f"-{tag}"
    if source_run_dir.name.endswith(suffix):
        return source_run_dir
    return source_run_dir.with_name(f"{source_run_dir.name}{suffix}")


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SmokeError(f"缺少必需文件：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SmokeError(f"JSON 解析失败：{path}") from exc
    if not isinstance(payload, dict):
        raise SmokeError(f"JSON 顶层必须是对象：{path}")
    return payload


def iter_text_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            candidates = [root]
        else:
            candidates = [path for path in root.rglob("*") if path.is_file()]
        for path in candidates:
            if path.suffix.lower() in TEXT_EXTENSIONS and path.stat().st_size <= 5_000_000:
                files.append(path)
    return files


def find_secret_leaks(secret: str, roots: list[Path]) -> tuple[Path, ...]:
    if not secret:
        return tuple()
    leaked: list[Path] = []
    for path in iter_text_files(roots):
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if secret in content:
            leaked.append(path)
    return tuple(leaked)


def default_secret_scan_roots(run_dir: Path) -> list[Path]:
    return [
        run_dir,
        ARTIFACT_ROOT / "experiment_runs_data" / "experiment_runs",
        PROJECT_ROOT / "outputs",
        PROJECT_ROOT / "reports",
        PROJECT_ROOT / ".codex" / "operations-log.md",
        PROJECT_ROOT / ".codex" / "verification-report.md",
    ]


def parse_evaluation_result(run_dir: Path) -> dict[str, str]:
    path = run_dir / "evaluation_results" / "evaluation_result.txt"
    if not path.exists():
        raise SmokeError(f"未找到 evaluation_result：{path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise SmokeError(f"evaluation_result 行数异常：{path}")
    return {key: value for key, value in rows[0].items() if key}


def count_metric_rows(run_dir: Path) -> int:
    path = run_dir / "metric_logs" / "test.jsonl"
    if not path.exists():
        raise SmokeError(f"未找到 metric log：{path}")
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        return sum(1 for line in handle if line.strip())


def backfill_missing_test_metric_rows(run_dir: Path, expected_items: list[Any]) -> int:
    path = run_dir / "metric_logs" / "test.jsonl"
    if not path.exists():
        raise SmokeError(f"未找到 metric log：{path}")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                records.append(payload)
    seen_indices = {
        record["idx_in_split"]
        for record in records
        if isinstance(record.get("idx_in_split"), int)
    }
    missing_indices = [index for index in range(len(expected_items)) if index not in seen_indices]
    if not missing_indices:
        return 0

    next_step_counter = max((int(record.get("step_counter", 0)) for record in records), default=0)
    next_test_counter = max((int(record.get("test_counter", 0)) for record in records), default=0)
    train_counter = max((int(record.get("train_counter", 0)) for record in records), default=0)
    val_counter = max((int(record.get("val_counter", 0)) for record in records), default=0)
    for missing_index in missing_indices:
        next_step_counter += 1
        next_test_counter += 1
        records.append(
            {
                "prediction": None,
                "metric_output": 0,
                "metric_call_count": next_test_counter,
                "step_counter": next_step_counter,
                "train_counter": train_counter,
                "val_counter": val_counter,
                "test_counter": next_test_counter,
                "idx_in_split": missing_index,
                "recovery_status": "filled_missing_metric_row",
                "recovery_reason": "dspy_evaluate_error_without_metric_row",
                "example_key": read_example_key(expected_items[missing_index]),
            }
        )

    records.sort(key=lambda record: int(record.get("idx_in_split", 0)))
    with path.open("w", encoding="utf-8", newline="") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(missing_indices)


def find_run_error_markers(run_dir: Path) -> tuple[str, ...]:
    stderr_path = run_dir / "run_log_stderr.txt"
    if not stderr_path.exists():
        return tuple()
    content = stderr_path.read_text(encoding="utf-8", errors="ignore")
    return tuple(marker for marker in RUN_ERROR_MARKERS if marker in content)


def assert_run_integrity(run_dir: Path, expected_metric_rows: int) -> int:
    error_markers = find_run_error_markers(run_dir)
    if error_markers:
        markers = ", ".join(error_markers)
        raise SmokeError(f"run stderr 包含异常标记，实验不可比：{markers}")

    metric_rows = count_metric_rows(run_dir)
    if metric_rows != expected_metric_rows:
        raise SmokeError(f"metric log 行数不完整：期望 {expected_metric_rows}，实际 {metric_rows}")
    return metric_rows


def build_worker_command(args: argparse.Namespace) -> list[str]:
    command = [
        resolve_worker_python(),
        str(Path(__file__).resolve()),
        "--worker",
        "--yes",
        "--api-key-env",
        args.api_key_env,
        "--api-base",
        args.api_base,
        "--model",
        args.model,
        "--lm-name",
        args.lm_name,
        "--optimizer",
        args.optimizer,
        "--max-metric-calls",
        str(args.max_metric_calls),
        "--train-size",
        str(args.train_size),
        "--val-size",
        str(args.val_size),
        "--test-size",
        str(args.test_size),
        "--seed",
        str(args.seed),
        "--num-threads",
        str(args.num_threads),
        "--temperature",
        str(args.temperature),
        "--top-p",
        str(args.top_p),
        "--top-k",
        str(args.top_k),
        "--max-tokens",
        str(args.max_tokens),
        "--request-timeout-seconds",
        str(args.request_timeout_seconds),
        "--process-timeout-seconds",
        str(args.process_timeout_seconds),
        "--num-retries",
        str(args.num_retries),
        "--lm-call-sleep-seconds",
        str(args.lm_call_sleep_seconds),
        "--parallel-straggler-timeout-seconds",
        str(args.parallel_straggler_timeout_seconds),
    ]
    if args.split_seed is not None:
        command.extend(["--split-seed", str(args.split_seed)])
    if args.enable_thinking:
        command.append("--enable-thinking")
    if args.skip_probe:
        command.append("--skip-probe")
    return command


def build_recovery_worker_command(args: argparse.Namespace, source_run_dir: Path) -> list[str]:
    return [
        resolve_worker_python(),
        str(Path(__file__).resolve()),
        "--worker-recover",
        "--api-key-env",
        args.api_key_env,
        "--recover-run-dir",
        str(source_run_dir),
        "--recovery-tag",
        args.recovery_tag,
        "--num-threads",
        str(args.num_threads),
        "--max-tokens",
        str(args.max_tokens),
        "--request-timeout-seconds",
        str(args.request_timeout_seconds),
        "--num-retries",
        str(args.num_retries),
        "--lm-call-sleep-seconds",
        str(args.lm_call_sleep_seconds),
        "--parallel-straggler-timeout-seconds",
        str(args.parallel_straggler_timeout_seconds),
    ]


def current_python_supports_ifbench() -> bool:
    return importlib.util.find_spec("spacy") is not None


def resolve_worker_python() -> str:
    if current_python_supports_ifbench():
        return sys.executable
    if os.name == "nt":
        candidate = ARTIFACT_ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = ARTIFACT_ROOT / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def build_recovery_summary(
    source_run_dir: Path,
    recovery_run_dir: Path,
    source_evaluation_result: dict[str, str],
    recovered_evaluation_result: dict[str, str],
    metric_rows: int,
    duration_seconds: float,
    args: argparse.Namespace,
    recovery_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "benchmark": BENCHMARK_NAME,
        "program": PROGRAM_NAME,
        "recovery_type": "artifact_ifbench_dashscope_qwen3_saved_program_final_eval_recovery",
        "source_run_dir": str(source_run_dir),
        "recovery_run_dir": str(recovery_run_dir),
        "optimizer": source_evaluation_result.get("optimizer") or GEPA_TINY_OPTIMIZER_NAME,
        "model": args.model,
        "metric_rows": metric_rows,
        "duration_seconds": duration_seconds,
        "max_tokens": args.max_tokens,
        "num_retries": args.num_retries,
        "lm_call_sleep_seconds": args.lm_call_sleep_seconds,
        "parallel_straggler_timeout_seconds": args.parallel_straggler_timeout_seconds,
        "recovery_metadata": recovery_metadata or {},
        "source_evaluation_result": source_evaluation_result,
        "recovered_evaluation_result": recovered_evaluation_result,
    }


def run_recovery_parent(args: argparse.Namespace, api_key: str) -> int:
    source_run_dir = Path(str(args.recover_run_dir)).expanduser().resolve()
    if not source_run_dir.exists():
        raise SmokeError(f"待恢复 run 目录不存在：{source_run_dir}")
    recovery_run_dir = build_recovery_run_dir(source_run_dir, args.recovery_tag)
    if args.force:
        backup_dir = move_existing_run_dir(recovery_run_dir)
        if backup_dir is not None:
            print(f"已有恢复目录已移动到：{backup_dir}")

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["OPENAI_API_KEY"] = api_key
    env["OPENAI_BASE_URL"] = args.api_base
    env["OPENAI_API_BASE"] = args.api_base
    env.setdefault("WANDB_MODE", "disabled")
    env.setdefault("WANDB_API_KEY", "disabled-for-ifbench-smoke")

    started = time.monotonic()
    try:
        completed = subprocess.run(
            build_recovery_worker_command(args, source_run_dir),
            cwd=ARTIFACT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=args.process_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = redact_text(exc.stdout or "", api_key)
        stderr = redact_text(exc.stderr or "", api_key)
        if stdout:
            safe_console_write(sys.stdout, stdout)
        if stderr:
            safe_console_write(sys.stderr, stderr)
        raise SmokeError(f"恢复评测 worker 超过 {args.process_timeout_seconds}s 未结束。") from exc

    duration = round(time.monotonic() - started, 3)
    if completed.stdout:
        safe_console_write(sys.stdout, redact_text(completed.stdout, api_key))
    if completed.stderr:
        safe_console_write(sys.stderr, redact_text(completed.stderr, api_key))
    if completed.returncode != 0:
        raise SmokeError(f"恢复评测 worker 退出码异常：{completed.returncode}")

    split_manifest = load_json_file(source_run_dir / "split_manifest.json")
    splits = split_manifest.get("splits")
    if not isinstance(splits, dict) or not isinstance(splits.get("test"), dict):
        raise SmokeError("source run 缺少 test split manifest。")
    expected_metric_rows = len(splits["test"].get("pool_indices", []))
    if expected_metric_rows <= 0:
        raise SmokeError("source run 的 test split 为空，无法恢复评测。")
    metric_rows = assert_run_integrity(recovery_run_dir, expected_metric_rows)
    recovered_evaluation_result = parse_evaluation_result(recovery_run_dir)
    source_evaluation_result = parse_evaluation_result(source_run_dir)
    recovery_metadata = load_json_file(recovery_run_dir / "recovery_metadata.json")
    leaked_files = find_secret_leaks(api_key, default_secret_scan_roots(recovery_run_dir))
    if leaked_files:
        joined = "\n".join(str(path) for path in leaked_files)
        raise SmokeError(f"检测到恢复评测 API key 落盘：\n{joined}")

    summary = build_recovery_summary(
        source_run_dir=source_run_dir,
        recovery_run_dir=recovery_run_dir,
        source_evaluation_result=source_evaluation_result,
        recovered_evaluation_result=recovered_evaluation_result,
        metric_rows=metric_rows,
        duration_seconds=duration,
        args=args,
        recovery_metadata=recovery_metadata,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def run_parent(args: argparse.Namespace) -> int:
    assert_artifact_ready()
    api_key = os.getenv(args.api_key_env, "").strip()
    if not api_key:
        raise SmokeError(f"缺少环境变量 `{args.api_key_env}`，不会启动真实模型调用。")

    if args.recover_run_dir:
        if args.preflight_only:
            print("preflight 通过，恢复评测模式未启动真实模型。")
            return 0
        if not args.yes:
            raise SmokeError("恢复评测同样需要显式传入 `--yes`。")
        return run_recovery_parent(args, api_key)

    probe_payload: dict[str, Any] | None = None
    if not args.skip_probe:
        probe_payload = probe_model(args, api_key)
        print(json.dumps({"probe": probe_payload}, ensure_ascii=False, indent=2))
        if not probe_payload["ok"]:
            return 3

    if args.preflight_only:
        print("preflight 通过，未启动 benchmark。")
        return 0
    if not args.yes:
        raise SmokeError("需要显式传入 `--yes` 才会调用真实模型。")

    optimizer_name = resolve_optimizer_name(args)
    effective_lm_name = resolve_lm_name(args)
    run_dir = build_run_dir(effective_lm_name, args.seed, optimizer_name)
    assert_run_path_safe(run_dir, optimizer_name)
    if args.force:
        backup_dir = move_existing_run_dir(run_dir)
        if backup_dir is not None:
            print(f"已有 run 目录已移动到：{backup_dir}")

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["OPENAI_API_KEY"] = api_key
    env["OPENAI_BASE_URL"] = args.api_base
    env["OPENAI_API_BASE"] = args.api_base
    env.setdefault("WANDB_MODE", "disabled")
    env.setdefault("WANDB_API_KEY", "disabled-for-ifbench-smoke")

    started = time.monotonic()
    try:
        completed = subprocess.run(
            build_worker_command(args),
            cwd=ARTIFACT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=args.process_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = redact_text(exc.stdout or "", api_key)
        stderr = redact_text(exc.stderr or "", api_key)
        if stdout:
            safe_console_write(sys.stdout, stdout)
        if stderr:
            safe_console_write(sys.stderr, stderr)
        raise SmokeError(f"worker 超过 {args.process_timeout_seconds}s 未结束，已判定为超时。") from exc

    duration = round(time.monotonic() - started, 3)
    if completed.stdout:
        safe_console_write(sys.stdout, redact_text(completed.stdout, api_key))
    if completed.stderr:
        safe_console_write(sys.stderr, redact_text(completed.stderr, api_key))
    if completed.returncode != 0:
        raise SmokeError(f"worker 退出码异常：{completed.returncode}")

    metric_rows = assert_run_integrity(run_dir, args.test_size)
    evaluation_result = parse_evaluation_result(run_dir)
    leaked_files = find_secret_leaks(api_key, default_secret_scan_roots(run_dir))
    if leaked_files:
        joined = "\n".join(str(path) for path in leaked_files)
        raise SmokeError(f"检测到 API key 落盘：\n{joined}")

    summary = {
        "benchmark": BENCHMARK_NAME,
        "program": PROGRAM_NAME,
        "optimizer": optimizer_name,
        "model": args.model,
        "lm_name": effective_lm_name,
        "base_lm_name": args.lm_name,
        "optimizer_seed": args.seed,
        "split_seed": args.split_seed,
        "split_protocol": "seeded_shuffle" if args.split_seed is not None else "legacy_prefix",
        "max_metric_calls": args.max_metric_calls if args.optimizer == "GEPA" else None,
        "gepa_num_iters": None,
        "split_sizes": {
            "train": args.train_size,
            "val": args.val_size,
            "dev": args.val_size,
            "test": args.test_size,
        },
        "run_dir": str(run_dir),
        "duration_seconds": duration,
        "metric_rows": metric_rows,
        "num_retries": args.num_retries,
        "lm_call_sleep_seconds": args.lm_call_sleep_seconds,
        "parallel_straggler_timeout_seconds": args.parallel_straggler_timeout_seconds,
        "evaluation_result": evaluation_result,
        "secret_scan_matches": 0,
        "probe": probe_payload,
        "reproduction_type": build_reproduction_type(args),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def run_worker(args: argparse.Namespace) -> int:
    if str(ARTIFACT_ROOT) not in sys.path:
        sys.path.insert(0, str(ARTIFACT_ROOT))
    os.chdir(ARTIFACT_ROOT)

    from gepa_artifact.benchmarks.IFBench import benchmark as ifbench_benchmark
    from gepa_artifact.benchmarks.IFBench.ifbench_data import IFBench
    from gepa_artifact.utils.optimizers import OptimizerConfig
    from dspy.utils.parallelizer import ParallelExecutor
    import scripts.run_experiments as runner

    original_init_dataset = IFBench.init_dataset
    original_parallel_executor_init = ParallelExecutor.__init__
    optimizer_name = resolve_optimizer_name(args)
    effective_lm_name = resolve_lm_name(args)
    run_dir = build_run_dir(effective_lm_name, args.seed, optimizer_name)
    split_manifest_payload: dict[str, Any] | None = None

    def patched_parallel_executor_init(self: Any, *init_args: Any, **init_kwargs: Any) -> Any:
        init_kwargs["timeout"] = args.parallel_straggler_timeout_seconds
        return original_parallel_executor_init(self, *init_args, **init_kwargs)

    def patched_init_dataset(self: Any) -> None:
        nonlocal split_manifest_payload
        original_init_dataset(self)
        train_pool = list(self.train_set)
        val_pool = list(self.val_set)
        test_pool = list(self.test_set)
        self.train_set, train_indices = select_split_items(
            train_pool,
            args.train_size,
            args.split_seed,
            "train",
        )
        self.val_set, val_indices = select_split_items(
            val_pool,
            args.val_size,
            args.split_seed,
            "val",
        )
        self.dev_set = list(self.val_set)
        self.test_set, test_indices = select_split_items(
            test_pool,
            args.test_size,
            args.split_seed,
            "test",
        )
        self.dataset = self.train_set + self.val_set + self.test_set
        split_manifest_payload = {
            "protocol": "seeded_shuffle" if args.split_seed is not None else "legacy_prefix",
            "optimizer_seed": args.seed,
            "split_seed": args.split_seed,
            "lm_name": effective_lm_name,
            "splits": {
                "train": build_split_entry(
                    self.train_set,
                    train_indices,
                    len(train_pool),
                    "IFBench_train.jsonl[300:600]",
                    source_offset=300,
                ),
                "val": build_split_entry(
                    self.val_set,
                    val_indices,
                    len(val_pool),
                    "IFBench_train.jsonl[0:300]",
                ),
                "dev": build_split_entry(
                    self.dev_set,
                    val_indices,
                    len(val_pool),
                    "IFBench_train.jsonl[0:300]",
                ),
                "test": build_split_entry(
                    self.test_set,
                    test_indices,
                    len(test_pool),
                    "IFBench_test.jsonl",
                ),
            },
        }

    def create_lm(lm_config: dict[str, Any]) -> Any:
        import dspy

        config = lm_config.copy()
        config["model"] = config.pop("new_model_name", config["model"])
        config = {key: value for key, value in config.items() if key != "name"}
        lm = dspy.LM(
            **config,
            max_tokens=args.max_tokens,
            num_retries=args.num_retries,
            provider=None,
        )
        if args.lm_call_sleep_seconds <= 0:
            return lm

        original_forward = lm.forward

        def throttled_forward(*forward_args: Any, **forward_kwargs: Any) -> Any:
            try:
                return original_forward(*forward_args, **forward_kwargs)
            finally:
                time.sleep(args.lm_call_sleep_seconds)

        lm.forward = throttled_forward
        return lm

    IFBench.init_dataset = patched_init_dataset
    ParallelExecutor.__init__ = patched_parallel_executor_init

    def build_optimizer_config() -> OptimizerConfig:
        if args.optimizer == "Baseline":
            return OptimizerConfig(
                optimizer=None,
                init_args={},
                compile_args={},
                langProBe_configs={"launch_arbor": False},
                name=optimizer_name,
            )

        from gepa_artifact.gepa.gepa import GEPA
        import gepa_artifact.gepa.instruction_proposal as instruction_proposal

        original_gepa_init = GEPA.__init__

        def patched_gepa_init(self: Any, *init_args: Any, **init_kwargs: Any) -> Any:
            init_kwargs["use_wandb"] = False
            init_kwargs["wandb_api_key"] = None
            return original_gepa_init(self, *init_args, **init_kwargs)

        def patched_call_lm_and_extract_response(
            prompt: str,
            lm: Any,
            current_instruction_doc: str,
            user_examples_and_feedback: str,
            reference_materials: str | None = None,
        ) -> str:
            full_prompt = prompt.replace("<curr_instructions>", current_instruction_doc)
            full_prompt = full_prompt.replace("<inputs_outputs_feedback>", user_examples_and_feedback)
            if reference_materials is not None:
                full_prompt = full_prompt.replace("<reference_materials>", reference_materials)
            lm_out = lm(full_prompt, max_tokens=args.max_tokens)[0].strip()
            if lm_out.count("```") >= 2:
                start = lm_out.find("```")
                end = lm_out.rfind("```")
                if start >= end or start == -1 or end == -1:
                    return lm_out
                return lm_out[start + 3 : end].strip()
            lm_out = lm_out.strip()
            if lm_out.startswith("```"):
                lm_out = lm_out[3:]
            if lm_out.endswith("```"):
                lm_out = lm_out[:-3]
            return lm_out

        GEPA.__init__ = patched_gepa_init
        instruction_proposal.call_lm_and_extract_response = patched_call_lm_and_extract_response
        runner.wandb_api_key = ""
        return OptimizerConfig(
            optimizer=GEPA,
            init_args={
                "run_linearized_gepa": False,
                "use_merge": False,
                "set_for_merge_minibatch": "val",
                "track_scores_on": "val",
                "max_metric_calls": args.max_metric_calls,
                "skip_perfect_score": False,
            },
            compile_args={},
            langProBe_configs={
                "use_valset": True,
                "launch_arbor": False,
            },
            name=optimizer_name,
        )

    runner.get_benchmarks = lambda: ifbench_benchmark
    runner.get_optimizers = lambda: [(optimizer_name, build_optimizer_config())]
    runner.create_lm = create_lm

    runner.run_experiment_and_write_results(
        bm_idx=0,
        benchmark_name=BENCHMARK_NAME,
        num_threads=args.num_threads,
        program_idx=0,
        prog_name=PROGRAM_NAME,
        opt_idx=0,
        optim_name=optimizer_name,
        lm_config=build_lm_config(args),
        dry_run=False,
        use_cache_from_opt=None,
        seed=args.seed,
    )
    if split_manifest_payload is None:
        raise SmokeError("IFBench 数据集未初始化，无法写入 split manifest。")
    write_split_manifest(run_dir, split_manifest_payload)
    return 0


def run_recovery_worker(args: argparse.Namespace) -> int:
    if str(ARTIFACT_ROOT) not in sys.path:
        sys.path.insert(0, str(ARTIFACT_ROOT))
    os.chdir(ARTIFACT_ROOT)

    import dspy
    from dspy.utils.parallelizer import ParallelExecutor
    from gepa_artifact.benchmarks.IFBench import benchmark as ifbench_benchmark
    from gepa_artifact.benchmarks.IFBench.ifbench_data import IFBench
    from gepa_artifact.benchmarks.benchmark import EvaluationResult
    from gepa_artifact.utils.metric_logger import CounterWithLock, MetricWithLogger
    from scripts.run_experiments import calculate_stats, write_evaluation_result_to_path

    source_run_dir = Path(str(args.recover_run_dir)).expanduser().resolve()
    if not source_run_dir.exists():
        raise SmokeError(f"待恢复 run 目录不存在：{source_run_dir}")
    source_config = load_json_file(source_run_dir / "config.json")
    split_manifest = load_json_file(source_run_dir / "split_manifest.json")
    source_evaluation_result = parse_evaluation_result(source_run_dir)
    optimized_program_dir = source_run_dir / "evaluation_results" / "optimized_program"
    if not optimized_program_dir.exists():
        raise SmokeError(f"source run 缺少 optimized_program：{optimized_program_dir}")

    recovery_run_dir = build_recovery_run_dir(source_run_dir, args.recovery_tag)
    recovery_run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_run_dir / "config.json", recovery_run_dir / "config.json")
    shutil.copy2(source_run_dir / "split_manifest.json", recovery_run_dir / "split_manifest.json")

    original_init_dataset = IFBench.init_dataset
    original_parallel_executor_init = ParallelExecutor.__init__

    def patched_parallel_executor_init(self: Any, *init_args: Any, **init_kwargs: Any) -> Any:
        init_kwargs["timeout"] = args.parallel_straggler_timeout_seconds
        return original_parallel_executor_init(self, *init_args, **init_kwargs)

    def patched_init_dataset(self: Any) -> None:
        original_init_dataset(self)
        train_pool = list(self.train_set)
        val_pool = list(self.val_set)
        test_pool = list(self.test_set)
        splits = split_manifest.get("splits")
        if not isinstance(splits, dict):
            raise SmokeError("split manifest 缺少 splits。")
        train_entry = splits.get("train")
        val_entry = splits.get("val")
        test_entry = splits.get("test")
        if not all(isinstance(entry, dict) for entry in (train_entry, val_entry, test_entry)):
            raise SmokeError("split manifest 缺少 train/val/test 明细。")
        self.train_set = select_manifest_items(train_pool, train_entry, "train")
        self.val_set = select_manifest_items(val_pool, val_entry, "val")
        self.dev_set = list(self.val_set)
        self.test_set = select_manifest_items(test_pool, test_entry, "test")
        self.dataset = self.train_set + self.val_set + self.test_set

    def create_recovery_lm(lm_config: dict[str, Any]) -> Any:
        config = dict(lm_config)
        config["api_key"] = os.environ.get("OPENAI_API_KEY", "").strip()
        if not config["api_key"]:
            raise SmokeError("恢复评测 worker 未拿到 OPENAI_API_KEY。")
        config["model"] = config.pop("new_model_name", config["model"])
        config = {key: value for key, value in config.items() if key != "name"}
        lm = dspy.LM(
            **config,
            max_tokens=args.max_tokens,
            num_retries=args.num_retries,
            provider=None,
        )
        if args.lm_call_sleep_seconds <= 0:
            return lm

        original_forward = lm.forward

        def throttled_forward(*forward_args: Any, **forward_kwargs: Any) -> Any:
            try:
                return original_forward(*forward_args, **forward_kwargs)
            finally:
                time.sleep(args.lm_call_sleep_seconds)

        lm.forward = throttled_forward
        return lm

    try:
        IFBench.init_dataset = patched_init_dataset
        ParallelExecutor.__init__ = patched_parallel_executor_init
        benchmark_meta = ifbench_benchmark[0]
        benchmark = benchmark_meta.benchmark()
        optimized_program = dspy.load(str(optimized_program_dir))
        metric_counter = CounterWithLock()
        adapter = dspy.settings.adapter
        eval_results = EvaluationResult(
            benchmark=source_config.get("benchmark_name", BENCHMARK_NAME),
            program=source_config.get("program_name", PROGRAM_NAME),
        )
        with MetricWithLogger(
            metric_fn=benchmark_meta.metric,
            run_dir=str(recovery_run_dir),
            counter_with_lock=metric_counter,
            train_dataset=benchmark.train_set,
            val_dataset=benchmark.val_set,
            test_dataset=benchmark.test_set,
            log_prediction=True,
        ) as metric_fn_with_logger:
            evaluate_prog = dspy.Evaluate(
                devset=benchmark.test_set,
                metric=metric_fn_with_logger,
                num_threads=args.num_threads,
                display_progress=True,
                max_errors=len(benchmark.test_set) * 10,
                provide_traceback=True,
            )
            eval_lm = create_recovery_lm(source_config.get("lm_config", {}))
            dspy.configure(lm=eval_lm, adapter=adapter)
            score = evaluate_prog(optimized_program)
            eval_results.score = score
            eval_results.cost, eval_results.input_tokens, eval_results.output_tokens = calculate_stats(eval_lm)
            eval_results.optimizer = source_evaluation_result.get("optimizer") or source_config.get(
                "optimizer_name", GEPA_TINY_OPTIMIZER_NAME
            )
            eval_results.optimizer_cost = float(source_evaluation_result.get("optimizer_cost") or 0)
            eval_results.optimizer_input_tokens = int(float(source_evaluation_result.get("optimizer_input_tokens") or 0))
            eval_results.optimizer_output_tokens = int(
                float(source_evaluation_result.get("optimizer_output_tokens") or 0)
            )
            eval_results.optimized_program = optimized_program
            dspy.configure(lm=None, adapter=None)
            del eval_lm
        backfilled_rows = backfill_missing_test_metric_rows(recovery_run_dir, benchmark.test_set)
        write_evaluation_result_to_path(eval_results, str(recovery_run_dir / "evaluation_results"))
        metadata_path = recovery_run_dir / "recovery_metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "source_run_dir": str(source_run_dir),
                    "recovery_run_dir": str(recovery_run_dir),
                    "optimized_program_dir": str(optimized_program_dir),
                    "max_tokens": args.max_tokens,
                    "num_retries": args.num_retries,
                    "lm_call_sleep_seconds": args.lm_call_sleep_seconds,
                    "parallel_straggler_timeout_seconds": args.parallel_straggler_timeout_seconds,
                    "backfilled_metric_rows": backfilled_rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        IFBench.init_dataset = original_init_dataset
        ParallelExecutor.__init__ = original_parallel_executor_init
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if args.worker:
            return run_worker(args)
        if args.worker_recover:
            return run_recovery_worker(args)
        return run_parent(args)
    except SmokeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
