from __future__ import annotations

import argparse
import concurrent.futures
import importlib
import importlib.util
import inspect
import json
import multiprocessing as mp
import os
import queue
import re
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator

from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.deepseek_utils import build_litellm_model_name, temporary_openai_compatible_env
from src.gepa_official_runner import load_official_aime_dataset
from src.logging_utils import create_run_dir, create_timestamp, write_json, write_text


DEFAULT_OUTPUT_DIR = "outputs/stage4c_glm_streaming_gepa_sanity"
DEFAULT_REPORT_PATH = "reports/stage4c_glm_streaming_gepa_sanity_result.md"
DEFAULT_SLEEP_SECONDS = 120.0
DEFAULT_MAX_METRIC_CALLS = 1
DEFAULT_DIAGNOSTIC_VAL_LIMIT = 3
DEFAULT_SEED_PROMPT = "strong_format"
DEFAULT_THINKING_TYPES: tuple[str, ...] = ("default", "disabled")

DIAGNOSTIC_FLAGS: dict[str, bool] = {
    "stage4c_glm_streaming_gepa_sanity": True,
    "diagnostic_only": True,
    "not_official_budget": True,
    "not_performance_claim": True,
    "not_model_ranking": True,
    "not_strict_default_path": True,
    "streaming_path_only": True,
    "glm_backend": True,
    "paired_thinking_diagnostic": True,
}

HEALTH_CHECK_PROMPT = "Return exactly: OK"


class Stage4CGLMStreamingGEPASanityError(RuntimeError):
    """Stage 4C GLM streaming GEPA sanity 的配置或执行错误。"""


class FirstTokenTimeout(RuntimeError):
    """首 token 等待超时。"""


class PostFirstTokenTimeout(RuntimeError):
    """首 token 后生成超时。"""


class ApplicationWallClockTimeout(RuntimeError):
    """单请求整体墙钟超时。"""


class EmergencyGuardTimeout(RuntimeError):
    """整个 arm 超出紧急保护时限。"""


@dataclass(frozen=True)
class ThinkingArmSpec:
    thinking_type: str
    sdk_timeout_seconds: int
    first_token_timeout_seconds: int
    post_first_token_timeout_seconds: int
    application_wall_clock_timeout_seconds: int
    emergency_guard_timeout_seconds: int


def _load_stage4b_base_module() -> ModuleType:
    script_path = PROJECT_ROOT / "scripts" / "stage4b_eval_fixed_prompt_aime_mimopro_glm47.py"
    spec = importlib.util.spec_from_file_location("stage4c_glm_gepa_base_script", script_path)
    if spec is None or spec.loader is None:
        raise Stage4CGLMStreamingGEPASanityError(f"无法加载 Stage 4B base script：{script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_stage4b_base_module()

SEED_PROMPTS: dict[str, dict[str, str]] = {
    "strong_format": {"system_prompt": BASE.PROMPTS["strong_format_seed_prompt"]},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage 4C GLM streaming GEPA micro-sanity。默认 dry-run，不调用模型或 GEPA。"
    )
    parser.add_argument("--glm-api-base", default=os.getenv("GLM_API_BASE", ""), help="GLM API base。")
    parser.add_argument("--glm-api-key-env", default="GLM_API_KEY", help="GLM API key 的环境变量名。")
    parser.add_argument("--glm-model", default=os.getenv("GLM_MODEL", ""), help="GLM model id。")
    parser.add_argument(
        "--paired-thinking-diagnostic",
        action="store_true",
        help="执行 paired thinking diagnostic；当前 Stage 4C 要求显式开启。",
    )
    parser.add_argument(
        "--thinking-types",
        nargs="+",
        choices=("default", "disabled", "enabled"),
        default=list(DEFAULT_THINKING_TYPES),
        help="thinking arm 顺序；默认 default disabled。",
    )
    parser.add_argument("--max-metric-calls", type=int, default=DEFAULT_MAX_METRIC_CALLS, help="GEPA 最大 metric calls。")
    parser.add_argument("--diagnostic-val-limit", type=int, default=DEFAULT_DIAGNOSTIC_VAL_LIMIT, help="GEPA micro-sanity 使用的 val subset 大小。")
    parser.add_argument("--seed-prompt", choices=tuple(SEED_PROMPTS), default=DEFAULT_SEED_PROMPT, help="Stage 4C 当前固定使用 strong_format。")
    parser.add_argument("--sleep-between-requests", type=float, default=DEFAULT_SLEEP_SECONDS, help="相邻底层请求之间的等待秒数。")
    parser.add_argument("--max-retries", type=int, default=0, help="底层请求重试次数；当前必须为 0。")
    parser.add_argument("--streaming", action="store_true", help="显式标记使用 streaming；当前 Stage 4C 必须开启。")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="outputs 根目录。")
    parser.add_argument("--report-path", default=DEFAULT_REPORT_PATH, help="结果报告路径。")
    parser.add_argument("--run-dir", default=None, help="复用现有 run_dir；默认新建。")
    parser.add_argument("--execute", action="store_true", help="显式执行真实 GEPA micro-sanity。")
    return parser.parse_args()


