from __future__ import annotations

import argparse
import importlib.util
import json
import os
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openai import OpenAI

from src.logging_utils import create_run_dir, create_timestamp, write_json, write_text


DEFAULT_OUTPUT_DIR = "outputs/stage4b_mimo_streaming_extended_timeout_diagnostic"
DEFAULT_REPORT_PATH = "reports/stage4b_mimo_streaming_extended_timeout_diagnostic_result.md"
DEFAULT_SAMPLE_IDS: tuple[str, ...] = ("test-1", "test-2", "test-3", "test-4", "test-5")
DEFAULT_SLEEP_SECONDS = 60.0
DEFAULT_APPLICATION_WALL_CLOCK_TIMEOUT_SECONDS = 600.0
DEFAULT_SDK_TIMEOUT_SECONDS = 600.0
STREAMING_MODE = "streaming"

DIAGNOSTIC_FLAGS: dict[str, bool] = {
    "diagnostic_only": True,
    "not_gepa_result": True,
    "not_official_budget": True,
    "not_model_ranking": True,
    "not_performance_claim": True,
    "streaming_path_only": True,
    "extended_timeout_diagnostic": True,
    "not_strict_non_streaming_path": True,
    "not_strict_60s_comparison": True,
    "mimo_only": True,
    "no_gepa_optimize_called": True,
    "stage4b_mimo_streaming_extended_timeout_diagnostic": True,
}


class Stage4BMiMoStreamingExtendedTimeoutDiagnosticError(RuntimeError):
    """MiMo streaming extended-timeout diagnostic 的配置或 artifact 不满足要求。"""


class ApplicationWallClockTimeout(RuntimeError):
    """应用层墙钟超时。"""


@dataclass(frozen=True)
class PromptVariantSpec:
    name: str
    label: str
    prompt_variant: str
    system_prompt: str
    description: str


