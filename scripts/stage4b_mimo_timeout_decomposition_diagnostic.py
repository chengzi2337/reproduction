from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
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


DEFAULT_OUTPUT_DIR = "outputs/stage4b_mimo_timeout_decomposition_diagnostic"
DEFAULT_REPORT_PATH = "reports/stage4b_mimo_timeout_decomposition_diagnostic_result.md"
DEFAULT_SAMPLE_IDS: tuple[str, ...] = ("test-1", "test-2", "test-3", "test-4", "test-5")
DEFAULT_TIMEOUT_VALUES: tuple[int, ...] = (60, 120, 240)
DEFAULT_MODES: tuple[str, ...] = ("non_streaming", "streaming")
DEFAULT_PROMPT_LAYERS: tuple[str, ...] = (
    "l2_question_only",
    "l3_original_seed",
    "l4_strong_format",
)
DEFAULT_SLEEP_SECONDS = 60.0

DIAGNOSTIC_FLAGS: dict[str, bool] = {
    "stage4b_mimo_timeout_decomposition_diagnostic": True,
    "diagnostic_only": True,
    "mimo_only": True,
    "not_gepa_result": True,
    "not_official_budget": True,
    "not_performance_claim": True,
    "no_gepa_optimize_called": True,
    "not_strict_stage4b_result": True,
}


class Stage4BMiMoTimeoutDiagnosticError(RuntimeError):
    """MiMo timeout decomposition diagnostic 的配置或 artifact 不满足要求。"""


@dataclass(frozen=True)
class PromptLayerSpec:
    name: str
    label: str
    prompt_variant: str
    system_prompt: str
    description: str