def build_glm_provider_config(args: argparse.Namespace) -> Any:
    namespace = SimpleNamespace(
        providers=("glm",),
        mimo_api_base="",
        mimo_api_key_env="MIMO_API_KEY",
        mimo_model="",
        mimo_provider_string=None,
        glm_api_base=args.glm_api_base,
        glm_api_key_env=args.glm_api_key_env,
        glm_model=args.glm_model,
        glm_provider_string=None,
    )
    configs = BASE.build_provider_configs(namespace)
    if len(configs) != 1 or configs[0].provider != "glm":
        raise Stage4CGLMStreamingGEPASanityError("GLM provider 配置构建失败。")
    return configs[0]


def build_arm_specs(thinking_types: list[str]) -> list[ThinkingArmSpec]:
    specs: list[ThinkingArmSpec] = []
    for thinking_type in list(dict.fromkeys(thinking_types)):
        if thinking_type == "default":
            specs.append(
                ThinkingArmSpec(
                    thinking_type="default",
                    sdk_timeout_seconds=1800,
                    first_token_timeout_seconds=1800,
                    post_first_token_timeout_seconds=900,
                    application_wall_clock_timeout_seconds=2700,
                    emergency_guard_timeout_seconds=3600,
                )
            )
        elif thinking_type == "disabled":
            specs.append(
                ThinkingArmSpec(
                    thinking_type="disabled",
                    sdk_timeout_seconds=900,
                    first_token_timeout_seconds=300,
                    post_first_token_timeout_seconds=900,
                    application_wall_clock_timeout_seconds=1200,
                    emergency_guard_timeout_seconds=1800,
                )
            )
        elif thinking_type == "enabled":
            specs.append(
                ThinkingArmSpec(
                    thinking_type="enabled",
                    sdk_timeout_seconds=1800,
                    first_token_timeout_seconds=1800,
                    post_first_token_timeout_seconds=900,
                    application_wall_clock_timeout_seconds=2700,
                    emergency_guard_timeout_seconds=3600,
                )
            )
        else:
            raise Stage4CGLMStreamingGEPASanityError(f"未知 thinking_type：{thinking_type}")
    return specs


def enforce_bounds(args: argparse.Namespace, arm_specs: list[ThinkingArmSpec]) -> None:
    if not args.paired_thinking_diagnostic:
        raise Stage4CGLMStreamingGEPASanityError("Stage 4C 必须显式传入 --paired-thinking-diagnostic。")
    if not args.streaming:
        raise Stage4CGLMStreamingGEPASanityError("Stage 4C 必须显式传入 --streaming。")
    if args.max_metric_calls != 1:
        raise Stage4CGLMStreamingGEPASanityError("Stage 4C 当前固定要求 --max-metric-calls 1。")
    if args.diagnostic_val_limit <= 0:
        raise Stage4CGLMStreamingGEPASanityError("--diagnostic-val-limit 必须大于 0。")
    if args.seed_prompt != "strong_format":
        raise Stage4CGLMStreamingGEPASanityError("Stage 4C 当前固定要求 --seed-prompt strong_format。")
    if args.max_retries != 0:
        raise Stage4CGLMStreamingGEPASanityError("Stage 4C 当前固定要求 --max-retries 0。")
    if args.sleep_between_requests < 0:
        raise Stage4CGLMStreamingGEPASanityError("--sleep-between-requests 不能小于 0。")
    if not arm_specs:
        raise Stage4CGLMStreamingGEPASanityError("至少需要一个 thinking arm。")


def build_dataset_payload(limit: int) -> dict[str, Any]:
    trainset, valset, testset, dataset_source, adaptation_notes = load_official_aime_dataset()
    limited_valset = list(valset)[:limit]
    return {
        "trainset": list(trainset),
        "valset": limited_valset,
        "testset_available": testset is not None,
        "dataset_source": sanitize_path_text(dataset_source),
        "adaptation_notes": [sanitize_path_text(note) for note in adaptation_notes],
        "trainset_size": len(trainset),
        "valset_size_full": len(valset),
        "diagnostic_val_limit": limit,
        "valset_size_used": len(limited_valset),
    }


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def build_extra_body(thinking_type: str) -> dict[str, Any] | None:
    normalized = str(thinking_type or "").strip().lower()
    if normalized == "default":
        return None
    if normalized in {"enabled", "disabled"}:
        return {"thinking": {"type": normalized}}
    return None


def sanitize_path_text(text: str | None) -> str:
    value = str(text or "")
    project_root_text = str(PROJECT_ROOT.resolve())
    if project_root_text:
        value = value.replace(project_root_text, "<project_root>")
    value = re.sub(r"[A-Za-z]:[\\/][^`'\"\s]+", "<local_path>", value)
    value = re.sub(r"/[^`'\"\s]*/site-packages/[^`'\"\s]+", "<local_path>", value)
    return value


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
        content = value.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "").lower()
                if item_type.startswith("reason"):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
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


def build_request_response(content: str, finish_reason: str | None, http_status: int | None) -> Any:
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    response = SimpleNamespace(choices=[choice])
    if http_status is not None:
        response._hidden_params = {"status_code": http_status}
    return response