def _load_stage4b_base_module() -> ModuleType:
    script_path = PROJECT_ROOT / "scripts" / "stage4b_eval_fixed_prompt_aime_mimopro_glm47.py"
    spec = importlib.util.spec_from_file_location("stage4b_mimo_streaming_extended_timeout_base_script", script_path)
    if spec is None or spec.loader is None:
        raise Stage4BMiMoStreamingExtendedTimeoutDiagnosticError(
            f"无法加载 Stage 4B base script：{script_path}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_stage4b_base_module()

PROMPT_VARIANTS: dict[str, PromptVariantSpec] = {
    "l4_strong_format": PromptVariantSpec(
        name="l4_strong_format",
        label="L4",
        prompt_variant="strong_format_seed_prompt",
        system_prompt=BASE.PROMPTS["strong_format_seed_prompt"],
        description="AIME question + strong_format_seed_prompt。",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage 4B MiMo streaming extended-timeout diagnostic。默认 dry-run，只有 --execute 才调用模型。"
    )
    parser.add_argument("--provider", choices=("mimo",), default="mimo", help="当前仅允许 mimo。")
    parser.add_argument("--api-key-env", default="MIMO_API_KEY", help="MiMo API key 的环境变量名。")
    parser.add_argument("--api-base-env", default="MIMO_API_BASE", help="MiMo API base 的环境变量名。")
    parser.add_argument("--model-env", default="MIMO_MODEL", help="MiMo model 的环境变量名。")
    parser.add_argument(
        "--backend-path",
        choices=("raw_sdk",),
        default="raw_sdk",
        help="当前只允许 raw_sdk。",
    )
    parser.add_argument(
        "--sample-ids",
        nargs="+",
        default=list(DEFAULT_SAMPLE_IDS),
        help="要执行的 sample_id 列表，默认 test-1 到 test-5。",
    )
    parser.add_argument(
        "--prompt-variant",
        choices=tuple(PROMPT_VARIANTS.keys()),
        default="l4_strong_format",
        help="当前默认且仅建议使用 L4 strong_format_seed_prompt。",
    )
    parser.add_argument(
        "--application-wall-clock-timeout",
        type=float,
        default=DEFAULT_APPLICATION_WALL_CLOCK_TIMEOUT_SECONDS,
        help="应用层墙钟超时秒数。",
    )
    parser.add_argument(
        "--sdk-timeout",
        type=float,
        default=DEFAULT_SDK_TIMEOUT_SECONDS,
        help="SDK timeout 秒数。",
    )
    parser.add_argument(
        "--sleep-between-requests",
        type=float,
        default=DEFAULT_SLEEP_SECONDS,
        help="相邻 AIME 请求之间的等待秒数。",
    )
    parser.add_argument("--max-retries", type=int, default=0, help="单请求重试次数。")
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="输出目录根路径。",
    )
    parser.add_argument(
        "--report-path",
        default=DEFAULT_REPORT_PATH,
        help="结果报告输出路径。",
    )
    parser.add_argument("--run-dir", default=None, help="复用已有 run_dir；默认创建新目录。")
    parser.add_argument("--execute", action="store_true", help="显式执行真实 diagnostic。")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def project_relative(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def build_provider_config(args: argparse.Namespace) -> Any:
    api_key = str(os.getenv(args.api_key_env) or "").strip()
    api_base = str(os.getenv(args.api_base_env) or "").strip()
    model = str(os.getenv(args.model_env) or "").strip()
    return BASE.ProviderConfig(
        provider="mimo",
        api_base=api_base,
        api_key_env=str(args.api_key_env),
        api_key=api_key,
        model=model,
        litellm_provider_string=None,
    )


def enforce_bounds(args: argparse.Namespace) -> None:
    if args.provider != "mimo":
        raise Stage4BMiMoStreamingExtendedTimeoutDiagnosticError("当前脚本只允许 provider=mimo。")
    if args.backend_path != "raw_sdk":
        raise Stage4BMiMoStreamingExtendedTimeoutDiagnosticError("当前脚本只允许 backend_path=raw_sdk。")
    if args.max_retries < 0:
        raise Stage4BMiMoStreamingExtendedTimeoutDiagnosticError("--max-retries 不能小于 0。")
    if args.max_retries != 0:
        raise Stage4BMiMoStreamingExtendedTimeoutDiagnosticError("当前诊断固定要求 max_retries=0。")
    if args.sleep_between_requests < 0:
        raise Stage4BMiMoStreamingExtendedTimeoutDiagnosticError("--sleep-between-requests 不能小于 0。")
    if not args.sample_ids:
        raise Stage4BMiMoStreamingExtendedTimeoutDiagnosticError("--sample-ids 不能为空。")
    if len(args.sample_ids) > 5:
        raise Stage4BMiMoStreamingExtendedTimeoutDiagnosticError("当前 streaming extended-timeout 最多只允许 5 个样本。")
    if any(not re.fullmatch(r"test-\d+", str(sample_id)) for sample_id in args.sample_ids):
        raise Stage4BMiMoStreamingExtendedTimeoutDiagnosticError("sample_id 必须是 test-<n> 形式。")
    if float(args.application_wall_clock_timeout) <= 0:
        raise Stage4BMiMoStreamingExtendedTimeoutDiagnosticError(
            "--application-wall-clock-timeout 必须大于 0。"
        )
    if float(args.sdk_timeout) <= 0:
        raise Stage4BMiMoStreamingExtendedTimeoutDiagnosticError("--sdk-timeout 必须大于 0。")


def load_prompt_variant(name: str) -> PromptVariantSpec:
    try:
        return PROMPT_VARIANTS[str(name)]
    except KeyError as exc:
        raise Stage4BMiMoStreamingExtendedTimeoutDiagnosticError(f"未知 prompt variant：{name}") from exc


def build_selected_samples(sample_ids: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    limit = max(int(str(sample_id).split("-")[-1]) for sample_id in sample_ids)
    if limit > 5:
        raise Stage4BMiMoStreamingExtendedTimeoutDiagnosticError("当前只允许访问前 5 个样本。")
    dataset, dataset_meta = BASE.load_official_dataset_for_execute(limit)
    selected: list[dict[str, Any]] = []
    requested = set(sample_ids)
    for sample_index, sample in enumerate(dataset, start=1):
        sample_id = BASE.build_sample_id(sample, dataset_meta["split"], sample_index)
        if sample_id not in requested:
            continue
        selected.append(
            {
                "sample_id": sample_id,
                "sample_index": sample_index,
                "sample": sample,
                "question": str(sample.get("input") or ""),
                "gold": str(sample.get("answer") or ""),
            }
        )
    found = {entry["sample_id"] for entry in selected}
    missing = [sample_id for sample_id in sample_ids if sample_id not in found]
    if missing:
        raise Stage4BMiMoStreamingExtendedTimeoutDiagnosticError(
            f"指定的 sample_id 不在可访问样本内：{', '.join(missing)}"
        )
    dataset_meta = dict(dataset_meta)
    dataset_meta["selected_sample_ids"] = [entry["sample_id"] for entry in selected]
    dataset_meta["selected_count"] = len(selected)
    dataset_meta["subset_selector"] = "explicit_sample_ids"
    return selected, dataset_meta


def build_messages(*, prompt_variant: PromptVariantSpec, question: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": prompt_variant.system_prompt},
        {"role": "user", "content": question},
    ]


def make_prompt_spec(prompt_variant: PromptVariantSpec) -> Any:
    return BASE.PromptSpec(name=prompt_variant.prompt_variant, system_prompt=prompt_variant.system_prompt)


def normalize_stream_chunk_payload(chunk: Any) -> dict[str, Any] | None:
    payload = BASE.to_jsonable(chunk)
    if not isinstance(payload, dict):
        return None
    nested = payload.get("payload")
    if isinstance(nested, dict) and "choices" in nested:
        return nested
    return payload


def extract_reasoning_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    parts: list[str] = []
    if isinstance(value, dict):
        reasoning_content = value.get("reasoning_content")
        if isinstance(reasoning_content, str):
            parts.append(reasoning_content)
        elif isinstance(reasoning_content, list):
            parts.extend(str(item) for item in reasoning_content if isinstance(item, str))
        content = value.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "").lower()
                if item_type.startswith("reason"):
                    text_value = item.get("text")
                    if isinstance(text_value, str):
                        parts.append(text_value)
    return "".join(parts)


def extract_stream_chunk_fields(chunk_payload: dict[str, Any]) -> tuple[str, str, str | None]:
    choices = chunk_payload.get("choices")
    if not isinstance(choices, list):
        return "", "", None
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    finish_reason: str | None = None
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        finish_reason = finish_reason or choice.get("finish_reason")
        delta = choice.get("delta")
        if delta is None:
            delta = choice.get("message")
        content_parts.append(BASE.extract_message_content(delta))
        reasoning_parts.append(extract_reasoning_text(delta))
    return "".join(content_parts), "".join(reasoning_parts), finish_reason


def extract_error_code(record: dict[str, Any]) -> str | None:
    body = str(record.get("error_body_sanitized") or "")
    message = str(record.get("error_message_sanitized") or "")
    for text in (body, message):
        if not text:
            continue
        match = re.search(r'"code"\s*:\s*"?(?P<code>[0-9A-Za-z_-]+)"?', text)
        if match:
            return match.group("code")
        match = re.search(r"'code'\s*:\s*'(?P<code>[0-9A-Za-z_-]+)'", text)
        if match:
            return match.group("code")
    return None


def is_rate_limit_record(record: dict[str, Any]) -> bool:
    if record.get("http_status") == 429:
        return True
    if str(record.get("error_type")) == "RateLimitError":
        return True
    message = str(record.get("error_message_sanitized") or "").lower()
    return "429" in message or "rate limit" in message


def classify_prediction(*, content: str, gold: str) -> dict[str, Any]:
    payload = BASE.classify_prediction(content=content, gold=gold)
    payload["relaxed_extractable_correct"] = bool(payload["relaxed_extractable_correct"])
    return payload


def save_raw_payload(*, run_dir: Path, record: dict[str, Any], payload: dict[str, Any]) -> str:
    raw_dir = run_dir / "raw_responses"
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_name = "__".join(
        [
            BASE.slugify(record["provider"]),
            BASE.slugify(record["mode"]),
            BASE.slugify(record["prompt_variant"]),
            BASE.slugify(record["sample_id"]),
        ]
    )
    raw_path = raw_dir / f"{file_name}.json"
    write_json(raw_path, payload)
    return project_relative(raw_path) or raw_path.name


def create_record(
    *,
    provider_config: Any,
    backend_path: str,
    prompt_variant: PromptVariantSpec,
    sample_id: str,
    gold: str,
    application_wall_clock_timeout_seconds: float,
    sdk_timeout_seconds: float,
    sleep_between_requests: float,
    max_retries: int,
) -> dict[str, Any]:
    prompt_spec = make_prompt_spec(prompt_variant)
    record = BASE.base_record(
        provider_config=provider_config,
        backend_path=backend_path,
        prompt_spec=prompt_spec,
        sample_id=sample_id,
        gold=gold,
    )
    record.update(
        {
            "mode": STREAMING_MODE,
            "prompt_variant_label": prompt_variant.label,
            "prompt_variant_description": prompt_variant.description,
            "application_wall_clock_timeout_seconds": application_wall_clock_timeout_seconds,
            "sdk_timeout_seconds": sdk_timeout_seconds,
            "sleep_between_requests": sleep_between_requests,
            "max_retries": max_retries,
            "started_at": None,
            "completed_at": None,
            "time_to_first_token_seconds": None,
            "time_to_complete_seconds": 0.0,
            "first_token_observed": False,
            "partial_content_nonempty": False,
            "reasoning_only_output": False,
            "timeout_enforced_by": None,
            "raw_response_path": None,
            "error_code": None,
            "provider_error": False,
            "rate_limit_observed": False,
            "stream_close_attempted": False,
            "stream_close_succeeded": False,
            **DIAGNOSTIC_FLAGS,
        }
    )
    return record


def create_health_record(
    *,
    provider_config: Any,
    backend_path: str,
    sdk_timeout_seconds: float,
    application_wall_clock_timeout_seconds: float,
    phase: str,
) -> dict[str, Any]:
    return {
        "provider": provider_config.provider,
        "model": provider_config.model,
        "backend_path": backend_path,
        "mode": STREAMING_MODE,
        "phase": phase,
        "prompt": "Return exactly: OK",
        "sdk_timeout_seconds": sdk_timeout_seconds,
        "application_wall_clock_timeout_seconds": application_wall_clock_timeout_seconds,
        "content_exact_ok": False,
        "content_preview": "",
        "latency_seconds": 0.0,
        "error_type": None,
        "error_message_sanitized": None,
        "http_status": None,
        "started_at": None,
        "completed_at": None,
        "raw_response_path": None,
        **DIAGNOSTIC_FLAGS,
    }


def _extract_stream_http_status(stream: Any) -> int | None:
    response = getattr(stream, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def _attempt_close_stream(stream: Any) -> tuple[bool, bool]:
    close_fn = getattr(stream, "close", None)
    if not callable(close_fn):
        return False, False
    try:
        close_fn()
        return True, True
    except Exception:
        return True, False


def _stream_worker(stream: Any, event_queue: queue.Queue[tuple[str, Any]]) -> None:
    try:
        for chunk in stream:
            event_queue.put(("chunk", chunk))
    except Exception as exc:  # pragma: no cover - 真实 provider 路径
        event_queue.put(("error", exc))
    finally:
        event_queue.put(("done", None))


def _apply_content_classification(record: dict[str, Any], *, content: str, gold: str) -> None:
    record["content_nonempty"] = bool(content.strip())
    record["partial_content_nonempty"] = bool(content.strip()) and not bool(record.get("request_completed"))
    if content.strip():
        record.update(classify_prediction(content=content, gold=gold))
    else:
        record["extracted_answer"] = None
        record["empty_or_invalid"] = True
        record["diagnosis"] = "empty_or_invalid"
    record["reasoning_only_output"] = bool(record.get("reasoning_content_present")) and not bool(content.strip())


def execute_health_check(
    *,
    provider_config: Any,
    backend_path: str,
    sdk_timeout_seconds: float,
    application_wall_clock_timeout_seconds: float,
    phase: str,
    run_dir: Path,
) -> dict[str, Any]:
    record = create_health_record(
        provider_config=provider_config,
        backend_path=backend_path,
        sdk_timeout_seconds=sdk_timeout_seconds,
        application_wall_clock_timeout_seconds=application_wall_clock_timeout_seconds,
        phase=phase,
    )
    missing = provider_config.missing_config_reasons()
    if missing:
        record["error_type"] = "ConfigMissing"
        record["error_message_sanitized"] = "; ".join(missing)
        return record

    secrets = [provider_config.api_key]
    messages = [{"role": "user", "content": "Return exactly: OK"}]
    record["started_at"] = now_iso()
    start_time = time.monotonic()
    try:
        client = OpenAI(
            api_key=provider_config.api_key,
            base_url=provider_config.api_base,
            timeout=float(sdk_timeout_seconds),
            max_retries=0,
        )
        stream = client.chat.completions.create(
            model=provider_config.model,
            messages=messages,
            temperature=0,
            timeout=float(sdk_timeout_seconds),
            stream=True,
        )
        record["http_status"] = _extract_stream_http_status(stream)
        content_parts: list[str] = []
        chunk_payloads: list[dict[str, Any]] = []
        try:
            for chunk in stream:
                chunk_payload = normalize_stream_chunk_payload(chunk)
                if isinstance(chunk_payload, dict):
                    chunk_payloads.append(chunk_payload)
                    chunk_content, _, _ = extract_stream_chunk_fields(chunk_payload)
                    if chunk_content:
                        content_parts.append(chunk_content)
        finally:
            attempted, succeeded = _attempt_close_stream(stream)
            record["stream_close_attempted"] = attempted
            record["stream_close_succeeded"] = succeeded
        content = "".join(content_parts)
        record["latency_seconds"] = round(time.monotonic() - start_time, 6)
        record["completed_at"] = now_iso()
        record["content_preview"] = BASE.sanitize_text(content, secrets=secrets, limit=120)
        record["content_exact_ok"] = content.strip() == "OK"
        record["raw_response_path"] = save_raw_payload(
            run_dir=run_dir,
            record={
                "provider": provider_config.provider,
                "mode": f"health_{STREAMING_MODE}_{phase}",
                "prompt_variant": "health_check",
                "sample_id": "health_check",
            },
            payload={
                "messages": messages,
                "content": content,
                "raw_payload": {"http_status": record["http_status"], "chunks": chunk_payloads},
            },
        )
        return record
    except Exception as exc:  # pragma: no cover - 真实 provider 路径
        record["latency_seconds"] = round(time.monotonic() - start_time, 6)
        record["completed_at"] = now_iso()
        record["error_type"] = type(exc).__name__
        record["http_status"] = BASE.extract_http_status_from_error(exc)
        error_message, _ = BASE.extract_error_message(exc, secrets=secrets)
        record["error_message_sanitized"] = error_message
        record["raw_response_path"] = save_raw_payload(
            run_dir=run_dir,
            record={
                "provider": provider_config.provider,
                "mode": f"health_{STREAMING_MODE}_{phase}",
                "prompt_variant": "health_check",
                "sample_id": "health_check",
            },
            payload={
                "messages": messages,
                "error_type": type(exc).__name__,
                "error_message_sanitized": error_message,
                "http_status": record["http_status"],
            },
        )
        return record


def execute_single_case(
    *,
    provider_config: Any,
    backend_path: str,
    prompt_variant: PromptVariantSpec,
    sample_entry: dict[str, Any],
    application_wall_clock_timeout_seconds: float,
    sdk_timeout_seconds: float,
    sleep_between_requests: float,
    max_retries: int,
    run_dir: Path,
) -> dict[str, Any]:
    record = create_record(
        provider_config=provider_config,
        backend_path=backend_path,
        prompt_variant=prompt_variant,
        sample_id=sample_entry["sample_id"],
        gold=sample_entry["gold"],
        application_wall_clock_timeout_seconds=application_wall_clock_timeout_seconds,
        sdk_timeout_seconds=sdk_timeout_seconds,
        sleep_between_requests=sleep_between_requests,
        max_retries=max_retries,
    )
    missing = provider_config.missing_config_reasons()
    if missing:
        record.update(
            {
                "status": "config_missing",
                "empty_or_invalid": True,
                "error_type": "ConfigMissing",
                "error_message_sanitized": "; ".join(missing),
                "diagnosis": "config_missing",
                "provider_error": True,
            }
        )
        return record

    secrets = [provider_config.api_key]
    messages = build_messages(prompt_variant=prompt_variant, question=sample_entry["question"])
    record["started_at"] = now_iso()
    start_time = time.monotonic()
    first_token_time: float | None = None
    finish_reason: str | None = None
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    chunk_payloads: list[dict[str, Any]] = []
    stream: Any = None
    worker: threading.Thread | None = None
    event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

    try:
        client = OpenAI(
            api_key=provider_config.api_key,
            base_url=provider_config.api_base,
            timeout=float(sdk_timeout_seconds),
            max_retries=0,
        )
        stream = client.chat.completions.create(
            model=provider_config.model,
            messages=messages,
            temperature=0,
            timeout=float(sdk_timeout_seconds),
            stream=True,
        )
        record["http_status"] = _extract_stream_http_status(stream)
        worker = threading.Thread(target=_stream_worker, args=(stream, event_queue), daemon=True)
        worker.start()

        while True:
            elapsed = time.monotonic() - start_time
            remaining = float(application_wall_clock_timeout_seconds) - elapsed
            if remaining <= 0:
                raise ApplicationWallClockTimeout("Application wall-clock timeout exceeded.")
            try:
                event_name, payload = event_queue.get(timeout=min(0.2, remaining))
            except queue.Empty:
                continue
            if event_name == "chunk":
                chunk_payload = normalize_stream_chunk_payload(payload)
                if not isinstance(chunk_payload, dict):
                    continue
                chunk_payloads.append(chunk_payload)
                chunk_content, chunk_reasoning, chunk_finish_reason = extract_stream_chunk_fields(chunk_payload)
                if first_token_time is None and (chunk_content or chunk_reasoning):
                    first_token_time = time.monotonic()
                if chunk_content:
                    content_parts.append(chunk_content)
                if chunk_reasoning:
                    reasoning_parts.append(chunk_reasoning)
                if chunk_finish_reason:
                    finish_reason = chunk_finish_reason
                continue
            if event_name == "error":
                raise payload
            if event_name == "done":
                break

        content = "".join(content_parts)
        reasoning_text = "".join(reasoning_parts)
        record["latency_seconds"] = round(time.monotonic() - start_time, 6)
        record["time_to_complete_seconds"] = record["latency_seconds"]
        record["completed_at"] = now_iso()
        record["status"] = "ok"
        record["completed"] = True
        record["request_completed"] = True
        record["finish_reason"] = finish_reason
        record["reasoning_content_present"] = bool(reasoning_text)
        record["first_token_observed"] = first_token_time is not None
        record["time_to_first_token_seconds"] = (
            round(first_token_time - start_time, 6) if first_token_time is not None else None
        )
        record["raw_response_preview"] = BASE.sanitize_text(content, secrets=secrets, limit=240)
        _apply_content_classification(record, content=content, gold=sample_entry["gold"])
        record["raw_response_path"] = save_raw_payload(
            run_dir=run_dir,
            record=record,
            payload={
                "provider": record["provider"],
                "model": record["model"],
                "backend_path": backend_path,
                "mode": STREAMING_MODE,
                "prompt_variant": prompt_variant.name,
                "sample_id": sample_entry["sample_id"],
                "question": sample_entry["question"],
                "gold": sample_entry["gold"],
                "messages": messages,
                "content": content,
                "reasoning_text": reasoning_text,
                "reasoning_content_present": record["reasoning_content_present"],
                "finish_reason": finish_reason,
                "http_status": record["http_status"],
                "raw_payload": {"http_status": record["http_status"], "chunks": chunk_payloads},
            },
        )
        return record
    except Exception as exc:  # pragma: no cover - 真实 provider 路径
        attempted = False
        succeeded = False
        if stream is not None:
            attempted, succeeded = _attempt_close_stream(stream)
        if attempted:
            record["stream_close_attempted"] = attempted
            record["stream_close_succeeded"] = succeeded
        if worker is not None and worker.is_alive():
            worker.join(timeout=1.0)

        content = "".join(content_parts)
        reasoning_text = "".join(reasoning_parts)
        record["latency_seconds"] = round(time.monotonic() - start_time, 6)
        record["time_to_complete_seconds"] = record["latency_seconds"]
        record["completed_at"] = now_iso()
        record["finish_reason"] = finish_reason
        record["reasoning_content_present"] = bool(reasoning_text)
        record["first_token_observed"] = first_token_time is not None
        record["time_to_first_token_seconds"] = (
            round(first_token_time - start_time, 6) if first_token_time is not None else None
        )
        record["raw_response_preview"] = BASE.sanitize_text(content, secrets=secrets, limit=240)

        if isinstance(exc, ApplicationWallClockTimeout):
            record.update(
                {
                    "status": "timeout",
                    "timeout": True,
                    "error_type": "ApplicationWallClockTimeout",
                    "error_message_sanitized": str(exc),
                    "diagnosis": "timeout",
                    "timeout_enforced_by": "application_wall_clock",
                }
            )
        else:
            record["http_status"] = record["http_status"] or BASE.extract_http_status_from_error(exc)
            error_message, error_body = BASE.extract_error_message(exc, secrets=secrets)
            timeout = BASE.is_timeout_error(exc)
            record.update(
                {
                    "status": "timeout" if timeout else "error",
                    "timeout": timeout,
                    "error_type": type(exc).__name__,
                    "error_message_sanitized": error_message,
                    "error_body_sanitized": error_body,
                    "diagnosis": "timeout" if timeout else "provider_error",
                    "provider_error": not timeout,
                    "timeout_enforced_by": "sdk_or_provider" if timeout else None,
                }
            )

        _apply_content_classification(record, content=content, gold=sample_entry["gold"])
        record["error_code"] = extract_error_code(record)
        record["rate_limit_observed"] = is_rate_limit_record(record)
        if record["timeout"] and record["timeout_enforced_by"] is None:
            record["timeout_enforced_by"] = "sdk_or_provider"
        if not content.strip() and not reasoning_text:
            record["empty_or_invalid"] = True

        record["raw_response_path"] = save_raw_payload(
            run_dir=run_dir,
            record=record,
            payload={
                "provider": record["provider"],
                "model": record["model"],
                "backend_path": backend_path,
                "mode": STREAMING_MODE,
                "prompt_variant": prompt_variant.name,
                "sample_id": sample_entry["sample_id"],
                "question": sample_entry["question"],
                "gold": sample_entry["gold"],
                "messages": messages,
                "content": content,
                "reasoning_text": reasoning_text,
                "reasoning_content_present": record["reasoning_content_present"],
                "finish_reason": finish_reason,
                "http_status": record["http_status"],
                "error_type": record["error_type"],
                "error_message_sanitized": record["error_message_sanitized"],
                "error_body_sanitized": record.get("error_body_sanitized"),
                "timeout_enforced_by": record.get("timeout_enforced_by"),
                "raw_payload": {"http_status": record["http_status"], "chunks": chunk_payloads},
            },
        )
        return record


def build_dry_run_records(
    *,
    provider_config: Any,
    backend_path: str,
    prompt_variant: PromptVariantSpec,
    sample_entries: list[dict[str, Any]],
    application_wall_clock_timeout_seconds: float,
    sdk_timeout_seconds: float,
    sleep_between_requests: float,
    max_retries: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    missing = provider_config.missing_config_reasons()
    for sample_entry in sample_entries:
        record = create_record(
            provider_config=provider_config,
            backend_path=backend_path,
            prompt_variant=prompt_variant,
            sample_id=sample_entry["sample_id"],
            gold=sample_entry["gold"],
            application_wall_clock_timeout_seconds=application_wall_clock_timeout_seconds,
            sdk_timeout_seconds=sdk_timeout_seconds,
            sleep_between_requests=sleep_between_requests,
            max_retries=max_retries,
        )
        record.update(
            {
                "status": "dry_run",
                "error_type": "ConfigPreview" if missing else None,
                "error_message_sanitized": "; ".join(missing) if missing else None,
                "diagnosis": "config_missing" if missing else "planned_only",
                "provider_error": bool(missing),
            }
        )
        records.append(record)
    return records


def build_dry_run_health_checks(
    *,
    provider_config: Any,
    backend_path: str,
    sdk_timeout_seconds: float,
    application_wall_clock_timeout_seconds: float,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    missing = provider_config.missing_config_reasons()
    for phase in ("pre", "post"):
        record = create_health_record(
            provider_config=provider_config,
            backend_path=backend_path,
            sdk_timeout_seconds=sdk_timeout_seconds,
            application_wall_clock_timeout_seconds=application_wall_clock_timeout_seconds,
            phase=phase,
        )
        if missing:
            record["error_type"] = "ConfigPreview"
            record["error_message_sanitized"] = "; ".join(missing)
        records.append(record)
    return records


def execute_plan(
    *,
    provider_config: Any,
    backend_path: str,
    prompt_variant: PromptVariantSpec,
    sample_entries: list[dict[str, Any]],
    application_wall_clock_timeout_seconds: float,
    sdk_timeout_seconds: float,
    sleep_between_requests: float,
    max_retries: int,
    run_dir: Path,
) -> dict[str, Any]:
    per_example_path = run_dir / "per_example_eval.jsonl"
    health_check_path = run_dir / "health_checks.jsonl"
    records: list[dict[str, Any]] = []
    health_checks: list[dict[str, Any]] = []

    pre_health = execute_health_check(
        provider_config=provider_config,
        backend_path=backend_path,
        sdk_timeout_seconds=sdk_timeout_seconds,
        application_wall_clock_timeout_seconds=application_wall_clock_timeout_seconds,
        phase="pre",
        run_dir=run_dir,
    )
    health_checks.append(pre_health)
    BASE.append_jsonl(health_check_path, [pre_health])

    for index, sample_entry in enumerate(sample_entries):
        if index > 0 and sleep_between_requests > 0:
            time.sleep(sleep_between_requests)
        record = execute_single_case(
            provider_config=provider_config,
            backend_path=backend_path,
            prompt_variant=prompt_variant,
            sample_entry=sample_entry,
            application_wall_clock_timeout_seconds=application_wall_clock_timeout_seconds,
            sdk_timeout_seconds=sdk_timeout_seconds,
            sleep_between_requests=sleep_between_requests,
            max_retries=max_retries,
            run_dir=run_dir,
        )
        records.append(record)
        BASE.append_jsonl(per_example_path, [record])

    post_health = execute_health_check(
        provider_config=provider_config,
        backend_path=backend_path,
        sdk_timeout_seconds=sdk_timeout_seconds,
        application_wall_clock_timeout_seconds=application_wall_clock_timeout_seconds,
        phase="post",
        run_dir=run_dir,
    )
    health_checks.append(post_health)
    BASE.append_jsonl(health_check_path, [post_health])

    BASE.write_jsonl(per_example_path, records)
    BASE.write_jsonl(health_check_path, health_checks)
    return {"records": records, "health_checks": health_checks}


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    latency_values = [float(item.get("latency_seconds", 0.0)) for item in records if item.get("latency_seconds")]
    ttft_values = [
        float(item["time_to_first_token_seconds"])
        for item in records
        if item.get("time_to_first_token_seconds") is not None
    ]
    complete_values = [
        float(item["time_to_complete_seconds"])
        for item in records
        if item.get("time_to_complete_seconds") is not None
    ]
    finish_reason_distribution: dict[str, int] = {}
    for item in records:
        finish_reason = str(item.get("finish_reason") or "null")
        finish_reason_distribution[finish_reason] = finish_reason_distribution.get(finish_reason, 0) + 1
    return {
        "provider": "mimo",
        "backend_path": "raw_sdk",
        "mode": STREAMING_MODE,
        "prompt_variant": "l4_strong_format",
        "sample_count": total,
        "completed_count": sum(bool(item.get("completed")) for item in records),
        "timeout_count": sum(bool(item.get("timeout")) for item in records),
        "application_wall_clock_timeout_count": sum(
            str(item.get("error_type")) == "ApplicationWallClockTimeout" for item in records
        ),
        "provider_error_count": sum(bool(item.get("provider_error")) for item in records),
        "rate_limit_count": sum(bool(item.get("rate_limit_observed")) for item in records),
        "official_score": round(sum(float(item.get("official_score", 0.0)) for item in records) / total, 12)
        if total
        else 0.0,
        "relaxed_extractable_score": round(
            sum(1.0 if item.get("relaxed_extractable_correct") else 0.0 for item in records) / total,
            12,
        )
        if total
        else 0.0,
        "format_loss_count": sum(bool(item.get("format_loss")) for item in records),
        "reasoning_error_count": sum(bool(item.get("reasoning_error")) for item in records),
        "empty_or_invalid_count": sum(bool(item.get("empty_or_invalid")) for item in records),
        "avg_time_to_first_token_seconds": round(sum(ttft_values) / len(ttft_values), 6) if ttft_values else None,
        "max_time_to_first_token_seconds": round(max(ttft_values), 6) if ttft_values else None,
        "avg_time_to_complete_seconds": round(sum(complete_values) / len(complete_values), 6)
        if complete_values
        else 0.0,
        "max_time_to_complete_seconds": round(max(complete_values), 6) if complete_values else 0.0,
        "avg_latency_seconds": round(sum(latency_values) / len(latency_values), 6) if latency_values else 0.0,
        "max_latency_seconds": round(max(latency_values), 6) if latency_values else 0.0,
        "finish_reason_distribution": finish_reason_distribution,
        "first_token_observed_count": sum(bool(item.get("first_token_observed")) for item in records),
        "content_nonempty_count": sum(bool(item.get("content_nonempty")) for item in records),
        **DIAGNOSTIC_FLAGS,
    }


def summarize_health_checks(health_checks: list[dict[str, Any]]) -> dict[str, Any]:
    latency_values = [float(item.get("latency_seconds", 0.0)) for item in health_checks if item.get("latency_seconds")]
    return {
        "check_count": len(health_checks),
        "ok_count": sum(bool(item.get("content_exact_ok")) for item in health_checks),
        "error_count": sum(1 for item in health_checks if item.get("error_type")),
        "avg_latency_seconds": round(sum(latency_values) / len(latency_values), 6) if latency_values else 0.0,
        "phases_seen": sorted({str(item.get("phase")) for item in health_checks}),
        **DIAGNOSTIC_FLAGS,
    }


def build_sample_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda item: str(item["sample_id"])):
        summaries.append(
            {
                "sample_id": record["sample_id"],
                "completed": bool(record.get("completed")),
                "timeout": bool(record.get("timeout")),
                "application_wall_clock_timeout": str(record.get("error_type")) == "ApplicationWallClockTimeout",
                "first_token_observed": bool(record.get("first_token_observed")),
                "time_to_first_token_seconds": record.get("time_to_first_token_seconds"),
                "time_to_complete_seconds": record.get("time_to_complete_seconds"),
                "official_score": record.get("official_score"),
                "relaxed_extractable_correct": bool(record.get("relaxed_extractable_correct")),
                "format_loss": bool(record.get("format_loss")),
                "reasoning_error": bool(record.get("reasoning_error")),
                "empty_or_invalid": bool(record.get("empty_or_invalid")),
                "partial_content_nonempty": bool(record.get("partial_content_nonempty")),
                "finish_reason": record.get("finish_reason"),
                "error_type": record.get("error_type"),
            }
        )
    return summaries


def build_failure_cases(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for record in records:
        if str(record.get("status")) == "ok" and not (
            record.get("format_loss")
            or record.get("reasoning_error")
            or record.get("empty_or_invalid")
            or record.get("reasoning_only_output")
        ):
            continue
        failures.append(
            {
                "provider": record["provider"],
                "model": record["model"],
                "backend_path": record["backend_path"],
                "mode": record["mode"],
                "sample_id": record["sample_id"],
                "prompt_variant": record["prompt_variant"],
                "first_token_observed": record.get("first_token_observed"),
                "time_to_first_token_seconds": record.get("time_to_first_token_seconds"),
                "time_to_complete_seconds": record.get("time_to_complete_seconds"),
                "partial_content_nonempty": record.get("partial_content_nonempty"),
                "content_nonempty": record.get("content_nonempty"),
                "finish_reason": record.get("finish_reason"),
                "official_score": record.get("official_score"),
                "relaxed_extractable_correct": record.get("relaxed_extractable_correct"),
                "format_loss": record.get("format_loss"),
                "reasoning_error": record.get("reasoning_error"),
                "empty_or_invalid": record.get("empty_or_invalid"),
                "reasoning_only_output": record.get("reasoning_only_output"),
                "timeout": record.get("timeout"),
                "timeout_enforced_by": record.get("timeout_enforced_by"),
                "error_type": record.get("error_type"),
                "error_code": record.get("error_code"),
                "http_status": record.get("http_status"),
                "error_message_sanitized": record.get("error_message_sanitized"),
                "raw_response_preview": record.get("raw_response_preview"),
            }
        )
    return failures


def build_run_summary(*, records: list[dict[str, Any]], health_checks: list[dict[str, Any]], execute: bool) -> dict[str, Any]:
    return {
        "generated_at": create_timestamp(),
        "mode": "execute" if execute else "dry_run",
        "record_count": len(records),
        "health_check_count": len(health_checks),
        "aggregate_summary": summarize_records(records) if execute else {},
        "sample_summaries": build_sample_summaries(records) if execute else [],
        "health_check_summary": summarize_health_checks(health_checks) if execute else {},
        "failure_cases_count": len(build_failure_cases(records)) if execute else 0,
        "failure_cases": build_failure_cases(records) if execute else [],
        **DIAGNOSTIC_FLAGS,
    }


def build_input_snapshot(
    *,
    provider_config: Any,
    backend_path: str,
    prompt_variant: PromptVariantSpec,
    sample_entries: list[dict[str, Any]],
    dataset_meta: dict[str, Any],
    application_wall_clock_timeout_seconds: float,
    sdk_timeout_seconds: float,
    sleep_between_requests: float,
    max_retries: int,
    run_dir: Path,
    execute: bool,
) -> dict[str, Any]:
    return {
        "metadata": {
            "generated_at": create_timestamp(),
            "mode": "execute" if execute else "dry_run",
            "run_dir": project_relative(run_dir),
            "model_called": bool(execute),
            "api_called": bool(execute),
            "new_experiment_executed": bool(execute),
            **DIAGNOSTIC_FLAGS,
        },
        "requested_execution": {
            "provider": provider_config.provider,
            "backend_path": backend_path,
            "mode": STREAMING_MODE,
            "prompt_variant": prompt_variant.name,
            "sample_ids": [entry["sample_id"] for entry in sample_entries],
            "application_wall_clock_timeout_seconds": application_wall_clock_timeout_seconds,
            "sdk_timeout_seconds": sdk_timeout_seconds,
            "sleep_between_requests": sleep_between_requests,
            "max_retries": max_retries,
            "concurrency": 1,
        },
        "provider_config": {
            "provider": provider_config.provider,
            "model": provider_config.model,
            "api_key_env": provider_config.api_key_env,
            "api_base_present": provider_config.api_base_present,
            "model_present": provider_config.model_present,
            "missing_config_reasons": provider_config.missing_config_reasons(),
        },
        "dataset_meta": dataset_meta,
    }


def render_report(
    payload: dict[str, Any],
    records: list[dict[str, Any]],
    health_checks: list[dict[str, Any]],
    run_summary: dict[str, Any],
) -> str:
    metadata = payload["metadata"]
    requested_execution = payload["requested_execution"]
    provider_config = payload["provider_config"]
    dataset_meta = payload["dataset_meta"]
    lines: list[str] = [
        "# Stage 4B MiMo streaming extended-timeout diagnostic 结果",
        "",
        "## 定位",
        "",
        "- 本报告只记录 MiMo 的 streaming extended-timeout diagnostic。",
        "- 它不是 strict non-streaming path 结果。",
        "- 它不是 strict 60s comparison。",
        "- 它不是 GEPA 结果。",
        "- 它不是 official_budget 结果。",
        "- 它不是 MiMo vs GLM 排名。",
        "- 所有真实调用都只允许解释为 diagnostic，不允许写成 performance claim。",
        "",
        "## 边界标识",
        "",
        f"- `model_called = {str(metadata['model_called']).lower()}`",
        f"- `api_called = {str(metadata['api_called']).lower()}`",
        f"- `new_experiment_executed = {str(metadata['new_experiment_executed']).lower()}`",
        "- `streaming_path_only = true`",
        "- `extended_timeout_diagnostic = true`",
        "- `not_strict_non_streaming_path = true`",
        "- `not_strict_60s_comparison = true`",
        "- `not_gepa_result = true`",
        "- `not_official_budget = true`",
        "- `not_model_ranking = true`",
        "- `not_performance_claim = true`",
        "- `diagnostic_only = true`",
        "",
        "## 请求计划",
        "",
        f"- provider：`{requested_execution['provider']}`",
        f"- backend path：`{requested_execution['backend_path']}`",
        f"- mode：`{requested_execution['mode']}`",
        f"- prompt variant：`{requested_execution['prompt_variant']}`",
        f"- sample ids：`{', '.join(requested_execution['sample_ids'])}`",
        f"- application_wall_clock_timeout_seconds：`{requested_execution['application_wall_clock_timeout_seconds']}`",
        f"- sdk_timeout_seconds：`{requested_execution['sdk_timeout_seconds']}`",
        f"- sleep_between_requests：`{requested_execution['sleep_between_requests']}` 秒",
        f"- max_retries：`{requested_execution['max_retries']}`",
        f"- concurrency：`{requested_execution['concurrency']}`",
        f"- split：`{dataset_meta['split_label']}`",
        "",
        "## 配置状态",
        "",
        f"- model：`{provider_config['model'] or '<missing>'}`",
        f"- api_key_env：`{provider_config['api_key_env']}`",
        f"- api_base_present：`{str(provider_config['api_base_present']).lower()}`",
        f"- model_present：`{str(provider_config['model_present']).lower()}`",
        f"- missing_config_reasons：`{', '.join(provider_config['missing_config_reasons']) if provider_config['missing_config_reasons'] else 'none'}`",
        "",
        "## 执行状态",
        "",
    ]

    if metadata["mode"] == "dry_run":
        lines.extend(
            [
                "- 当前状态：dry-run，未调用模型，未调用 API，未运行新实验。",
                "- 本次报告只验证脚手架、streaming-only 边界、wall-clock guard schema 和结果报告骨架。",
                "- health check：未执行；脚本已预留 pre / post streaming health check 路径。",
                "",
                "## 计划覆盖",
                "",
                f"- planned_request_count：`{len(records)}`",
                f"- planned_health_check_count：`{len(health_checks)}`",
                "- 真实执行时必须先比较 pre/post health check，再解释 AIME 失败归因。",
                "",
                "## 待执行判读框架",
                "",
                "1. 如果 health check 失败，而 AIME 也失败，应优先归因为 provider / endpoint / key / 网络问题。",
                "2. 如果 health check 正常，但 AIME streaming 超时，应继续区分首 token 前超时、生成中途超时、partial content、finish_reason、reasoning_only_output。",
                "3. 如果 5/5 completed 且 format_loss=0，可以建议扩到 streaming extended-timeout 30-sample diagnostic。",
                "4. 即使全部完成，也不能写成 strict non-streaming path 已成功。",
            ]
        )
        return "\n".join(lines) + "\n"

    aggregate = run_summary["aggregate_summary"]
    health_summary = run_summary["health_check_summary"]
    lines.extend(
        [
            "- 当前状态：execute 已执行。",
            "- health check 已在 streaming 批次前后执行。",
            "",
            "## health check 汇总",
            "",
            f"- check_count：`{health_summary['check_count']}`",
            f"- ok_count：`{health_summary['ok_count']}`",
            f"- error_count：`{health_summary['error_count']}`",
            f"- avg_latency_seconds：`{health_summary['avg_latency_seconds']}`",
            "",
            "## 汇总指标",
            "",
            f"- completed_count：`{aggregate['completed_count']}`",
            f"- timeout_count：`{aggregate['timeout_count']}`",
            f"- application_wall_clock_timeout_count：`{aggregate['application_wall_clock_timeout_count']}`",
            f"- provider_error_count：`{aggregate['provider_error_count']}`",
            f"- rate_limit_count：`{aggregate['rate_limit_count']}`",
            f"- official_score：`{aggregate['official_score']}`",
            f"- relaxed_extractable_score：`{aggregate['relaxed_extractable_score']}`",
            f"- format_loss_count：`{aggregate['format_loss_count']}`",
            f"- reasoning_error_count：`{aggregate['reasoning_error_count']}`",
            f"- empty_or_invalid_count：`{aggregate['empty_or_invalid_count']}`",
            f"- first_token_observed_count：`{aggregate['first_token_observed_count']}`",
            f"- content_nonempty_count：`{aggregate['content_nonempty_count']}`",
            f"- avg_time_to_first_token_seconds：`{aggregate['avg_time_to_first_token_seconds']}`",
            f"- max_time_to_first_token_seconds：`{aggregate['max_time_to_first_token_seconds']}`",
            f"- avg_time_to_complete_seconds：`{aggregate['avg_time_to_complete_seconds']}`",
            f"- max_time_to_complete_seconds：`{aggregate['max_time_to_complete_seconds']}`",
            f"- finish_reason_distribution：`{json.dumps(aggregate['finish_reason_distribution'], ensure_ascii=False)}`",
            "",
            "## 单样本摘要",
            "",
            "| sample_id | completed | timeout | app_wc_timeout | first_token | ttft | complete_time | official | relaxed | format_loss | reasoning_error | empty_or_invalid | finish_reason | error_type |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )

    for summary in run_summary["sample_summaries"]:
        lines.append(
            f"| `{summary['sample_id']}` | {int(summary['completed'])} | {int(summary['timeout'])} | "
            f"{int(summary['application_wall_clock_timeout'])} | {int(summary['first_token_observed'])} | "
            f"{summary['time_to_first_token_seconds']} | {summary['time_to_complete_seconds']} | "
            f"{summary['official_score']} | {int(summary['relaxed_extractable_correct'])} | "
            f"{int(summary['format_loss'])} | {int(summary['reasoning_error'])} | "
            f"{int(summary['empty_or_invalid'])} | `{summary['finish_reason']}` | "
            f"`{summary['error_type']}` |"
        )

    if run_summary["failure_cases"]:
        lines.extend(
            [
                "",
                "## failure cases",
                "",
                "| sample_id | timeout | enforced_by | first_token | partial_content | finish_reason | diagnosis_hint | preview |",
                "|---|---|---|---|---|---|---|---|",
            ]
        )
        for record in run_summary["failure_cases"][:20]:
            diagnosis_hint = "timeout"
            if record["format_loss"]:
                diagnosis_hint = "format_loss"
            elif record["reasoning_error"]:
                diagnosis_hint = "reasoning_error"
            elif record["reasoning_only_output"]:
                diagnosis_hint = "reasoning_only_output"
            elif record["empty_or_invalid"]:
                diagnosis_hint = "empty_or_invalid"
            lines.append(
                f"| `{record['sample_id']}` | `{str(record['timeout']).lower()}` | "
                f"`{record['timeout_enforced_by']}` | `{str(record['first_token_observed']).lower()}` | "
                f"`{str(record['partial_content_nonempty']).lower()}` | `{record['finish_reason']}` | "
                f"`{diagnosis_hint}` | {record['raw_response_preview'] or '<empty>'} |"
            )

    lines.extend(
        [
            "",
            "## 结论边界",
            "",
            "- 可以写：MiMo 在 streaming extended-timeout 条件下是否能完成 fixed-prompt diagnostic。",
            "- 可以写：L4 是否改善协议遵循、是否仍有 format_loss、reasoning_error、empty_or_invalid。",
            "- 可以写：是否触发 application wall-clock guard，以及 SDK timeout 与 wall-clock 行为是否一致。",
            "- 不可以写：MiMo strict path passed。",
            "- 不可以写：MiMo 可以替代 DeepSeek。",
            "- 不可以写：MiMo 数学能力更强。",
            "- 不可以写：MiMo 已经适合 GEPA。",
            "- 不可以写：MiMo 与 GLM 的性能比较。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    enforce_bounds(args)
    provider_config = build_provider_config(args)
    prompt_variant = load_prompt_variant(args.prompt_variant)
    sample_entries, dataset_meta = build_selected_samples(list(args.sample_ids))
    output_root = PROJECT_ROOT / args.output_dir
    report_path = PROJECT_ROOT / args.report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if args.run_dir:
        run_dir = (PROJECT_ROOT / args.run_dir).resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
    else:
        run_dir = create_run_dir(output_root)

    payload = build_input_snapshot(
        provider_config=provider_config,
        backend_path=args.backend_path,
        prompt_variant=prompt_variant,
        sample_entries=sample_entries,
        dataset_meta=dataset_meta,
        application_wall_clock_timeout_seconds=float(args.application_wall_clock_timeout),
        sdk_timeout_seconds=float(args.sdk_timeout),
        sleep_between_requests=args.sleep_between_requests,
        max_retries=args.max_retries,
        run_dir=run_dir,
        execute=args.execute,
    )

    if args.execute:
        execution_result = execute_plan(
            provider_config=provider_config,
            backend_path=args.backend_path,
            prompt_variant=prompt_variant,
            sample_entries=sample_entries,
            application_wall_clock_timeout_seconds=float(args.application_wall_clock_timeout),
            sdk_timeout_seconds=float(args.sdk_timeout),
            sleep_between_requests=args.sleep_between_requests,
            max_retries=args.max_retries,
            run_dir=run_dir,
        )
        records = execution_result["records"]
        health_checks = execution_result["health_checks"]
    else:
        records = build_dry_run_records(
            provider_config=provider_config,
            backend_path=args.backend_path,
            prompt_variant=prompt_variant,
            sample_entries=sample_entries,
            application_wall_clock_timeout_seconds=float(args.application_wall_clock_timeout),
            sdk_timeout_seconds=float(args.sdk_timeout),
            sleep_between_requests=args.sleep_between_requests,
            max_retries=args.max_retries,
        )
        health_checks = build_dry_run_health_checks(
            provider_config=provider_config,
            backend_path=args.backend_path,
            sdk_timeout_seconds=float(args.sdk_timeout),
            application_wall_clock_timeout_seconds=float(args.application_wall_clock_timeout),
        )

    per_example_path = run_dir / "per_example_eval.jsonl"
    health_check_path = run_dir / "health_checks.jsonl"
    failure_cases = build_failure_cases(records) if args.execute else []
    run_summary = build_run_summary(records=records, health_checks=health_checks, execute=args.execute)
    results_payload = {
        "metadata": payload["metadata"],
        "execution": payload["requested_execution"],
        "provider_config": payload["provider_config"],
        "dataset_meta": payload["dataset_meta"],
        "aggregate_summary": run_summary["aggregate_summary"],
        "sample_summaries": run_summary["sample_summaries"],
        "health_check_summary": run_summary["health_check_summary"],
        **DIAGNOSTIC_FLAGS,
    }

    write_json(run_dir / "input_snapshot.json", payload)
    BASE.write_jsonl(per_example_path, records)
    BASE.write_jsonl(health_check_path, health_checks)
    write_json(run_dir / "streaming_extended_timeout_results.json", results_payload)
    write_json(run_dir / "run_summary.json", run_summary)
    write_json(run_dir / "failure_cases.json", failure_cases)
    write_text(report_path, render_report(payload, records, health_checks, run_summary))


if __name__ == "__main__":
    main()
