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
import threading
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = PROJECT_ROOT / ".codex" / "gepa-artifact"
DEFAULT_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3-8b"
DEFAULT_LM_NAME = "qwen3-8b-dashscope-smoke"
DEFAULT_PAPER_ADAPTED_LM_NAME = "qwen3-8b-dashscope-paper-adapted"
BENCHMARK_NAME = "IFBench"
PROGRAM_NAME = "IFBenchCoT2StageProgram"
BASELINE_OPTIMIZER_NAME = "Baseline"
GEPA_TINY_OPTIMIZER_NAME = "GEPA-Tiny"
PAPER_ADAPTED_GEPA_OPTIMIZER_NAME = "GEPA"
PAPER_ADAPTED_MAX_METRIC_CALLS = 3593
PAPER_ADAPTED_TRAIN_SIZE = 300
PAPER_ADAPTED_VAL_SIZE = 300
PAPER_ADAPTED_TEST_SIZE = 294
PAPER_ADAPTED_LAUNCH_NUM_THREADS = 32
PAPER_ADAPTED_NUM_THREADS = min(PAPER_ADAPTED_LAUNCH_NUM_THREADS, os.cpu_count() or 1)
PAPER_ADAPTED_LOW_CONCURRENCY_NUM_THREADS = 1
TEXT_EXTENSIONS = {".json", ".jsonl", ".log", ".md", ".txt", ".yaml", ".yml"}
RUN_ERROR_MARKERS = (
    "litellm.Timeout",
    "APITimeoutError",
    "ReadTimeout",
    "RateLimitError",
    "exceeded your current request limit",
)
PROVIDER_REJECTION_AUDIT_FILENAME = "provider_rejections.json"
PROVIDER_REJECTION_MESSAGE_MAX_CHARS = 500
IFBENCH_EVIDENCE_DIR_NAME = "evidence"
IFBENCH_EVIDENCE_JSONL_FILENAME = "ifbench_evidence.jsonl"
IFBENCH_EVIDENCE_SUMMARY_FILENAME = "ifbench_evidence_summary.json"
DEFAULT_IFBENCH_EVIDENCE_REPORT_DIR = PROJECT_ROOT / "reports" / "ifbench_qwen3_evidence_replay"
PROVIDER_CONTENT_REJECTION_MARKERS = (
    "data_inspection_failed",
    "inappropriate content",
    "input data may contain inappropriate content",
)
WINDOWS_MAX_PATH = 260
GEPA_DEEPEST_RELATIVE_PATH = Path(
    "generated_best_outputs_valset/task_0/iter_0_prog_0.json"
)


class SmokeError(RuntimeError):
    pass