def build_request_record(
    *,
    provider_config: Any,
    arm_spec: ThinkingArmSpec,
    request_role: str,
    request_index: int,
    arm_dir: Path,
) -> dict[str, Any]:
    return {
        "provider": provider_config.provider,
        "model": provider_config.model,
        "api_base_present": provider_config.api_base_present,
        "backend_family": provider_config.backend_family,
        "backend_path": "raw_sdk",
        "mode": "streaming",
        "thinking_type": arm_spec.thinking_type,
        "request_role": request_role,
        "request_index": request_index,
        "sdk_timeout_seconds": arm_spec.sdk_timeout_seconds,
        "first_token_timeout_seconds": arm_spec.first_token_timeout_seconds,
        "post_first_token_timeout_seconds": arm_spec.post_first_token_timeout_seconds,
        "application_wall_clock_timeout_seconds": arm_spec.application_wall_clock_timeout_seconds,
        "arm_dir": BASE.project_relative(arm_dir),
        "status": "pending",
        "timeout": False,
        "error_type": None,
        "error_message_sanitized": None,
        "error_body_sanitized": None,
        "http_status": None,
        "finish_reason": None,
        "content_nonempty": False,
        "reasoning_content_present": False,
        "time_to_first_token_seconds": None,
        "time_to_complete_seconds": None,
        "raw_response_preview": "",
        "full_response_path": None,
        "timeout_source": None,
        **DIAGNOSTIC_FLAGS,
    }


def save_request_payload(
    *,
    arm_dir: Path,
    record: dict[str, Any],
    payload: dict[str, Any],
) -> str:
    raw_dir = arm_dir / "raw_responses"
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_name = "__".join(
        [
            BASE.slugify(record["thinking_type"]),
            BASE.slugify(record["request_role"]),
            BASE.slugify(str(record["request_index"])),
        ]
    )
    raw_path = raw_dir / f"{file_name}.json"
    write_json(raw_path, payload)
    return BASE.project_relative(raw_path)


def execute_streaming_request(
    *,
    provider_config: Any,
    arm_spec: ThinkingArmSpec,
    messages: list[dict[str, str]],
    request_role: str,
    request_index: int,
    arm_dir: Path,
) -> tuple[Any, dict[str, Any]]:
    record = build_request_record(
        provider_config=provider_config,
        arm_spec=arm_spec,
        request_role=request_role,
        request_index=request_index,
        arm_dir=arm_dir,
    )
    missing = provider_config.missing_config_reasons()
    if missing:
        record.update(
            {
                "status": "config_missing",
                "timeout": False,
                "error_type": "ConfigMissing",
                "error_message_sanitized": "; ".join(missing),
            }
        )
        return build_request_response("", None, None), record

    secrets = [provider_config.api_key]
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    chunk_payloads: list[dict[str, Any]] = []
    finish_reason: str | None = None
    first_token_time: float | None = None
    started_at = time.monotonic()
    stream: Any = None
    worker: threading.Thread | None = None
    event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
    try:
        client = OpenAI(
            api_key=provider_config.api_key,
            base_url=provider_config.api_base,
            timeout=float(arm_spec.sdk_timeout_seconds),
            max_retries=0,
        )
        stream = client.chat.completions.create(
            model=provider_config.model,
            messages=messages,
            temperature=0,
            timeout=float(arm_spec.sdk_timeout_seconds),
            stream=True,
            stream_options={"include_usage": True},
            extra_body=build_extra_body(arm_spec.thinking_type),
        )
        record["http_status"] = _extract_stream_http_status(stream)
        worker = threading.Thread(target=_stream_worker, args=(stream, event_queue), daemon=True)
        worker.start()

        while True:
            elapsed = time.monotonic() - started_at
            wall_remaining = float(arm_spec.application_wall_clock_timeout_seconds) - elapsed
            if wall_remaining <= 0:
                raise ApplicationWallClockTimeout("Application wall-clock timeout exceeded.")
            if first_token_time is None:
                first_remaining = float(arm_spec.first_token_timeout_seconds) - elapsed
                if first_remaining <= 0:
                    raise FirstTokenTimeout("First token timeout exceeded.")
                wait_timeout = min(0.2, wall_remaining, first_remaining)
            else:
                post_elapsed = time.monotonic() - first_token_time
                post_remaining = float(arm_spec.post_first_token_timeout_seconds) - post_elapsed
                if post_remaining <= 0:
                    raise PostFirstTokenTimeout("Post first-token timeout exceeded.")
                wait_timeout = min(0.2, wall_remaining, post_remaining)
            try:
                event_name, payload = event_queue.get(timeout=wait_timeout)
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
        record.update(
            {
                "status": "ok",
                "content_nonempty": bool(content.strip()),
                "reasoning_content_present": bool(reasoning_text),
                "finish_reason": finish_reason,
                "time_to_first_token_seconds": (
                    round(first_token_time - started_at, 6) if first_token_time is not None else None
                ),
                "time_to_complete_seconds": round(time.monotonic() - started_at, 6),
                "raw_response_preview": BASE.sanitize_text(content, secrets=secrets, limit=240),
            }
        )
        record["full_response_path"] = save_request_payload(
            arm_dir=arm_dir,
            record=record,
            payload={
                "messages": messages,
                "content": content,
                "reasoning_text": reasoning_text,
                "finish_reason": finish_reason,
                "http_status": record["http_status"],
                "raw_payload": {"chunks": chunk_payloads},
            },
        )
        return build_request_response(content, finish_reason, record["http_status"]), record
    except Exception as exc:  # pragma: no cover - 真实 provider 路径
        attempted, succeeded = _attempt_close_stream(stream)
        if worker is not None and worker.is_alive():
            worker.join(timeout=1.0)
        content = "".join(content_parts)
        reasoning_text = "".join(reasoning_parts)
        time_to_first = round(first_token_time - started_at, 6) if first_token_time is not None else None
        time_to_complete = round(time.monotonic() - started_at, 6)
        record.update(
            {
                "content_nonempty": bool(content.strip()),
                "reasoning_content_present": bool(reasoning_text),
                "finish_reason": finish_reason,
                "time_to_first_token_seconds": time_to_first,
                "time_to_complete_seconds": time_to_complete,
                "raw_response_preview": BASE.sanitize_text(content, secrets=secrets, limit=240),
                "stream_close_attempted": attempted,
                "stream_close_succeeded": succeeded,
            }
        )
        if isinstance(exc, FirstTokenTimeout):
            record.update(
                {
                    "status": "timeout",
                    "timeout": True,
                    "error_type": "FirstTokenTimeout",
                    "error_message_sanitized": str(exc),
                    "timeout_source": "first_token_guard",
                }
            )
        elif isinstance(exc, PostFirstTokenTimeout):
            record.update(
                {
                    "status": "timeout",
                    "timeout": True,
                    "error_type": "PostFirstTokenTimeout",
                    "error_message_sanitized": str(exc),
                    "timeout_source": "post_first_token_guard",
                }
            )
        elif isinstance(exc, ApplicationWallClockTimeout):
            record.update(
                {
                    "status": "timeout",
                    "timeout": True,
                    "error_type": "ApplicationWallClockTimeout",
                    "error_message_sanitized": str(exc),
                    "timeout_source": "application_wall_clock",
                }
            )
        else:
            record["http_status"] = record["http_status"] or BASE.extract_http_status_from_error(exc)
            error_message, error_body = BASE.extract_error_message(exc, secrets=secrets)
            record.update(
                {
                    "status": "timeout" if BASE.is_timeout_error(exc) else "error",
                    "timeout": BASE.is_timeout_error(exc),
                    "error_type": type(exc).__name__,
                    "error_message_sanitized": error_message,
                    "error_body_sanitized": error_body,
                    "timeout_source": "sdk_or_provider" if BASE.is_timeout_error(exc) else None,
                }
            )
        record["full_response_path"] = save_request_payload(
            arm_dir=arm_dir,
            record=record,
            payload={
                "messages": messages,
                "partial_content": content,
                "reasoning_text": reasoning_text,
                "finish_reason": finish_reason,
                "http_status": record["http_status"],
                "error_type": record["error_type"],
                "error_message_sanitized": record["error_message_sanitized"],
                "error_body_sanitized": record["error_body_sanitized"],
                "raw_payload": {"chunks": chunk_payloads},
            },
        )
        return build_request_response(content, finish_reason, record["http_status"]), record