def _load_stage4b_base_module() -> ModuleType:
    script_path = PROJECT_ROOT / "scripts" / "stage4b_eval_fixed_prompt_aime_mimopro_glm47.py"
    spec = importlib.util.spec_from_file_location("stage4b_mimo_timeout_base_script", script_path)
    if spec is None or spec.loader is None:
        raise Stage4BMiMoTimeoutDiagnosticError(f"无法加载 Stage 4B base script：{script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_stage4b_base_module()

PROMPT_LAYERS: dict[str, PromptLayerSpec] = {
    "l2_question_only": PromptLayerSpec(
        name="l2_question_only",
        label="L2",
        prompt_variant="real_aime_question_only",
        system_prompt="",
        description="只传 AIME question，不添加格式约束。",
    ),
    "l3_original_seed": PromptLayerSpec(
        name="l3_original_seed",
        label="L3",
        prompt_variant="original_seed_prompt",
        system_prompt=BASE.PROMPTS["original_seed_prompt"],
        description="AIME question + original_seed_prompt。",
    ),
    "l4_strong_format": PromptLayerSpec(
        name="l4_strong_format",
        label="L4",
        prompt_variant="strong_format_seed_prompt",
        system_prompt=BASE.PROMPTS["strong_format_seed_prompt"],
        description="AIME question + strong_format_seed_prompt。",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage 4B MiMo timeout decomposition diagnostic。默认 dry-run，只有 --execute 才调用模型。"
    )
    parser.add_argument("--provider", choices=("mimo",), default="mimo", help="当前仅允许 mimo。")
    parser.add_argument("--api-key-env", default="MIMO_API_KEY", help="MiMo API key 的环境变量名。")
    parser.add_argument("--api-base-env", default="MIMO_API_BASE", help="MiMo API base 的环境变量名。")
    parser.add_argument("--model-env", default="MIMO_MODEL", help="MiMo model 的环境变量名。")
    parser.add_argument(
        "--backend-path",
        choices=("raw_sdk",),
        default="raw_sdk",
        help="当前 timeout decomposition 只允许 raw_sdk。",
    )
    parser.add_argument(
        "--sample-ids",
        nargs="+",
        default=list(DEFAULT_SAMPLE_IDS),
        help="要执行的 sample_id 列表，默认 test-1 到 test-5。",
    )
    parser.add_argument(
        "--timeout-values",
        nargs="+",
        type=int,
        default=list(DEFAULT_TIMEOUT_VALUES),
        help="要执行的 timeout 秒数列表，默认 60 120 240。",
    )
    parser.add_argument(
        "--sleep-between-requests",
        type=float,
        default=DEFAULT_SLEEP_SECONDS,
        help="相邻 AIME 请求之间的等待秒数。",
    )
    parser.add_argument("--max-retries", type=int, default=0, help="单请求重试次数。")
    parser.add_argument(
        "--mode",
        nargs="+",
        choices=DEFAULT_MODES,
        default=list(DEFAULT_MODES),
        help="执行模式，可选 non_streaming / streaming。",
    )
    parser.add_argument(
        "--prompt-layers",
        nargs="+",
        choices=tuple(PROMPT_LAYERS.keys()),
        default=list(DEFAULT_PROMPT_LAYERS),
        help="要执行的 prompt layer 列表。",
    )
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
        raise Stage4BMiMoTimeoutDiagnosticError("当前脚本只允许 provider=mimo。")
    if args.backend_path != "raw_sdk":
        raise Stage4BMiMoTimeoutDiagnosticError("当前脚本只允许 backend_path=raw_sdk。")
    if args.max_retries < 0:
        raise Stage4BMiMoTimeoutDiagnosticError("--max-retries 不能小于 0。")
    if args.sleep_between_requests < 0:
        raise Stage4BMiMoTimeoutDiagnosticError("--sleep-between-requests 不能小于 0。")
    if not args.sample_ids:
        raise Stage4BMiMoTimeoutDiagnosticError("--sample-ids 不能为空。")
    if len(args.sample_ids) > 5:
        raise Stage4BMiMoTimeoutDiagnosticError("当前 timeout decomposition 最多只允许 5 个样本。")
    if any(not re.fullmatch(r"test-\d+", str(sample_id)) for sample_id in args.sample_ids):
        raise Stage4BMiMoTimeoutDiagnosticError("sample_id 必须是 test-<n> 形式。")
    if not args.timeout_values:
        raise Stage4BMiMoTimeoutDiagnosticError("--timeout-values 不能为空。")
    if any(int(value) <= 0 for value in args.timeout_values):
        raise Stage4BMiMoTimeoutDiagnosticError("timeout-values 中的每个值都必须大于 0。")


def load_prompt_layers(selected_layers: list[str]) -> list[PromptLayerSpec]:
    names = list(dict.fromkeys(str(name) for name in selected_layers))
    unknown = sorted(set(names) - set(PROMPT_LAYERS))
    if unknown:
        raise Stage4BMiMoTimeoutDiagnosticError(f"未知 prompt layer：{', '.join(unknown)}")
    return [PROMPT_LAYERS[name] for name in names]


def load_modes(selected_modes: list[str]) -> list[str]:
    modes = list(dict.fromkeys(str(mode) for mode in selected_modes))
    unknown = sorted(set(modes) - set(DEFAULT_MODES))
    if unknown:
        raise Stage4BMiMoTimeoutDiagnosticError(f"未知 mode：{', '.join(unknown)}")
    return modes


def load_timeout_values(values: list[int]) -> list[int]:
    timeout_values = [int(value) for value in dict.fromkeys(values)]
    if not timeout_values:
        raise Stage4BMiMoTimeoutDiagnosticError("timeout-values 不能为空。")
    if any(value <= 0 for value in timeout_values):
        raise Stage4BMiMoTimeoutDiagnosticError("timeout-values 中的每个值都必须大于 0。")
    return timeout_values


def build_selected_samples(sample_ids: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    limit = max(int(str(sample_id).split("-")[-1]) for sample_id in sample_ids)
    if limit > 5:
        raise Stage4BMiMoTimeoutDiagnosticError("当前 timeout decomposition 只允许访问前 5 个样本。")
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
        raise Stage4BMiMoTimeoutDiagnosticError(f"指定的 sample_id 不在可访问样本内：{', '.join(missing)}")
    dataset_meta = dict(dataset_meta)
    dataset_meta["selected_sample_ids"] = [entry["sample_id"] for entry in selected]
    dataset_meta["selected_count"] = len(selected)
    dataset_meta["subset_selector"] = "explicit_sample_ids"
    return selected, dataset_meta


def build_messages(*, layer_spec: PromptLayerSpec, question: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if layer_spec.system_prompt.strip():
        messages.append({"role": "system", "content": layer_spec.system_prompt})
    messages.append({"role": "user", "content": question})
    return messages


def make_prompt_spec(layer_spec: PromptLayerSpec) -> Any:
    return BASE.PromptSpec(name=layer_spec.prompt_variant, system_prompt=layer_spec.system_prompt)


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


def normalize_stream_chunk_payload(chunk: Any) -> dict[str, Any] | None:
    payload = BASE.to_jsonable(chunk)
    if not isinstance(payload, dict):
        return None
    nested = payload.get("payload")
    if isinstance(nested, dict) and "choices" in nested:
        return nested
    return payload


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


def build_record_key(record: dict[str, Any]) -> str:
    return "::".join(
        [
            str(record.get("provider")),
            str(record.get("backend_path")),
            str(record.get("mode")),
            str(record.get("prompt_layer")),
            str(record.get("timeout_setting")),
            str(record.get("sample_id")),
        ]
    )


def normalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        latest[build_record_key(record)] = record
    return list(latest.values())


def classify_prediction(*, content: str, gold: str) -> dict[str, Any]:
    payload = BASE.classify_prediction(content=content, gold=gold)
    payload["relaxed_extractable_correct"] = bool(payload["relaxed_extractable_correct"])
    return payload


def save_raw_payload(
    *,
    run_dir: Path,
    record: dict[str, Any],
    payload: dict[str, Any],
) -> str:
    raw_dir = run_dir / "raw_responses"
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_name = "__".join(
        [
            BASE.slugify(record["provider"]),
            BASE.slugify(record["mode"]),
            BASE.slugify(record["prompt_layer"]),
            BASE.slugify(str(record["timeout_setting"])),
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
    mode: str,
    layer_spec: PromptLayerSpec,
    sample_id: str,
    gold: str,
    timeout_setting: int,
    sleep_between_requests: float,
    max_retries: int,
) -> dict[str, Any]:
    prompt_spec = make_prompt_spec(layer_spec)
    record = BASE.base_record(
        provider_config=provider_config,
        backend_path=backend_path,
        prompt_spec=prompt_spec,
        sample_id=sample_id,
        gold=gold,
    )
    record.update(
        {
            "mode": mode,
            "prompt_layer": layer_spec.name,
            "prompt_layer_label": layer_spec.label,
            "prompt_layer_description": layer_spec.description,
            "timeout_setting": timeout_setting,
            "sleep_between_requests": sleep_between_requests,
            "max_retries": max_retries,
            "started_at": None,
            "completed_at": None,
            "time_to_first_token_seconds": None,
            "time_to_complete_seconds": 0.0,
            "first_token_observed": False,
            "reasoning_only_output": False,
            "raw_response_path": None,
            "error_code": None,
            "provider_error": False,
            "rate_limit_observed": False,
            **DIAGNOSTIC_FLAGS,
        }
    )
    return record


def create_health_record(
    *,
    provider_config: Any,
    backend_path: str,
    mode: str,
    timeout_setting: int,
    phase: str,
    round_label: str,
) -> dict[str, Any]:
    return {
        "provider": provider_config.provider,
        "model": provider_config.model,
        "backend_path": backend_path,
        "mode": mode,
        "timeout_setting": timeout_setting,
        "phase": phase,
        "round_label": round_label,
        "prompt": "Return exactly: OK",
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


def execute_health_check(
    *,
    provider_config: Any,
    backend_path: str,
    mode: str,
    timeout_setting: int,
    phase: str,
    round_label: str,
    run_dir: Path,
) -> dict[str, Any]:
    record = create_health_record(
        provider_config=provider_config,
        backend_path=backend_path,
        mode=mode,
        timeout_setting=timeout_setting,
        phase=phase,
        round_label=round_label,
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
            timeout=float(timeout_setting),
            max_retries=0,
        )
        if mode == "non_streaming":
            raw_response = client.chat.completions.with_raw_response.create(
                model=provider_config.model,
                messages=messages,
                temperature=0,
                timeout=float(timeout_setting),
            )
            completion = raw_response.parse()
            choice = completion.choices[0] if getattr(completion, "choices", None) else None
            message = getattr(choice, "message", None) if choice is not None else None
            content = BASE.extract_message_content(message)
            record["http_status"] = getattr(raw_response, "status_code", None)
            raw_payload: dict[str, Any] = {
                "http_status": record["http_status"],
                "completion": BASE.to_jsonable(completion),
            }
        else:
            content_parts: list[str] = []
            chunk_payloads: list[dict[str, Any]] = []
            stream = client.chat.completions.create(
                model=provider_config.model,
                messages=messages,
                temperature=0,
                timeout=float(timeout_setting),
                stream=True,
            )
            try:
                record["http_status"] = _extract_stream_http_status(stream)
                for chunk in stream:
                    chunk_payload = normalize_stream_chunk_payload(chunk)
                    if isinstance(chunk_payload, dict):
                        chunk_payloads.append(chunk_payload)
                        chunk_content, _, _ = extract_stream_chunk_fields(chunk_payload)
                        if chunk_content:
                            content_parts.append(chunk_content)
            finally:
                close_fn = getattr(stream, "close", None)
                if callable(close_fn):
                    close_fn()
            content = "".join(content_parts)
            raw_payload = {"http_status": record["http_status"], "chunks": chunk_payloads}
        record["latency_seconds"] = round(time.monotonic() - start_time, 6)
        record["completed_at"] = now_iso()
        record["content_preview"] = BASE.sanitize_text(content, secrets=secrets, limit=120)
        record["content_exact_ok"] = content.strip() == "OK"
        record["raw_response_path"] = save_raw_payload(
            run_dir=run_dir,
            record={
                "provider": provider_config.provider,
                "mode": f"health_{mode}_{phase}",
                "prompt_layer": round_label,
                "timeout_setting": timeout_setting,
                "sample_id": "health_check",
            },
            payload={
                "messages": messages,
                "content": content,
                "raw_payload": raw_payload,
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
        record["content_preview"] = ""
        record["raw_response_path"] = save_raw_payload(
            run_dir=run_dir,
            record={
                "provider": provider_config.provider,
                "mode": f"health_{mode}_{phase}",
                "prompt_layer": round_label,
                "timeout_setting": timeout_setting,
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
    mode: str,
    layer_spec: PromptLayerSpec,
    sample_entry: dict[str, Any],
    timeout_setting: int,
    sleep_between_requests: float,
    max_retries: int,
    run_dir: Path,
) -> dict[str, Any]:
    record = create_record(
        provider_config=provider_config,
        backend_path=backend_path,
        mode=mode,
        layer_spec=layer_spec,
        sample_id=sample_entry["sample_id"],
        gold=sample_entry["gold"],
        timeout_setting=timeout_setting,
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
    messages = build_messages(layer_spec=layer_spec, question=sample_entry["question"])
    record["started_at"] = now_iso()
    start_time = time.monotonic()
    try:
        client = OpenAI(
            api_key=provider_config.api_key,
            base_url=provider_config.api_base,
            timeout=float(timeout_setting),
            max_retries=0,
        )
        raw_payload: dict[str, Any]
        finish_reason: str | None = None
        content = ""
        reasoning_text = ""
        if mode == "non_streaming":
            raw_response = client.chat.completions.with_raw_response.create(
                model=provider_config.model,
                messages=messages,
                temperature=0,
                timeout=float(timeout_setting),
            )
            completion = raw_response.parse()
            choice = completion.choices[0] if getattr(completion, "choices", None) else None
            message = getattr(choice, "message", None) if choice is not None else None
            content = BASE.extract_message_content(message)
            finish_reason = getattr(choice, "finish_reason", None)
            record["http_status"] = getattr(raw_response, "status_code", None)
            record["reasoning_content_present"] = BASE.extract_reasoning_content_present(message)
            raw_payload = {
                "http_status": record["http_status"],
                "completion": BASE.to_jsonable(completion),
            }
        else:
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            chunk_payloads: list[dict[str, Any]] = []
            first_token_time: float | None = None
            stream = client.chat.completions.create(
                model=provider_config.model,
                messages=messages,
                temperature=0,
                timeout=float(timeout_setting),
                stream=True,
            )
            try:
                record["http_status"] = _extract_stream_http_status(stream)
                for chunk in stream:
                    chunk_payload = normalize_stream_chunk_payload(chunk)
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
            finally:
                close_fn = getattr(stream, "close", None)
                if callable(close_fn):
                    close_fn()
            content = "".join(content_parts)
            reasoning_text = "".join(reasoning_parts)
            record["reasoning_content_present"] = bool(reasoning_text)
            record["first_token_observed"] = first_token_time is not None
            record["time_to_first_token_seconds"] = (
                round(first_token_time - start_time, 6) if first_token_time is not None else None
            )
            raw_payload = {"http_status": record["http_status"], "chunks": chunk_payloads}

        record["latency_seconds"] = round(time.monotonic() - start_time, 6)
        record["time_to_complete_seconds"] = record["latency_seconds"]
        record["completed_at"] = now_iso()
        record["status"] = "ok"
        record["completed"] = True
        record["request_completed"] = True
        record["finish_reason"] = finish_reason
        record["content_nonempty"] = bool(content.strip())
        record["raw_response_preview"] = BASE.sanitize_text(content, secrets=secrets, limit=240)
        record.update(classify_prediction(content=content, gold=sample_entry["gold"]))
        record["reasoning_only_output"] = bool(record["reasoning_content_present"]) and not bool(content.strip())
        record["raw_response_path"] = save_raw_payload(
            run_dir=run_dir,
            record=record,
            payload={
                "provider": record["provider"],
                "model": record["model"],
                "backend_path": backend_path,
                "mode": mode,
                "prompt_layer": layer_spec.name,
                "sample_id": sample_entry["sample_id"],
                "question": sample_entry["question"],
                "gold": sample_entry["gold"],
                "messages": messages,
                "content": content,
                "reasoning_text": reasoning_text,
                "reasoning_content_present": record["reasoning_content_present"],
                "finish_reason": finish_reason,
                "http_status": record["http_status"],
                "raw_payload": raw_payload,
            },
        )
        return record
    except Exception as exc:  # pragma: no cover - 真实 provider 路径
        record["latency_seconds"] = round(time.monotonic() - start_time, 6)
        record["time_to_complete_seconds"] = record["latency_seconds"]
        record["completed_at"] = now_iso()
        record["http_status"] = BASE.extract_http_status_from_error(exc)
        error_message, error_body = BASE.extract_error_message(exc, secrets=secrets)
        timeout = BASE.is_timeout_error(exc)
        record.update(
            {
                "status": "timeout" if timeout else "error",
                "timeout": timeout,
                "empty_or_invalid": True,
                "error_type": type(exc).__name__,
                "error_message_sanitized": error_message,
                "error_body_sanitized": error_body,
                "diagnosis": "timeout" if timeout else "provider_error",
                "provider_error": not timeout,
            }
        )
        record["error_code"] = extract_error_code(record)
        record["rate_limit_observed"] = is_rate_limit_record(record)
        record["raw_response_path"] = save_raw_payload(
            run_dir=run_dir,
            record=record,
            payload={
                "provider": record["provider"],
                "model": record["model"],
                "backend_path": backend_path,
                "mode": mode,
                "prompt_layer": layer_spec.name,
                "sample_id": sample_entry["sample_id"],
                "question": sample_entry["question"],
                "gold": sample_entry["gold"],
                "messages": messages,
                "error_type": type(exc).__name__,
                "error_message_sanitized": error_message,
                "error_body_sanitized": error_body,
                "http_status": record["http_status"],
            },
        )
        return record


def build_dry_run_records(
    *,
    provider_config: Any,
    backend_path: str,
    modes: list[str],
    layer_specs: list[PromptLayerSpec],
    sample_entries: list[dict[str, Any]],
    timeout_values: list[int],
    sleep_between_requests: float,
    max_retries: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    missing = provider_config.missing_config_reasons()
    for mode in modes:
        for timeout_setting in timeout_values:
            for layer_spec in layer_specs:
                for sample_entry in sample_entries:
                    record = create_record(
                        provider_config=provider_config,
                        backend_path=backend_path,
                        mode=mode,
                        layer_spec=layer_spec,
                        sample_id=sample_entry["sample_id"],
                        gold=sample_entry["gold"],
                        timeout_setting=timeout_setting,
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
    modes: list[str],
    timeout_values: list[int],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    missing = provider_config.missing_config_reasons()
    for mode in modes:
        for timeout_setting in timeout_values:
            round_label = f"{mode}@{timeout_setting}s"
            for phase in ("pre", "post"):
                record = create_health_record(
                    provider_config=provider_config,
                    backend_path=backend_path,
                    mode=mode,
                    timeout_setting=timeout_setting,
                    phase=phase,
                    round_label=round_label,
                )
                if missing:
                    record["error_type"] = "ConfigPreview"
                    record["error_message_sanitized"] = "; ".join(missing)
                records.append(record)
    return records


def execute_timeout_plan(
    *,
    provider_config: Any,
    backend_path: str,
    modes: list[str],
    layer_specs: list[PromptLayerSpec],
    sample_entries: list[dict[str, Any]],
    timeout_values: list[int],
    sleep_between_requests: float,
    max_retries: int,
    run_dir: Path,
) -> dict[str, Any]:
    per_example_path = run_dir / "per_example_eval.jsonl"
    health_check_path = run_dir / "health_checks.jsonl"
    records: list[dict[str, Any]] = []
    health_checks: list[dict[str, Any]] = []
    real_request_index = 0

    for mode in modes:
        for timeout_setting in timeout_values:
            round_label = f"{mode}@{timeout_setting}s"
            pre_health = execute_health_check(
                provider_config=provider_config,
                backend_path=backend_path,
                mode=mode,
                timeout_setting=timeout_setting,
                phase="pre",
                round_label=round_label,
                run_dir=run_dir,
            )
            health_checks.append(pre_health)
            BASE.append_jsonl(health_check_path, [pre_health])

            for layer_spec in layer_specs:
                for sample_entry in sample_entries:
                    if real_request_index > 0 and sleep_between_requests > 0:
                        time.sleep(sleep_between_requests)
                    record = execute_single_case(
                        provider_config=provider_config,
                        backend_path=backend_path,
                        mode=mode,
                        layer_spec=layer_spec,
                        sample_entry=sample_entry,
                        timeout_setting=timeout_setting,
                        sleep_between_requests=sleep_between_requests,
                        max_retries=max_retries,
                        run_dir=run_dir,
                    )
                    records.append(record)
                    BASE.append_jsonl(per_example_path, [record])
                    real_request_index += 1

            post_health = execute_health_check(
                provider_config=provider_config,
                backend_path=backend_path,
                mode=mode,
                timeout_setting=timeout_setting,
                phase="post",
                round_label=round_label,
                run_dir=run_dir,
            )
            health_checks.append(post_health)
            BASE.append_jsonl(health_check_path, [post_health])

    records = normalize_records(records)
    BASE.write_jsonl(per_example_path, records)
    BASE.write_jsonl(health_check_path, health_checks)
    return {"records": records, "health_checks": health_checks}


def summarize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(
            (str(record["mode"]), str(record["prompt_layer"]), int(record["timeout_setting"])),
            [],
        ).append(record)

    summaries: list[dict[str, Any]] = []
    for (mode, prompt_layer, timeout_setting), group in sorted(grouped.items(), key=lambda item: item[0]):
        total = len(group)
        completed_count = sum(bool(item.get("completed")) for item in group)
        latency_values = [float(item.get("latency_seconds", 0.0)) for item in group if item.get("latency_seconds")]
        ttft_values = [
            float(item["time_to_first_token_seconds"])
            for item in group
            if item.get("time_to_first_token_seconds") is not None
        ]
        finish_reason_distribution: dict[str, int] = {}
        for item in group:
            finish_reason = str(item.get("finish_reason") or "null")
            finish_reason_distribution[finish_reason] = finish_reason_distribution.get(finish_reason, 0) + 1
        summaries.append(
            {
                "provider": "mimo",
                "backend_path": "raw_sdk",
                "mode": mode,
                "prompt_layer": prompt_layer,
                "timeout_setting": timeout_setting,
                "sample_count": total,
                "completed_count": completed_count,
                "timeout_count": sum(bool(item.get("timeout")) for item in group),
                "rate_limit_count": sum(bool(item.get("rate_limit_observed")) for item in group),
                "provider_error_count": sum(bool(item.get("provider_error")) for item in group),
                "official_score": round(
                    sum(float(item.get("official_score", 0.0)) for item in group) / total,
                    12,
                ),
                "relaxed_extractable_score": round(
                    sum(1.0 if item.get("relaxed_extractable_correct") else 0.0 for item in group) / total,
                    12,
                ),
                "format_loss_count": sum(bool(item.get("format_loss")) for item in group),
                "reasoning_error_count": sum(bool(item.get("reasoning_error")) for item in group),
                "empty_or_invalid_count": sum(bool(item.get("empty_or_invalid")) for item in group),
                "avg_latency_seconds": round(sum(latency_values) / len(latency_values), 6) if latency_values else 0.0,
                "max_latency_seconds": round(max(latency_values), 6) if latency_values else 0.0,
                "avg_time_to_first_token_seconds": round(sum(ttft_values) / len(ttft_values), 6)
                if ttft_values
                else None,
                "max_time_to_first_token_seconds": round(max(ttft_values), 6) if ttft_values else None,
                "finish_reason_distribution": finish_reason_distribution,
                **DIAGNOSTIC_FLAGS,
            }
        )
    return summaries


def build_sample_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record["sample_id"]), []).append(record)
    summaries: list[dict[str, Any]] = []
    for sample_id, group in sorted(grouped.items()):
        summaries.append(
            {
                "sample_id": sample_id,
                "completed_count": sum(bool(item.get("completed")) for item in group),
                "timeout_count": sum(bool(item.get("timeout")) for item in group),
                "rate_limit_count": sum(bool(item.get("rate_limit_observed")) for item in group),
                "provider_error_count": sum(bool(item.get("provider_error")) for item in group),
                "first_token_missing_count": sum(not bool(item.get("first_token_observed")) for item in group),
                "prompt_layers_seen": sorted({str(item.get("prompt_layer")) for item in group}),
                "modes_seen": sorted({str(item.get("mode")) for item in group}),
                "timeout_settings_seen": sorted({int(item.get("timeout_setting")) for item in group}),
            }
        )
    return summaries


def summarize_health_checks(health_checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for record in health_checks:
        grouped.setdefault((str(record["mode"]), int(record["timeout_setting"])), []).append(record)
    summaries: list[dict[str, Any]] = []
    for (mode, timeout_setting), group in sorted(grouped.items()):
        latency_values = [float(item.get("latency_seconds", 0.0)) for item in group if item.get("latency_seconds")]
        summaries.append(
            {
                "mode": mode,
                "timeout_setting": timeout_setting,
                "check_count": len(group),
                "ok_count": sum(bool(item.get("content_exact_ok")) for item in group),
                "error_count": sum(1 for item in group if item.get("error_type")),
                "avg_latency_seconds": round(sum(latency_values) / len(latency_values), 6) if latency_values else 0.0,
                "phases_seen": sorted({str(item.get("phase")) for item in group}),
                **DIAGNOSTIC_FLAGS,
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
                "prompt_layer": record["prompt_layer"],
                "timeout_setting": record["timeout_setting"],
                "first_token_observed": record.get("first_token_observed"),
                "time_to_first_token_seconds": record.get("time_to_first_token_seconds"),
                "finish_reason": record.get("finish_reason"),
                "official_score": record.get("official_score"),
                "relaxed_extractable_correct": record.get("relaxed_extractable_correct"),
                "format_loss": record.get("format_loss"),
                "reasoning_error": record.get("reasoning_error"),
                "empty_or_invalid": record.get("empty_or_invalid"),
                "reasoning_only_output": record.get("reasoning_only_output"),
                "timeout": record.get("timeout"),
                "error_type": record.get("error_type"),
                "error_code": record.get("error_code"),
                "http_status": record.get("http_status"),
                "error_message_sanitized": record.get("error_message_sanitized"),
                "raw_response_preview": record.get("raw_response_preview"),
            }
        )
    return failures


def build_run_summary(
    *,
    records: list[dict[str, Any]],
    health_checks: list[dict[str, Any]],
    execute: bool,
) -> dict[str, Any]:
    return {
        "generated_at": create_timestamp(),
        "mode": "execute" if execute else "dry_run",
        "record_count": len(records),
        "health_check_count": len(health_checks),
        "group_summaries": summarize_records(records) if execute else [],
        "sample_summaries": build_sample_summaries(records) if execute else [],
        "health_check_summaries": summarize_health_checks(health_checks) if execute else [],
        "failure_cases_count": len(build_failure_cases(records)) if execute else 0,
        "failure_cases": build_failure_cases(records) if execute else [],
        **DIAGNOSTIC_FLAGS,
    }


def build_input_snapshot(
    *,
    provider_config: Any,
    backend_path: str,
    modes: list[str],
    layer_specs: list[PromptLayerSpec],
    sample_entries: list[dict[str, Any]],
    dataset_meta: dict[str, Any],
    timeout_values: list[int],
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
            "modes": modes,
            "prompt_layers": [layer.name for layer in layer_specs],
            "sample_ids": [entry["sample_id"] for entry in sample_entries],
            "timeout_values": timeout_values,
            "sleep_between_requests": sleep_between_requests,
            "max_retries": max_retries,
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
        "# Stage 4B MiMo timeout decomposition diagnostic 结果",
        "",
        "## 定位",
        "",
        "- 本报告只记录 MiMo 的 timeout / generation stability diagnostic。",
        "- 它不是 GEPA 结果。",
        "- 它不是 official_budget 结果。",
        "- 它不是 pilot。",
        "- 它不是 5-seed。",
        "- 它不是 MiMo vs GLM 排名。",
        "- 所有真实调用如果存在，都只允许解释为 diagnostic，不允许写成 performance claim。",
        "",
        "## 边界标记",
        "",
        f"- `model_called = {str(metadata['model_called']).lower()}`",
        f"- `api_called = {str(metadata['api_called']).lower()}`",
        f"- `new_experiment_executed = {str(metadata['new_experiment_executed']).lower()}`",
        "- `diagnostic_only = true`",
        "- `not_gepa_result = true`",
        "- `not_official_budget = true`",
        "- `not_performance_claim = true`",
        "",
        "## 请求计划",
        "",
        f"- provider：`{requested_execution['provider']}`",
        f"- backend path：`{requested_execution['backend_path']}`",
        f"- modes：`{', '.join(requested_execution['modes'])}`",
        f"- prompt layers：`{', '.join(requested_execution['prompt_layers'])}`",
        f"- sample ids：`{', '.join(requested_execution['sample_ids'])}`",
        f"- timeout values：`{', '.join(str(value) for value in requested_execution['timeout_values'])}`",
        f"- sleep_between_requests：`{requested_execution['sleep_between_requests']}` 秒",
        f"- max_retries：`{requested_execution['max_retries']}`",
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
                "- 本次报告只验证脚手架、参数边界、artifact schema 和报告边界。",
                "- health check：未执行；脚本已预留 pre / post health check 路径。",
                "",
                "## 计划覆盖",
                "",
                f"- planned_request_count：`{len(records)}`",
                f"- planned_health_check_count：`{len(health_checks)}`",
                "- 如果后续执行真实 diagnostic，必须先比较 health check，再解释 AIME timeout。",
                "",
                "## 待执行判读框架",
                "",
                "1. 如果 health check 失败，而 AIME 也失败，应优先归因为 provider / endpoint / key / 网络问题。",
                "2. 如果 health check 正常，但 AIME timeout，应继续区分首 token 前等待、首 token 后长生成、finish_reason=length、reasoning_only_output、prompt layer 差异与 sample 特异性。",
                "3. 如果 streaming 明显优于 non_streaming，只能写成 transport / return path 诊断现象，不能写成 strict path 已成功。",
                "4. 如果 strong_format 只减少 format_loss 而不减少 timeout，必须写成协议改善，不得写成 reasoning 改善。",
            ]
        )
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "- 当前状态：execute 已执行。",
            "- health check 已在每个 `mode @ timeout` 轮次前后执行。",
            "",
            "## health check 汇总",
            "",
            "| mode | timeout | check_count | ok_count | error_count | avg_latency_seconds |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for summary in run_summary["health_check_summaries"]:
        lines.append(
            f"| `{summary['mode']}` | {summary['timeout_setting']} | {summary['check_count']} | "
            f"{summary['ok_count']} | {summary['error_count']} | {summary['avg_latency_seconds']} |"
        )

    lines.extend(
        [
            "",
            "## 分组汇总",
            "",
            "| mode | prompt_layer | timeout | completed | timeout | rate_limit | provider_error | official | relaxed | avg_ttft | avg_latency |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for summary in run_summary["group_summaries"]:
        avg_ttft = "None" if summary["avg_time_to_first_token_seconds"] is None else summary["avg_time_to_first_token_seconds"]
        lines.append(
            f"| `{summary['mode']}` | `{summary['prompt_layer']}` | {summary['timeout_setting']} | "
            f"{summary['completed_count']} | {summary['timeout_count']} | {summary['rate_limit_count']} | "
            f"{summary['provider_error_count']} | {summary['official_score']} | {summary['relaxed_extractable_score']} | "
            f"{avg_ttft} | {summary['avg_latency_seconds']} |"
        )

    lines.extend(
        [
            "",
            "## 样本集中度",
            "",
            "| sample_id | completed | timeout | rate_limit | provider_error | first_token_missing |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for summary in run_summary["sample_summaries"]:
        lines.append(
            f"| `{summary['sample_id']}` | {summary['completed_count']} | {summary['timeout_count']} | "
            f"{summary['rate_limit_count']} | {summary['provider_error_count']} | {summary['first_token_missing_count']} |"
        )

    if run_summary["failure_cases"]:
        lines.extend(
            [
                "",
                "## failure cases",
                "",
                "| mode | prompt_layer | sample_id | timeout | first_token | finish_reason | diagnosis_hint | preview |",
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
                f"| `{record['mode']}` | `{record['prompt_layer']}` | `{record['sample_id']}` | "
                f"`{str(record['timeout']).lower()}` | `{str(record['first_token_observed']).lower()}` | "
                f"`{record['finish_reason']}` | `{diagnosis_hint}` | {record['raw_response_preview'] or '<empty>'} |"
            )

    lines.extend(
        [
            "",
            "## 结论边界",
            "",
            "- 可以写：timeout 是否与 timeout 设置、mode、prompt layer、sample_id、health check 结果相关。",
            "- 可以写：是否出现首 token 前等待过长、首 token 后长生成、reasoning_only_output、finish_reason=length。",
            "- 不可以写：MiMo 数学能力差。",
            "- 不可以写：output-protocol failure 就是 reasoning failure。",
            "- 不可以写：strict Stage 4B 已经成功或可以直接进入 GEPA。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    enforce_bounds(args)
    provider_config = build_provider_config(args)
    layer_specs = load_prompt_layers(args.prompt_layers)
    modes = load_modes(args.mode)
    timeout_values = load_timeout_values(args.timeout_values)
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
        modes=modes,
        layer_specs=layer_specs,
        sample_entries=sample_entries,
        dataset_meta=dataset_meta,
        timeout_values=timeout_values,
        sleep_between_requests=args.sleep_between_requests,
        max_retries=args.max_retries,
        run_dir=run_dir,
        execute=args.execute,
    )

    if args.execute:
        execution_result = execute_timeout_plan(
            provider_config=provider_config,
            backend_path=args.backend_path,
            modes=modes,
            layer_specs=layer_specs,
            sample_entries=sample_entries,
            timeout_values=timeout_values,
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
            modes=modes,
            layer_specs=layer_specs,
            sample_entries=sample_entries,
            timeout_values=timeout_values,
            sleep_between_requests=args.sleep_between_requests,
            max_retries=args.max_retries,
        )
        health_checks = build_dry_run_health_checks(
            provider_config=provider_config,
            backend_path=args.backend_path,
            modes=modes,
            timeout_values=timeout_values,
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
        "group_summaries": run_summary["group_summaries"],
        "sample_summaries": run_summary["sample_summaries"],
        "health_check_summaries": run_summary["health_check_summaries"],
        **DIAGNOSTIC_FLAGS,
    }

    write_json(run_dir / "input_snapshot.json", payload)
    BASE.write_jsonl(per_example_path, records)
    BASE.write_jsonl(health_check_path, health_checks)
    write_json(run_dir / "timeout_decomposition_results.json", results_payload)
    write_json(run_dir / "run_summary.json", run_summary)
    write_json(run_dir / "failure_cases.json", failure_cases)
    write_text(report_path, render_report(payload, records, health_checks, run_summary))


if __name__ == "__main__":
    main()