class ProviderContentRejectionAudit:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[dict[str, Any]] = []

    def record(
        self,
        scope: str,
        exc: BaseException,
        example_key: str | None = None,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "scope": scope,
            "example_key": example_key,
            "error_type": exc.__class__.__name__,
            "message": summarize_provider_rejection(exc),
        }
        with self._lock:
            self._events.append(event)
        return event

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            events = [dict(event) for event in self._events]
        counts_by_scope: dict[str, int] = {}
        counts_by_key: dict[str, int] = {}
        for event in events:
            scope = str(event.get("scope") or "unknown")
            counts_by_scope[scope] = counts_by_scope.get(scope, 0) + 1
            example_key = event.get("example_key")
            if example_key is not None:
                key = str(example_key)
                counts_by_key[key] = counts_by_key.get(key, 0) + 1
        return {
            "total_events": len(events),
            "counts_by_scope": counts_by_scope,
            "counts_by_key": counts_by_key,
            "events": events,
        }

    def write(self, run_dir: Path) -> Path:
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / PROVIDER_REJECTION_AUDIT_FILENAME
        path.write_text(
            json.dumps(self.snapshot(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        description="运行官方 GEPA artifact 的 IFBench + Qwen3 DashScope adapted 实验。"
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
    parser.add_argument(
        "--paper-adapted",
        action="store_true",
        help=(
            "启用论文级云 API 适配口径：IFBench 300/300/294，GEPA budget=3593，"
            "并保留原 GEPA 默认行为。"
        ),
    )
    parser.add_argument(
        "--cloud-low-concurrency",
        action="store_true",
        help="仅用于 paper-adapted 云 API 路线，将运行线程固定为 1 并显式标注运行层适配。",
    )
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
        "--export-ifbench-evidence",
        action="store_true",
        help="运行结束后导出 IFBench 样本级 prompt、原始回答、metric 与异常状态证据。",
    )
    parser.add_argument(
        "--evidence-report-dir",
        default=str(DEFAULT_IFBENCH_EVIDENCE_REPORT_DIR),
        help="额外保存 IFBench evidence 汇总的项目报告目录。",
    )
    parser.add_argument(
        "--recovery-tag",
        default="recovered-final-eval",
        help="恢复评测输出目录后缀。",
    )
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--worker-recover", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(raw_argv)
    apply_paper_adapted_defaults(args, raw_argv)
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


def option_was_provided(argv: list[str], option: str) -> bool:
    return any(item == option or item.startswith(f"{option}=") for item in argv)


def apply_paper_adapted_defaults(args: argparse.Namespace, argv: list[str]) -> None:
    if not args.paper_adapted:
        if args.cloud_low_concurrency:
            raise SmokeError("`--cloud-low-concurrency` 必须与 `--paper-adapted` 同时使用。")
        return
    if args.split_seed is not None:
        raise SmokeError("`--paper-adapted` 保留 artifact 前缀切分，不允许同时使用 `--split-seed`。")

    paper_num_threads = (
        PAPER_ADAPTED_LOW_CONCURRENCY_NUM_THREADS
        if args.cloud_low_concurrency
        else PAPER_ADAPTED_NUM_THREADS
    )
    for field_name, option_name, paper_value in (
        ("train_size", "--train-size", PAPER_ADAPTED_TRAIN_SIZE),
        ("val_size", "--val-size", PAPER_ADAPTED_VAL_SIZE),
        ("test_size", "--test-size", PAPER_ADAPTED_TEST_SIZE),
        ("num_threads", "--num-threads", paper_num_threads),
    ):
        if option_was_provided(argv, option_name) and getattr(args, field_name) != paper_value:
            raise SmokeError(f"`--paper-adapted` 要求 `{option_name}` 为 {paper_value}。")
        setattr(args, field_name, paper_value)

    if args.optimizer == "GEPA":
        if (
            option_was_provided(argv, "--max-metric-calls")
            and args.max_metric_calls != PAPER_ADAPTED_MAX_METRIC_CALLS
        ):
            raise SmokeError(
                f"`--paper-adapted` 的 GEPA budget 必须是 {PAPER_ADAPTED_MAX_METRIC_CALLS}。"
            )
        args.max_metric_calls = PAPER_ADAPTED_MAX_METRIC_CALLS

    if not option_was_provided(argv, "--lm-name") and args.lm_name == DEFAULT_LM_NAME:
        args.lm_name = DEFAULT_PAPER_ADAPTED_LM_NAME


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
    if getattr(args, "paper_adapted", False):
        return PAPER_ADAPTED_GEPA_OPTIMIZER_NAME
    return GEPA_TINY_OPTIMIZER_NAME


def resolve_lm_name(args: argparse.Namespace) -> str:
    if args.split_seed is None:
        return args.lm_name
    suffix = f"-split{args.split_seed}"
    if args.lm_name.endswith(suffix):
        return args.lm_name
    return f"{args.lm_name}{suffix}"


def build_reproduction_type(args: argparse.Namespace) -> str:
    if getattr(args, "paper_adapted", False):
        suffix = "_low_concurrency" if getattr(args, "cloud_low_concurrency", False) else ""
        if args.optimizer == "Baseline":
            return f"artifact_ifbench_dashscope_qwen3_paper_adapted_baseline{suffix}"
        return f"artifact_ifbench_dashscope_qwen3_paper_adapted_gepa{suffix}"
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


def build_gepa_init_args(args: argparse.Namespace) -> dict[str, Any]:
    init_args = {
        "run_linearized_gepa": False,
        "use_merge": False,
        "set_for_merge_minibatch": "val",
        "track_scores_on": "val",
        "max_metric_calls": args.max_metric_calls,
    }
    if getattr(args, "cloud_low_concurrency", False):
        init_args["num_threads"] = args.num_threads
    if not args.paper_adapted:
        init_args["skip_perfect_score"] = False
    return init_args


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
    value = read_example_field(example, "key")
    return None if value is None else str(value)


def read_example_field(example: Any, field_name: str) -> Any | None:
    if isinstance(example, dict):
        return example.get(field_name)
    try:
        return example[field_name]
    except (KeyError, TypeError):
        return getattr(example, field_name, None)


def read_example_prompt(example: Any) -> str | None:
    value = read_example_field(example, "prompt")
    return None if value is None else str(value)


def read_example_instruction_ids(example: Any) -> list[str]:
    value = read_example_field(example, "instruction_id_list")
    if value is None:
        value = read_example_field(example, "instruction_ids")
    if value is None:
        value = read_example_field(example, "instruction_id")
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def build_instruction_group(instruction_ids: list[str]) -> str:
    if not instruction_ids:
        return "unknown"
    first = instruction_ids[0]
    for delimiter in (":", "/", "."):
        if delimiter in first:
            group = first.split(delimiter, 1)[0].strip()
            return group or "unknown"
    return first.strip() or "unknown"


def summarize_provider_rejection(exc: BaseException) -> str:
    message = " ".join(str(exc).split())
    return message[:PROVIDER_REJECTION_MESSAGE_MAX_CHARS]


def is_provider_content_rejection(exc: BaseException) -> bool:
    text = f"{exc.__class__.__module__}.{exc.__class__.__name__} {exc}".lower()
    return any(marker in text for marker in PROVIDER_CONTENT_REJECTION_MARKERS)


def load_provider_rejection_audit(run_dir: Path) -> dict[str, Any]:
    path = run_dir / PROVIDER_REJECTION_AUDIT_FILENAME
    if not path.exists():
        return {
            "total_events": 0,
            "counts_by_scope": {},
            "counts_by_key": {},
            "events": [],
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SmokeError(f"provider rejection 审计文件 JSON 解析失败：{path}") from exc
    if not isinstance(payload, dict):
        raise SmokeError(f"provider rejection 审计文件顶层必须是对象：{path}")
    return payload


def handle_program_provider_rejection(
    original_call: Any,
    prediction_factory: Any,
    audit: ProviderContentRejectionAudit,
    example_key: str | None,
    *call_args: Any,
    **call_kwargs: Any,
) -> Any:
    try:
        return original_call(*call_args, **call_kwargs)
    except Exception as exc:
        if not is_provider_content_rejection(exc):
            raise
        audit.record("program_prediction", exc, example_key=example_key)
        return prediction_factory(response="")


def build_gepa_instruction_prompt(
    prompt: str,
    current_instruction_doc: str,
    user_examples_and_feedback: str,
    reference_materials: str | None = None,
) -> str:
    full_prompt = prompt.replace("<curr_instructions>", current_instruction_doc)
    full_prompt = full_prompt.replace("<inputs_outputs_feedback>", user_examples_and_feedback)
    if reference_materials is not None:
        full_prompt = full_prompt.replace("<reference_materials>", reference_materials)
    return full_prompt


def extract_gepa_instruction_response(lm_out: str) -> str:
    lm_out = lm_out.strip()
    if lm_out.count("```") >= 2:
        start = lm_out.find("```")
        end = lm_out.rfind("```")
        if start >= end or start == -1 or end == -1:
            return lm_out
        return lm_out[start + 3 : end].strip()
    if lm_out.startswith("```"):
        lm_out = lm_out[3:]
    if lm_out.endswith("```"):
        lm_out = lm_out[:-3]
    return lm_out


def call_instruction_lm_with_provider_rejection(
    prompt: str,
    lm: Any,
    current_instruction_doc: str,
    user_examples_and_feedback: str,
    max_tokens: int,
    audit: ProviderContentRejectionAudit | None = None,
    reference_materials: str | None = None,
) -> str:
    full_prompt = build_gepa_instruction_prompt(
        prompt,
        current_instruction_doc,
        user_examples_and_feedback,
        reference_materials,
    )
    try:
        lm_out = lm(full_prompt, max_tokens=max_tokens)[0].strip()
    except Exception as exc:
        if not is_provider_content_rejection(exc):
            raise
        if audit is not None:
            audit.record("instruction_proposal", exc)
        return current_instruction_doc
    return extract_gepa_instruction_response(lm_out)


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
    if os.name != "nt" or optimizer_name == BASELINE_OPTIMIZER_NAME:
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


def load_metric_log_records(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "metric_logs" / "test.jsonl"
    if not path.exists():
        raise SmokeError(f"未找到 metric log：{path}")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise SmokeError(f"metric log 第 {line_number} 行 JSON 解析失败：{path}") from exc
            if isinstance(payload, dict):
                records.append(payload)
    return records


def to_json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except TypeError:
        return str(value)


def read_prediction_field(prediction: Any, field_name: str) -> Any | None:
    if prediction is None:
        return None
    if isinstance(prediction, dict):
        return prediction.get(field_name)
    try:
        return prediction[field_name]
    except (KeyError, TypeError):
        return getattr(prediction, field_name, None)


def extract_prediction_response(prediction: Any) -> str | None:
    if prediction is None:
        return None
    if isinstance(prediction, str):
        return prediction
    if isinstance(prediction, (int, float, bool)):
        return str(prediction)
    for field_name in (
        "response",
        "answer",
        "output",
        "completion",
        "text",
        "raw_response",
        "full_assistant_response",
    ):
        value = read_prediction_field(prediction, field_name)
        if value is None:
            continue
        if isinstance(value, str):
            return value
        return str(value)
    nested = read_prediction_field(prediction, "prediction")
    if nested is not None and nested is not prediction:
        return extract_prediction_response(nested)
    return None


def collect_values_by_key(value: Any, target_keys: set[str], max_items: int = 20) -> list[Any]:
    results: list[Any] = []

    def visit(node: Any) -> None:
        if len(results) >= max_items:
            return
        if isinstance(node, dict):
            for key, child in node.items():
                if key in target_keys:
                    if isinstance(child, list):
                        results.extend(child[: max_items - len(results)])
                    else:
                        results.append(child)
                    if len(results) >= max_items:
                        return
                visit(child)
                if len(results) >= max_items:
                    return
        elif isinstance(node, list):
            for child in node:
                visit(child)
                if len(results) >= max_items:
                    return

    visit(value)
    return to_json_safe(results)


def metric_record_parse_failed(record: dict[str, Any] | None) -> bool:
    if record is None:
        return True
    if record.get("recovery_status") == "filled_missing_metric_row":
        return True
    prediction = record.get("prediction")
    if prediction is None and record.get("metric_output") == 0:
        return True
    status = str(record.get("status") or record.get("error") or "").lower()
    return "parse" in status or "failed" in status


def safe_report_stem(run_dir: Path) -> str:
    stem = run_dir.name.strip() or "ifbench-run"
    safe_chars = []
    for char in stem:
        if char.isalnum() or char in ("-", "_", "."):
            safe_chars.append(char)
        else:
            safe_chars.append("_")
    return "".join(safe_chars)


def export_ifbench_evidence(
    run_dir: Path,
    test_items: list[Any],
    provider_rejections: dict[str, Any] | None = None,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    metric_records = load_metric_log_records(run_dir)
    records_by_index: dict[int, dict[str, Any]] = {}
    for record in metric_records:
        idx = record.get("idx_in_split")
        if isinstance(idx, int) and idx not in records_by_index:
            records_by_index[idx] = record

    provider_counts_by_key = {}
    if isinstance(provider_rejections, dict):
        raw_counts = provider_rejections.get("counts_by_key")
        if isinstance(raw_counts, dict):
            provider_counts_by_key = {str(key): int(value) for key, value in raw_counts.items()}

    evidence_rows: list[dict[str, Any]] = []
    for idx, example in enumerate(test_items):
        record = records_by_index.get(idx)
        example_key = read_example_key(example)
        instruction_ids = read_example_instruction_ids(example)
        prediction_payload = None if record is None else to_json_safe(record.get("prediction"))
        raw_response = extract_prediction_response(prediction_payload)
        finish_reasons = collect_values_by_key(
            record or {},
            {"finish_reason", "finish_reasons"},
        )
        provider_rejection_count = provider_counts_by_key.get(str(example_key), 0)
        evidence_rows.append(
            {
                "idx_in_split": idx,
                "example_key": example_key,
                "prompt": read_example_prompt(example),
                "instruction_id_list": instruction_ids,
                "instruction_group": build_instruction_group(instruction_ids),
                "metric_record_available": record is not None,
                "metric_output": None if record is None else record.get("metric_output"),
                "raw_response": raw_response,
                "prediction_payload": prediction_payload,
                "finish_reasons": finish_reasons,
                "parse_failure": metric_record_parse_failed(record),
                "provider_rejection": provider_rejection_count > 0,
                "provider_rejection_count": provider_rejection_count,
                "recovery_status": None if record is None else record.get("recovery_status"),
                "recovery_reason": None if record is None else record.get("recovery_reason"),
            }
        )

    evidence_dir = run_dir / IFBENCH_EVIDENCE_DIR_NAME
    evidence_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = evidence_dir / IFBENCH_EVIDENCE_JSONL_FILENAME
    with jsonl_path.open("w", encoding="utf-8", newline="") as handle:
        for row in evidence_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    metric_sum = sum(
        float(row["metric_output"])
        for row in evidence_rows
        if isinstance(row.get("metric_output"), (int, float))
    )
    summary = {
        "run_dir": str(run_dir),
        "evidence_jsonl": str(jsonl_path),
        "expected_test_items": len(test_items),
        "metric_records": len(metric_records),
        "evidence_rows": len(evidence_rows),
        "missing_metric_records": sum(
            1 for row in evidence_rows if not row["metric_record_available"]
        ),
        "parse_failure_count": sum(1 for row in evidence_rows if row["parse_failure"]),
        "provider_rejection_count": sum(
            int(row["provider_rejection_count"]) for row in evidence_rows
        ),
        "raw_response_available_count": sum(
            1 for row in evidence_rows if row.get("raw_response") is not None
        ),
        "metric_sum": metric_sum,
        "score_percent": round(metric_sum / len(test_items) * 100, 6)
        if test_items
        else None,
        "schema": [
            "idx_in_split",
            "example_key",
            "prompt",
            "instruction_id_list",
            "instruction_group",
            "metric_record_available",
            "metric_output",
            "raw_response",
            "prediction_payload",
            "finish_reasons",
            "parse_failure",
            "provider_rejection",
            "provider_rejection_count",
            "recovery_status",
            "recovery_reason",
        ],
    }
    summary_path = evidence_dir / IFBENCH_EVIDENCE_SUMMARY_FILENAME
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        report_stem = safe_report_stem(run_dir)
        report_jsonl_path = report_dir / f"{report_stem}_{IFBENCH_EVIDENCE_JSONL_FILENAME}"
        report_summary_path = report_dir / f"{report_stem}_{IFBENCH_EVIDENCE_SUMMARY_FILENAME}"
        shutil.copy2(jsonl_path, report_jsonl_path)
        report_summary = dict(summary)
        report_summary["report_evidence_jsonl"] = str(report_jsonl_path)
        report_summary["report_summary"] = str(report_summary_path)
        report_summary_path.write_text(
            json.dumps(report_summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary_path.write_text(
            json.dumps(report_summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary = report_summary

    return summary


def load_ifbench_evidence_summary(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / IFBENCH_EVIDENCE_DIR_NAME / IFBENCH_EVIDENCE_SUMMARY_FILENAME
    if not path.exists():
        return None
    payload = load_json_file(path)
    return payload


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
    if args.paper_adapted:
        command.append("--paper-adapted")
    if args.cloud_low_concurrency:
        command.append("--cloud-low-concurrency")
    if args.split_seed is not None:
        command.extend(["--split-seed", str(args.split_seed)])
    if args.enable_thinking:
        command.append("--enable-thinking")
    if args.skip_probe:
        command.append("--skip-probe")
    if args.export_ifbench_evidence:
        command.append("--export-ifbench-evidence")
        command.extend(["--evidence-report-dir", args.evidence_report_dir])
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
    provider_rejections = load_provider_rejection_audit(run_dir)
    evidence_summary = load_ifbench_evidence_summary(run_dir)
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
        "paper_adapted": args.paper_adapted,
        "cloud_low_concurrency": args.cloud_low_concurrency,
        "evaluation_result": evaluation_result,
        "provider_rejections": provider_rejections,
        "ifbench_evidence": evidence_summary,
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

    import dspy
    from gepa_artifact.benchmarks.IFBench import benchmark as ifbench_benchmark
    from gepa_artifact.benchmarks.IFBench.ifbench_data import IFBench
    from gepa_artifact.benchmarks.IFBench.ifbench_program import IFBenchCoT2StageProgram
    from gepa_artifact.utils.optimizers import OptimizerConfig
    from dspy.utils.parallelizer import ParallelExecutor
    import scripts.run_experiments as runner

    original_init_dataset = IFBench.init_dataset
    original_program_call = IFBenchCoT2StageProgram.__call__
    original_parallel_executor_init = ParallelExecutor.__init__
    optimizer_name = resolve_optimizer_name(args)
    effective_lm_name = resolve_lm_name(args)
    run_dir = build_run_dir(effective_lm_name, args.seed, optimizer_name)
    split_manifest_payload: dict[str, Any] | None = None
    selected_test_items: list[Any] | None = None
    prompt_to_key: dict[str, str | None] = {}
    provider_rejection_audit = ProviderContentRejectionAudit()

    def patched_parallel_executor_init(self: Any, *init_args: Any, **init_kwargs: Any) -> Any:
        init_kwargs["timeout"] = args.parallel_straggler_timeout_seconds
        return original_parallel_executor_init(self, *init_args, **init_kwargs)

    def patched_init_dataset(self: Any) -> None:
        nonlocal selected_test_items, split_manifest_payload
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
        selected_test_items = list(self.test_set)
        self.dataset = self.train_set + self.val_set + self.test_set
        prompt_to_key.clear()
        for item in self.dataset:
            prompt = read_example_prompt(item)
            if prompt is not None and prompt not in prompt_to_key:
                prompt_to_key[prompt] = read_example_key(item)
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

    def patched_ifbench_program_call(self: Any, *call_args: Any, **call_kwargs: Any) -> Any:
        prompt = call_kwargs.get("prompt")
        if prompt is None and call_args:
            prompt = call_args[0]
        example_key = prompt_to_key.get(str(prompt)) if prompt is not None else None
        return handle_program_provider_rejection(
            original_program_call,
            dspy.Prediction,
            provider_rejection_audit,
            example_key,
            self,
            *call_args,
            **call_kwargs,
        )

    def create_lm(lm_config: dict[str, Any]) -> Any:
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
    IFBenchCoT2StageProgram.__call__ = patched_ifbench_program_call
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
            return call_instruction_lm_with_provider_rejection(
                prompt=prompt,
                lm=lm,
                current_instruction_doc=current_instruction_doc,
                user_examples_and_feedback=user_examples_and_feedback,
                reference_materials=reference_materials,
                max_tokens=args.max_tokens,
                audit=provider_rejection_audit,
            )

        GEPA.__init__ = patched_gepa_init
        instruction_proposal.call_lm_and_extract_response = patched_call_lm_and_extract_response
        runner.wandb_api_key = ""
        return OptimizerConfig(
            optimizer=GEPA,
            init_args=build_gepa_init_args(args),
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

    try:
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
    finally:
        provider_rejection_audit.write(run_dir)
    if split_manifest_payload is None:
        raise SmokeError("IFBench 数据集未初始化，无法写入 split manifest。")
    write_split_manifest(run_dir, split_manifest_payload)
    if args.export_ifbench_evidence:
        if selected_test_items is None:
            raise SmokeError("IFBench test set 未初始化，无法导出 evidence。")
        export_ifbench_evidence(
            run_dir=run_dir,
            test_items=selected_test_items,
            provider_rejections=provider_rejection_audit.snapshot(),
            report_dir=Path(args.evidence_report_dir),
        )
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