def execute_health_check(
    *,
    provider_config: Any,
    arm_spec: ThinkingArmSpec,
    phase: str,
    arm_dir: Path,
    request_index: int,
) -> dict[str, Any]:
    response, record = execute_streaming_request(
        provider_config=provider_config,
        arm_spec=arm_spec,
        messages=[{"role": "user", "content": HEALTH_CHECK_PROMPT}],
        request_role=f"health_{phase}",
        request_index=request_index,
        arm_dir=arm_dir,
    )
    content = BASE.extract_message_content(response.choices[0].message)
    record["content_exact_ok"] = content.strip() == "OK"
    if record["status"] == "ok" and not record["content_exact_ok"]:
        record["status"] = "content_mismatch"
        record["error_type"] = "HealthCheckContentMismatch"
        record["error_message_sanitized"] = "Health check did not return exactly OK."
    return record


class StreamingLitellmBridge:
    def __init__(
        self,
        *,
        provider_config: Any,
        arm_spec: ThinkingArmSpec,
        arm_dir: Path,
        sleep_between_requests: float,
        max_retries: int,
    ) -> None:
        self.provider_config = provider_config
        self.arm_spec = arm_spec
        self.arm_dir = arm_dir
        self.sleep_between_requests = sleep_between_requests
        self.max_retries = max_retries
        self.records: list[dict[str, Any]] = []
        self._request_counter = 0

    def _sleep_if_needed(self) -> None:
        if self._request_counter > 0 and self.sleep_between_requests > 0:
            time.sleep(self.sleep_between_requests)

    def _run_messages(self, *, messages: list[dict[str, str]], request_role: str) -> Any:
        if self.max_retries != 0:
            raise Stage4CGLMStreamingGEPASanityError("Stage 4C 当前固定要求 max_retries=0。")
        self._sleep_if_needed()
        response, record = execute_streaming_request(
            provider_config=self.provider_config,
            arm_spec=self.arm_spec,
            messages=messages,
            request_role=request_role,
            request_index=self._request_counter + 1,
            arm_dir=self.arm_dir,
        )
        self.records.append(record)
        self._request_counter += 1
        if record.get("status") != "ok":
            error_type = record.get("error_type") or "StreamingRequestError"
            error_message = record.get("error_message_sanitized") or "streaming request failed"
            raise Stage4CGLMStreamingGEPASanityError(f"{error_type}: {error_message}")
        return response

    def completion(self, *, model: str, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        return self._run_messages(messages=messages, request_role="reflection_completion")

    def batch_completion(
        self,
        *,
        model: str,
        messages: list[list[dict[str, str]]],
        max_workers: int | None = None,
        **kwargs: Any,
    ) -> list[Any]:
        responses: list[Any] = []
        for index, message_list in enumerate(messages, start=1):
            responses.append(self._run_messages(messages=message_list, request_role=f"task_batch_{index}"))
        return responses


@contextmanager
def patch_litellm_for_streaming(bridge: StreamingLitellmBridge) -> Iterator[None]:
    litellm_module = importlib.import_module("litellm")
    original_completion = litellm_module.completion
    original_batch_completion = litellm_module.batch_completion
    litellm_module.completion = bridge.completion
    litellm_module.batch_completion = bridge.batch_completion
    try:
        yield
    finally:
        litellm_module.completion = original_completion
        litellm_module.batch_completion = original_batch_completion


def build_optimize_kwargs(
    *,
    provider_config: Any,
    dataset_payload: dict[str, Any],
    seed_prompt_name: str,
    max_metric_calls: int,
    arm_dir: Path,
) -> dict[str, Any]:
    return {
        "seed_candidate": SEED_PROMPTS[seed_prompt_name],
        "trainset": dataset_payload["trainset"],
        "valset": dataset_payload["valset"],
        "task_lm": build_litellm_model_name(provider_config.model),
        "reflection_lm": build_litellm_model_name(provider_config.model),
        "max_metric_calls": max_metric_calls,
        "seed": 42,
        "run_dir": str(arm_dir),
    }


def summarize_request_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "request_count": 0,
            "completed_count": 0,
            "timeout_count": 0,
            "first_token_timeout_count": 0,
            "post_first_token_timeout_count": 0,
            "application_wall_clock_timeout_count": 0,
            "avg_time_to_first_token_seconds": None,
            "max_time_to_first_token_seconds": None,
            "avg_time_to_complete_seconds": None,
            "max_time_to_complete_seconds": None,
            "finish_reason_distribution": {},
        }
    first_token_values = [
        float(item["time_to_first_token_seconds"])
        for item in records
        if item.get("time_to_first_token_seconds") is not None
    ]
    complete_values = [
        float(item["time_to_complete_seconds"])
        for item in records
        if item.get("time_to_complete_seconds") is not None
    ]
    distribution: dict[str, int] = {}
    for item in records:
        key = str(item.get("finish_reason") or "null")
        distribution[key] = distribution.get(key, 0) + 1
    return {
        "request_count": len(records),
        "completed_count": sum(str(item.get("status")) == "ok" for item in records),
        "timeout_count": sum(bool(item.get("timeout")) for item in records),
        "first_token_timeout_count": sum(str(item.get("error_type")) == "FirstTokenTimeout" for item in records),
        "post_first_token_timeout_count": sum(str(item.get("error_type")) == "PostFirstTokenTimeout" for item in records),
        "application_wall_clock_timeout_count": sum(
            str(item.get("error_type")) == "ApplicationWallClockTimeout" for item in records
        ),
        "avg_time_to_first_token_seconds": round(sum(first_token_values) / len(first_token_values), 6)
        if first_token_values
        else None,
        "max_time_to_first_token_seconds": round(max(first_token_values), 6) if first_token_values else None,
        "avg_time_to_complete_seconds": round(sum(complete_values) / len(complete_values), 6)
        if complete_values
        else None,
        "max_time_to_complete_seconds": round(max(complete_values), 6) if complete_values else None,
        "finish_reason_distribution": distribution,
    }


def execute_thinking_arm(
    *,
    provider_config: Any,
    arm_spec: ThinkingArmSpec,
    dataset_payload: dict[str, Any],
    seed_prompt_name: str,
    max_metric_calls: int,
    sleep_between_requests: float,
    max_retries: int,
    arm_dir: Path,
) -> dict[str, Any]:
    arm_dir.mkdir(parents=True, exist_ok=True)
    health_checks: list[dict[str, Any]] = []
    request_records: list[dict[str, Any]] = []
    pre_health = execute_health_check(
        provider_config=provider_config,
        arm_spec=arm_spec,
        phase="before",
        arm_dir=arm_dir,
        request_index=0,
    )
    health_checks.append(pre_health)
    if pre_health["status"] != "ok" or not pre_health.get("content_exact_ok"):
        arm_result = {
            "thinking_type": arm_spec.thinking_type,
            "status": "blocked_by_health_check",
            "optimize_called": False,
            "optimize_completed": False,
            "health_before": pre_health,
            "health_after": None,
            "request_summary": summarize_request_records(request_records),
            "failure_reason": "pre_health_check_failed",
            **DIAGNOSTIC_FLAGS,
        }
        BASE.write_jsonl(arm_dir / "per_request_eval.jsonl", request_records)
        BASE.write_jsonl(arm_dir / "health_checks.jsonl", health_checks)
        write_json(arm_dir / "arm_result.json", arm_result)
        return arm_result

    bridge = StreamingLitellmBridge(
        provider_config=provider_config,
        arm_spec=arm_spec,
        arm_dir=arm_dir,
        sleep_between_requests=sleep_between_requests,
        max_retries=max_retries,
    )
    optimize_kwargs = build_optimize_kwargs(
        provider_config=provider_config,
        dataset_payload=dataset_payload,
        seed_prompt_name=seed_prompt_name,
        max_metric_calls=max_metric_calls,
        arm_dir=arm_dir,
    )
    try:
        import gepa

        with temporary_openai_compatible_env(api_key=provider_config.api_key, api_base=provider_config.api_base):
            with patch_litellm_for_streaming(bridge):
                result = gepa.optimize(**optimize_kwargs)
        request_records.extend(bridge.records)
        post_health = execute_health_check(
            provider_config=provider_config,
            arm_spec=arm_spec,
            phase="after",
            arm_dir=arm_dir,
            request_index=len(request_records) + 1,
        )
        health_checks.append(post_health)
        best_idx = int(result.best_idx)
        best_score = float(result.val_aggregate_scores[best_idx])
        arm_result = {
            "thinking_type": arm_spec.thinking_type,
            "status": "ok",
            "optimize_called": True,
            "optimize_completed": True,
            "health_before": pre_health,
            "health_after": post_health,
            "gepa_result_summary": {
                "best_idx": best_idx,
                "best_score": best_score,
                "total_metric_calls": int(result.total_metric_calls),
                "num_candidates": int(result.num_candidates),
                "num_val_instances": int(result.num_val_instances),
                "num_full_val_evals": int(result.num_full_val_evals),
            },
            "request_summary": summarize_request_records(request_records),
            **DIAGNOSTIC_FLAGS,
        }
    except Exception as exc:  # pragma: no cover - 真实 GEPA 路径
        request_records.extend(bridge.records)
        post_health = execute_health_check(
            provider_config=provider_config,
            arm_spec=arm_spec,
            phase="after",
            arm_dir=arm_dir,
            request_index=len(request_records) + 1,
        )
        health_checks.append(post_health)
        secrets = [provider_config.api_key]
        error_message, error_body = BASE.extract_error_message(exc, secrets=secrets)
        arm_result = {
            "thinking_type": arm_spec.thinking_type,
            "status": "error",
            "optimize_called": True,
            "optimize_completed": False,
            "health_before": pre_health,
            "health_after": post_health,
            "error_type": type(exc).__name__,
            "error_message_sanitized": error_message,
            "error_body_sanitized": error_body,
            "request_summary": summarize_request_records(request_records),
            **DIAGNOSTIC_FLAGS,
        }

    BASE.write_jsonl(arm_dir / "per_request_eval.jsonl", request_records)
    BASE.write_jsonl(arm_dir / "health_checks.jsonl", health_checks)
    write_json(arm_dir / "arm_result.json", arm_result)
    return arm_result


def _arm_worker(queue: Any, payload: dict[str, Any]) -> None:
    try:
        result = execute_thinking_arm(
            provider_config=BASE.ProviderConfig(**payload["provider_config"]),
            arm_spec=ThinkingArmSpec(**payload["arm_spec"]),
            dataset_payload=payload["dataset_payload"],
            seed_prompt_name=payload["seed_prompt_name"],
            max_metric_calls=payload["max_metric_calls"],
            sleep_between_requests=payload["sleep_between_requests"],
            max_retries=payload["max_retries"],
            arm_dir=Path(payload["arm_dir"]),
        )
        queue.put({"status": "ok", "result": result})
    except Exception as exc:  # pragma: no cover - 防御路径
        queue.put({"status": "worker_exception", "error_type": type(exc).__name__, "error_message": str(exc)})


def execute_arm_with_emergency_guard(
    *,
    provider_config: Any,
    arm_spec: ThinkingArmSpec,
    dataset_payload: dict[str, Any],
    seed_prompt_name: str,
    max_metric_calls: int,
    sleep_between_requests: float,
    max_retries: int,
    run_dir: Path,
) -> dict[str, Any]:
    arm_dir = run_dir / "arms" / arm_spec.thinking_type
    ctx = mp.get_context("fork" if os.name != "nt" else "spawn")
    queue = ctx.Queue()
    payload = {
        "provider_config": {
            "provider": provider_config.provider,
            "api_base": provider_config.api_base,
            "api_key_env": provider_config.api_key_env,
            "api_key": provider_config.api_key,
            "model": provider_config.model,
            "litellm_provider_string": provider_config.litellm_provider_string,
        },
        "arm_spec": asdict(arm_spec),
        "dataset_payload": dataset_payload,
        "seed_prompt_name": seed_prompt_name,
        "max_metric_calls": max_metric_calls,
        "sleep_between_requests": sleep_between_requests,
        "max_retries": max_retries,
        "arm_dir": str(arm_dir),
    }
    process = ctx.Process(target=_arm_worker, args=(queue, payload))
    process.start()
    process.join(arm_spec.emergency_guard_timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5.0)
        arm_dir.mkdir(parents=True, exist_ok=True)
        result = {
            "thinking_type": arm_spec.thinking_type,
            "status": "timeout",
            "optimize_called": True,
            "optimize_completed": False,
            "error_type": "EmergencyGuardTimeout",
            "error_message_sanitized": "Emergency guard timeout exceeded.",
            "health_before": None,
            "health_after": None,
            "request_summary": summarize_request_records([]),
            **DIAGNOSTIC_FLAGS,
        }
        write_json(arm_dir / "arm_result.json", result)
        return result
    try:
        payload = queue.get_nowait()
    except queue.Empty:
        payload = {"status": "worker_exception", "error_type": "MissingWorkerPayload", "error_message": ""}
    if payload.get("status") == "ok":
        return payload["result"]
    arm_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "thinking_type": arm_spec.thinking_type,
        "status": "error",
        "optimize_called": True,
        "optimize_completed": False,
        "error_type": payload.get("error_type"),
        "error_message_sanitized": str(payload.get("error_message") or ""),
        "health_before": None,
        "health_after": None,
        "request_summary": summarize_request_records([]),
        **DIAGNOSTIC_FLAGS,
    }
    write_json(arm_dir / "arm_result.json", result)
    return result


def build_input_snapshot(
    *,
    provider_config: Any,
    arm_specs: list[ThinkingArmSpec],
    dataset_payload: dict[str, Any],
    seed_prompt_name: str,
    max_metric_calls: int,
    sleep_between_requests: float,
    max_retries: int,
    run_dir: Path,
    execute: bool,
) -> dict[str, Any]:
    return {
        "metadata": {
            "generated_at": create_timestamp(),
            "mode": "execute" if execute else "dry_run",
            "run_dir": BASE.project_relative(run_dir),
            "model_called": bool(execute),
            "api_called": bool(execute),
            "new_experiment_executed": bool(execute),
            **DIAGNOSTIC_FLAGS,
        },
        "provider_config": {
            "provider": provider_config.provider,
            "model": provider_config.model,
            "api_base_present": provider_config.api_base_present,
            "backend_family": provider_config.backend_family,
            "missing_config_reasons": provider_config.missing_config_reasons(),
        },
        "requested_execution": {
            "paired_thinking_diagnostic": True,
            "thinking_types": [item.thinking_type for item in arm_specs],
            "seed_prompt": seed_prompt_name,
            "streaming": True,
            "max_metric_calls": max_metric_calls,
            "diagnostic_val_limit": dataset_payload["diagnostic_val_limit"],
            "sleep_between_requests": sleep_between_requests,
            "max_retries": max_retries,
            "arm_specs": [asdict(item) for item in arm_specs],
        },
        "dataset_meta": {
            "dataset_source": dataset_payload["dataset_source"],
            "adaptation_notes": dataset_payload["adaptation_notes"],
            "trainset_size": dataset_payload["trainset_size"],
            "valset_size_full": dataset_payload["valset_size_full"],
            "valset_size_used": dataset_payload["valset_size_used"],
        },
    }


def build_dry_run_results(
    *,
    provider_config: Any,
    arm_specs: list[ThinkingArmSpec],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    missing = provider_config.missing_config_reasons()
    for arm_spec in arm_specs:
        results.append(
            {
                "thinking_type": arm_spec.thinking_type,
                "status": "dry_run",
                "optimize_called": False,
                "optimize_completed": False,
                "health_before": None,
                "health_after": None,
                "request_summary": summarize_request_records([]),
                "error_type": "ConfigPreview" if missing else None,
                "error_message_sanitized": "; ".join(missing) if missing else None,
                **DIAGNOSTIC_FLAGS,
            }
        )
    return results


def build_failure_cases(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for item in results:
        if item.get("status") == "ok":
            continue
        failures.append(
            {
                "thinking_type": item["thinking_type"],
                "status": item.get("status"),
                "error_type": item.get("error_type"),
                "error_message_sanitized": item.get("error_message_sanitized"),
            }
        )
    return failures


def build_run_summary(*, results: list[dict[str, Any]], execute: bool) -> dict[str, Any]:
    return {
        "generated_at": create_timestamp(),
        "mode": "execute" if execute else "dry_run",
        "arm_count": len(results),
        "completed_arms": [item["thinking_type"] for item in results if item.get("status") == "ok"],
        "blocked_arms": [item["thinking_type"] for item in results if item.get("status") == "blocked_by_health_check"],
        "failure_cases": build_failure_cases(results) if execute else [],
        **DIAGNOSTIC_FLAGS,
    }


def render_report(payload: dict[str, Any], results: list[dict[str, Any]], run_summary: dict[str, Any]) -> str:
    metadata = payload["metadata"]
    requested = payload["requested_execution"]
    provider_config = payload["provider_config"]
    lines = [
        "# Stage 4C GLM streaming GEPA sanity 结果",
        "",
        "## 定位",
        "",
        "- 本报告只记录 GLM streaming GEPA micro-sanity paired diagnostic。",
        "- 它不是 official_budget。",
        "- 它不是模型排名。",
        "- 它不是 strict default path 对比。",
        "- 它不是最终性能结论。",
        "",
        "## 边界标记",
        "",
    ]
    for key, value in metadata.items():
        if isinstance(value, bool):
            lines.append(f"- `{key} = {str(value).lower()}`")

    lines.extend(
        [
            "",
            "## 配置",
            "",
            f"- provider：`{provider_config['provider']}`",
            f"- model：`{provider_config['model'] or '<missing>'}`",
            f"- api_base_present：`{str(provider_config['api_base_present']).lower()}`",
            f"- thinking_types：`{', '.join(requested['thinking_types'])}`",
            f"- seed_prompt：`{requested['seed_prompt']}`",
            f"- max_metric_calls：`{requested['max_metric_calls']}`",
            f"- diagnostic_val_limit：`{requested['diagnostic_val_limit']}`",
            f"- sleep_between_requests：`{requested['sleep_between_requests']}`",
            "",
            "## 执行状态",
            "",
        ]
    )
    if metadata["mode"] == "dry_run":
        lines.extend(
            [
                "- 当前状态：dry-run manifest 已生成，未调用模型，未调用 `gepa.optimize()`。",
                "- 只验证了 paired thinking 顺序、timeout 预算配置、artifact schema 与报告骨架。",
            ]
        )
    else:
        lines.extend(
            [
                "- 当前状态：真实 paired diagnostic 已执行。",
                f"- completed_arms：`{', '.join(run_summary['completed_arms']) or 'none'}`",
                f"- blocked_arms：`{', '.join(run_summary['blocked_arms']) or 'none'}`",
            ]
        )

    lines.extend(
        [
            "",
            "## Arm 汇总",
            "",
            "| thinking_type | status | optimize_called | optimize_completed | health_before | health_after | total_metric_calls | request_count | timeout_count | avg_first_token | max_first_token |",
            "|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for item in results:
        health_before = (
            item["health_before"]["status"] if isinstance(item.get("health_before"), dict) else None
        )
        health_after = item["health_after"]["status"] if isinstance(item.get("health_after"), dict) else None
        gepa_summary = item.get("gepa_result_summary") or {}
        request_summary = item.get("request_summary") or {}
        lines.append(
            f"| `{item['thinking_type']}` | `{item.get('status')}` | {int(bool(item.get('optimize_called')))} | "
            f"{int(bool(item.get('optimize_completed')))} | `{health_before}` | `{health_after}` | "
            f"{gepa_summary.get('total_metric_calls', 0)} | {request_summary.get('request_count', 0)} | "
            f"{request_summary.get('timeout_count', 0)} | {request_summary.get('avg_time_to_first_token_seconds')} | "
            f"{request_summary.get('max_time_to_first_token_seconds')} |"
        )

    if metadata["mode"] == "execute" and run_summary["failure_cases"]:
        lines.extend(
            [
                "",
                "## failure-mode table",
                "",
                "| thinking_type | status | error_type | error_message |",
                "|---|---|---|---|",
            ]
        )
        for item in run_summary["failure_cases"]:
            lines.append(
                f"| `{item['thinking_type']}` | `{item.get('status')}` | `{item.get('error_type')}` | "
                f"{item.get('error_message_sanitized') or '-'} |"
            )

    lines.extend(
        [
            "",
            "## 结论边界",
            "",
            "- 可以写：default / disabled thinking 两个 arm 是否跑通、health check 是否正常、请求级 timeout 类型与首 token 延迟特征。",
            "- 不能写：GLM 比 MiMo 强，或 GLM 已适合 official_budget / GEPA 正式复现。",
        ]
    )
    return "\n".join(lines) + "\n"


def run_execute(
    *,
    provider_config: Any,
    arm_specs: list[ThinkingArmSpec],
    dataset_payload: dict[str, Any],
    seed_prompt_name: str,
    max_metric_calls: int,
    sleep_between_requests: float,
    max_retries: int,
    run_dir: Path,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for arm_spec in arm_specs:
        results.append(
            execute_arm_with_emergency_guard(
                provider_config=provider_config,
                arm_spec=arm_spec,
                dataset_payload=dataset_payload,
                seed_prompt_name=seed_prompt_name,
                max_metric_calls=max_metric_calls,
                sleep_between_requests=sleep_between_requests,
                max_retries=max_retries,
                run_dir=run_dir,
            )
        )
    return results


def main() -> None:
    args = parse_args()
    arm_specs = build_arm_specs(args.thinking_types)
    enforce_bounds(args, arm_specs)
    provider_config = build_glm_provider_config(args)
    dataset_payload = build_dataset_payload(args.diagnostic_val_limit)
    report_path = (PROJECT_ROOT / args.report_path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if args.run_dir:
        run_dir = (PROJECT_ROOT / args.run_dir).resolve()
        run_dir.mkdir(parents=True, exist_ok=True)
    else:
        run_dir = create_run_dir((PROJECT_ROOT / args.output_dir).resolve())

    input_snapshot = build_input_snapshot(
        provider_config=provider_config,
        arm_specs=arm_specs,
        dataset_payload=dataset_payload,
        seed_prompt_name=args.seed_prompt,
        max_metric_calls=args.max_metric_calls,
        sleep_between_requests=args.sleep_between_requests,
        max_retries=args.max_retries,
        run_dir=run_dir,
        execute=args.execute,
    )
    write_json(run_dir / "input_snapshot.json", input_snapshot)

    if args.execute:
        results = run_execute(
            provider_config=provider_config,
            arm_specs=arm_specs,
            dataset_payload=dataset_payload,
            seed_prompt_name=args.seed_prompt,
            max_metric_calls=args.max_metric_calls,
            sleep_between_requests=args.sleep_between_requests,
            max_retries=args.max_retries,
            run_dir=run_dir,
        )
    else:
        results = build_dry_run_results(provider_config=provider_config, arm_specs=arm_specs)

    paired_results = {
        "generated_at": create_timestamp(),
        "mode": "execute" if args.execute else "dry_run",
        "results": results,
        **DIAGNOSTIC_FLAGS,
    }
    run_summary = build_run_summary(results=results, execute=args.execute)
    write_json(run_dir / "paired_results.json", paired_results)
    write_json(run_dir / "run_summary.json", run_summary)
    write_json(run_dir / "failure_cases.json", run_summary["failure_cases"])
    write_text(report_path, render_report(input_snapshot, results, run_summary))
    print(
        json.dumps(
            {
                "run_dir": BASE.project_relative(run_dir),
                "report_path": BASE.project_relative(report_path),
                "mode": input_snapshot["metadata"]["mode"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
