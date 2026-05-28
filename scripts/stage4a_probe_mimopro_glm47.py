from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import APIStatusError, APITimeoutError, OpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.deepseek_utils import redact_secret
from src.logging_utils import create_run_dir, create_timestamp, write_json, write_text


try:
    import litellm
except Exception:  # pragma: no cover - 仅在依赖异常时触发
    litellm = None


DEFAULT_OUTPUT_DIR = "outputs/stage4a_provider_probe"
DEFAULT_REPORT_PATH = "reports/stage4a_provider_probe_result.md"
DEFAULT_TIMEOUT_SECONDS = 30.0

BACKEND_FAMILY_OPENAI_COMPATIBLE = "openai_compatible"

DIAGNOSTIC_FLAGS: dict[str, bool] = {
    "stage4a_provider_probe": True,
    "diagnostic_only": True,
    "not_gepa_result": True,
    "not_performance_claim": True,
    "no_gepa_optimize_called": True,
    "not_official_budget_baseline": True,
    "mechanism_diagnostic_only": True,
}


class Stage4AProbeError(RuntimeError):
    """Stage 4A provider probe 的配置或 artifact 不满足要求。"""


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    api_base: str
    api_key_env: str
    api_key: str
    model: str
    litellm_provider_string: str | None

    @property
    def api_base_present(self) -> bool:
        return bool(self.api_base.strip())

    @property
    def key_present(self) -> bool:
        return bool(self.api_key.strip())

    @property
    def model_present(self) -> bool:
        return bool(self.model.strip())

    @property
    def backend_family(self) -> str:
        return BACKEND_FAMILY_OPENAI_COMPATIBLE

    @property
    def effective_litellm_model(self) -> str:
        if self.litellm_provider_string:
            return self.litellm_provider_string.strip()
        normalized_model = self.model.strip()
        if normalized_model.startswith("openai/"):
            return normalized_model
        return f"openai/{normalized_model}"

    def missing_config_reasons(self) -> list[str]:
        reasons: list[str] = []
        if not self.api_base_present:
            reasons.append("missing api_base")
        if not self.key_present:
            reasons.append(f"missing credential env: {self.api_key_env}")
        if not self.model_present:
            reasons.append("missing model")
        return reasons


@dataclass(frozen=True)
class ProbeCase:
    probe_id: str
    prompt: str
    expected_exact: str
    expected_answer: str | None


PROBE_CASES: tuple[ProbeCase, ...] = (
    ProbeCase(
        probe_id="simple_ok",
        prompt="Return exactly: OK",
        expected_exact="OK",
        expected_answer=None,
    ),
    ProbeCase(
        probe_id="short_math",
        prompt="What is 19 + 23? Return only the final answer.",
        expected_exact="42",
        expected_answer="42",
    ),
    ProbeCase(
        probe_id="strong_format_micro",
        prompt="Solve 19 + 23. Your entire response must be exactly one line: ### N",
        expected_exact="### 42",
        expected_answer="42",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage 4A MiMo Pro vs GLM-4.7 provider probe。默认 dry-run，不调用模型。"
    )
    parser.add_argument(
        "--providers",
        nargs="+",
        choices=("mimo", "glm"),
        default=("mimo", "glm"),
        help="要检查的 provider 列表。",
    )
    parser.add_argument("--mimo-api-base", default=os.getenv("MIMO_API_BASE", ""), help="MiMo API base。")
    parser.add_argument("--mimo-api-key-env", default="MIMO_API_KEY", help="MiMo key 的环境变量名。")
    parser.add_argument("--mimo-model", default=os.getenv("MIMO_MODEL", ""), help="MiMo model id。")
    parser.add_argument(
        "--mimo-provider-string",
        default=None,
        help="MiMo 的可选 LiteLLM provider string；默认回退到 openai/<model>。",
    )
    parser.add_argument("--glm-api-base", default=os.getenv("GLM_API_BASE", ""), help="GLM API base。")
    parser.add_argument("--glm-api-key-env", default="GLM_API_KEY", help="GLM key 的环境变量名。")
    parser.add_argument("--glm-model", default=os.getenv("GLM_MODEL", ""), help="GLM model id。")
    parser.add_argument(
        "--glm-provider-string",
        default=None,
        help="GLM 的可选 LiteLLM provider string；默认回退到 openai/<model>。",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="单次 probe 超时秒数。",
    )
    parser.add_argument("--probe-raw-sdk", action="store_true", help="只显式启用 raw SDK 路径。")
    parser.add_argument("--probe-litellm", action="store_true", help="只显式启用 LiteLLM 路径。")
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="probe outputs 根目录；默认写入 outputs/stage4a_provider_probe。",
    )
    parser.add_argument(
        "--report-path",
        default=DEFAULT_REPORT_PATH,
        help="结果报告写入路径。",
    )
    parser.add_argument("--execute", action="store_true", help="显式执行真实 probe；默认只 dry-run。")
    return parser.parse_args()


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def sanitize_text(text: str | None, *, secrets: list[str], limit: int = 160) -> str:
    value = str(text or "")
    for secret in secrets:
        if secret:
            value = redact_secret(value, secret)
    project_root_text = str(PROJECT_ROOT.resolve())
    if project_root_text:
        value = value.replace(project_root_text, "<project_root>")
    value = normalize_space(value)
    if len(value) > limit:
        return value[: limit - 3] + "..."
    return value


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return to_jsonable(value.model_dump())
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            return to_jsonable(value.dict())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        return to_jsonable(vars(value))
    return str(value)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            json.dump(row, handle, ensure_ascii=False)
            handle.write("\n")


def load_required_artifacts(run_dir: Path) -> dict[str, Any]:
    required = (
        run_dir / "input_snapshot.json",
        run_dir / "probe_results.json",
        run_dir / "run_summary.json",
        run_dir / "failure_cases.json",
    )
    missing = [project_relative(path) for path in required if not path.exists()]
    if missing:
        raise Stage4AProbeError(f"缺少必需 artifact：{', '.join(missing)}")
    return {
        "input_snapshot": json.loads((run_dir / "input_snapshot.json").read_text(encoding="utf-8")),
        "probe_results": json.loads((run_dir / "probe_results.json").read_text(encoding="utf-8")),
        "run_summary": json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8")),
        "failure_cases": json.loads((run_dir / "failure_cases.json").read_text(encoding="utf-8")),
    }


def extract_relaxed_integer_answer(text: str) -> str | None:
    content = str(text or "").strip()
    if not content:
        return None

    patterns: tuple[str, ...] = (
        r"###\s*([+-]?\d+)",
        r"\\boxed\{([+-]?\d+)\}",
        r"(?i)final answer(?: is|:)?\s*([+-]?\d+)",
        r"(?i)answer is\s*([+-]?\d+)",
    )
    for pattern in patterns:
        matches = re.findall(pattern, content)
        if matches:
            return str(int(matches[-1]))

    plain = content.strip("` \t\r\n")
    if re.fullmatch(r"[+-]?\d+", plain):
        return str(int(plain))

    last_line = content.splitlines()[-1].strip()
    if re.fullmatch(r"[+-]?\d+", last_line):
        return str(int(last_line))
    return None


def classify_format_result(*, probe_case: ProbeCase, content: str) -> dict[str, Any]:
    normalized = str(content or "").strip()
    extracted = extract_relaxed_integer_answer(normalized)
    exact_match = normalized == probe_case.expected_exact

    if not normalized:
        category = "empty_or_invalid"
        format_loss = False
    elif exact_match:
        category = "exact_match"
        format_loss = False
    elif probe_case.expected_answer is not None and extracted == probe_case.expected_answer:
        category = "format_loss"
        format_loss = True
    else:
        category = "content_mismatch"
        format_loss = False

    return {
        "expected_exact": probe_case.expected_exact,
        "expected_answer": probe_case.expected_answer,
        "extracted_answer": extracted,
        "protocol_exact_match": exact_match,
        "format_loss": format_loss,
        "protocol_category": category,
    }


def resolve_probe_types(args: argparse.Namespace) -> list[str]:
    probe_types: list[str] = []
    if args.probe_raw_sdk:
        probe_types.append("raw_sdk")
    if args.probe_litellm:
        probe_types.append("litellm")
    if not probe_types:
        return ["raw_sdk", "litellm"]
    return probe_types


def build_provider_configs(args: argparse.Namespace) -> list[ProviderConfig]:
    selected = set(args.providers)
    configs: list[ProviderConfig] = []
    if "mimo" in selected:
        api_key = str(os.getenv(args.mimo_api_key_env) or "").strip()
        configs.append(
            ProviderConfig(
                provider="mimo",
                api_base=str(args.mimo_api_base or "").strip(),
                api_key_env=str(args.mimo_api_key_env),
                api_key=api_key,
                model=str(args.mimo_model or "").strip(),
                litellm_provider_string=(
                    str(args.mimo_provider_string).strip() if args.mimo_provider_string else None
                ),
            )
        )
    if "glm" in selected:
        api_key = str(os.getenv(args.glm_api_key_env) or "").strip()
        configs.append(
            ProviderConfig(
                provider="glm",
                api_base=str(args.glm_api_base or "").strip(),
                api_key_env=str(args.glm_api_key_env),
                api_key=api_key,
                model=str(args.glm_model or "").strip(),
                litellm_provider_string=(
                    str(args.glm_provider_string).strip() if args.glm_provider_string else None
                ),
            )
        )
    return configs


def build_input_snapshot(
    *,
    args: argparse.Namespace,
    provider_configs: list[ProviderConfig],
    probe_types: list[str],
    run_dir: Path,
) -> dict[str, Any]:
    return {
        "metadata": {
            "generated_at": create_timestamp(),
            "mode": "execute" if args.execute else "dry_run",
            "run_dir": project_relative(run_dir),
            "model_called": bool(args.execute),
            "api_called": bool(args.execute),
            "new_experiment_executed": bool(args.execute),
            **DIAGNOSTIC_FLAGS,
        },
        "requested_execution": {
            "providers": [config.provider for config in provider_configs],
            "probe_types": probe_types,
            "timeout_seconds": args.timeout,
            "execute": bool(args.execute),
        },
        "providers": [
            {
                "provider": config.provider,
                "api_base": config.api_base,
                "api_base_present": config.api_base_present,
                "api_key_env": config.api_key_env,
                "api_key_present": config.key_present,
                "model": config.model,
                "backend_family": config.backend_family,
                "litellm_provider_string": config.litellm_provider_string,
                "effective_litellm_model": (
                    config.effective_litellm_model if config.model_present else None
                ),
                "missing_config_reasons": config.missing_config_reasons(),
            }
            for config in provider_configs
        ],
        "probe_cases": [
            {
                "probe_id": case.probe_id,
                "prompt": case.prompt,
                "expected_exact": case.expected_exact,
                "expected_answer": case.expected_answer,
            }
            for case in PROBE_CASES
        ],
    }


def extract_message_content(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text_value = item.get("text")
                if text_value:
                    parts.append(str(text_value))
            else:
                text_value = getattr(item, "text", None)
                if text_value:
                    parts.append(str(text_value))
        return "\n".join(parts).strip()
    return str(content or "").strip()


def extract_reasoning_content_present(message: Any) -> bool:
    if message is None:
        return False
    candidate_fields = (
        "reasoning_content",
        "reasoning",
        "reasoning_text",
    )
    if isinstance(message, dict):
        return any(bool(message.get(field)) for field in candidate_fields)
    return any(bool(getattr(message, field, None)) for field in candidate_fields)


def extract_http_status_from_error(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def extract_error_message(exc: Exception, *, secrets: list[str]) -> tuple[str | None, str | None]:
    response = getattr(exc, "response", None)
    error_body = ""
    if response is not None:
        response_text = getattr(response, "text", None)
        if isinstance(response_text, str) and response_text:
            error_body = response_text
        elif callable(getattr(response, "json", None)):
            try:
                error_body = json.dumps(response.json(), ensure_ascii=False)
            except Exception:
                error_body = ""
    if isinstance(exc, APIStatusError) and getattr(exc, "body", None) is not None and not error_body:
        error_body = json.dumps(to_jsonable(exc.body), ensure_ascii=False)
    message = sanitize_text(str(exc), secrets=secrets, limit=240)
    body = sanitize_text(error_body, secrets=secrets, limit=240) if error_body else None
    return message or None, body


def is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, APITimeoutError)):
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    return "timeout" in text or "timed out" in text


def base_record(
    *,
    provider_config: ProviderConfig,
    probe_type: str,
    probe_case: ProbeCase,
) -> dict[str, Any]:
    return {
        "provider": provider_config.provider,
        "model": provider_config.model,
        "api_base_present": provider_config.api_base_present,
        "backend_family": provider_config.backend_family,
        "provider_string": (
            provider_config.effective_litellm_model if probe_type == "litellm" else None
        ),
        "probe_type": probe_type,
        "probe_prompt_id": probe_case.probe_id,
        "status": "pending",
        "http_status": None,
        "content_nonempty": False,
        "content_preview": "",
        "reasoning_content_present": False,
        "finish_reason": None,
        "latency_seconds": 0.0,
        "error_type": None,
        "error_message_sanitized": None,
        "error_body_sanitized": None,
        "timeout": False,
        "not_performance_claim": True,
        "no_gepa_optimize_called": True,
        "not_gepa_result": True,
    }


def save_raw_response_sample(
    *,
    run_dir: Path,
    record: dict[str, Any],
    raw_payload: dict[str, Any],
) -> str:
    raw_dir = run_dir / "raw_responses"
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_name = (
        f"{record['provider']}__{record['probe_type']}__{record['probe_prompt_id']}.json"
    )
    raw_path = raw_dir / file_name
    write_json(raw_path, raw_payload)
    return project_relative(raw_path)


def execute_raw_sdk_probe(
    *,
    provider_config: ProviderConfig,
    probe_case: ProbeCase,
    timeout_seconds: float,
    run_dir: Path,
) -> dict[str, Any]:
    record = base_record(provider_config=provider_config, probe_type="raw_sdk", probe_case=probe_case)
    if provider_config.missing_config_reasons():
        record["status"] = "config_missing"
        record["error_type"] = "ConfigMissing"
        record["error_message_sanitized"] = "; ".join(provider_config.missing_config_reasons())
        return record

    secrets = [provider_config.api_key]
    client = OpenAI(api_key=provider_config.api_key, base_url=provider_config.api_base)
    start_time = time.monotonic()
    try:
        raw_response = client.chat.completions.with_raw_response.create(
            model=provider_config.model,
            messages=[{"role": "user", "content": probe_case.prompt}],
            temperature=0,
            timeout=timeout_seconds,
        )
        completion = raw_response.parse()
        choice = completion.choices[0] if getattr(completion, "choices", None) else None
        message = getattr(choice, "message", None) if choice is not None else None
        content = extract_message_content(message)
        latency_seconds = round(time.monotonic() - start_time, 6)
        record.update(
            {
                "status": "ok" if content.strip() == probe_case.expected_exact else "content_mismatch",
                "http_status": getattr(raw_response, "status_code", None),
                "content_nonempty": bool(content.strip()),
                "content_preview": sanitize_text(content, secrets=secrets),
                "reasoning_content_present": extract_reasoning_content_present(message),
                "finish_reason": getattr(choice, "finish_reason", None),
                "latency_seconds": latency_seconds,
            }
        )
        record.update(classify_format_result(probe_case=probe_case, content=content))
        record["raw_response_path"] = save_raw_response_sample(
            run_dir=run_dir,
            record=record,
            raw_payload={
                "http_status": getattr(raw_response, "status_code", None),
                "completion": to_jsonable(completion),
            },
        )
        return record
    except Exception as exc:
        latency_seconds = round(time.monotonic() - start_time, 6)
        error_message, error_body = extract_error_message(exc, secrets=secrets)
        record.update(
            {
                "status": "timeout" if is_timeout_error(exc) else "error",
                "http_status": extract_http_status_from_error(exc),
                "latency_seconds": latency_seconds,
                "error_type": type(exc).__name__,
                "error_message_sanitized": error_message,
                "error_body_sanitized": error_body,
                "timeout": is_timeout_error(exc),
            }
        )
        record["raw_response_path"] = save_raw_response_sample(
            run_dir=run_dir,
            record=record,
            raw_payload={
                "error_type": type(exc).__name__,
                "error_message_sanitized": error_message,
                "error_body_sanitized": error_body,
            },
        )
        return record


def _extract_litellm_http_status(response: Any) -> int | None:
    hidden = getattr(response, "_hidden_params", None)
    if isinstance(hidden, dict):
        candidate = hidden.get("status_code") or hidden.get("http_status")
        if isinstance(candidate, int):
            return candidate
    return None


def execute_litellm_probe(
    *,
    provider_config: ProviderConfig,
    probe_case: ProbeCase,
    timeout_seconds: float,
    run_dir: Path,
) -> dict[str, Any]:
    record = base_record(provider_config=provider_config, probe_type="litellm", probe_case=probe_case)
    if provider_config.missing_config_reasons():
        record["status"] = "config_missing"
        record["error_type"] = "ConfigMissing"
        record["error_message_sanitized"] = "; ".join(provider_config.missing_config_reasons())
        return record
    if litellm is None:
        record["status"] = "error"
        record["error_type"] = "ImportError"
        record["error_message_sanitized"] = "litellm 未安装或导入失败。"
        return record

    secrets = [provider_config.api_key]
    start_time = time.monotonic()
    try:
        response = litellm.completion(
            model=provider_config.effective_litellm_model,
            messages=[{"role": "user", "content": probe_case.prompt}],
            api_key=provider_config.api_key,
            base_url=provider_config.api_base,
            timeout=timeout_seconds,
            temperature=0,
        )
        response_json = to_jsonable(response)
        choices = response_json.get("choices") if isinstance(response_json, dict) else None
        choice = choices[0] if choices else {}
        message = choice.get("message") if isinstance(choice, dict) else {}
        content = extract_message_content(message)
        latency_seconds = round(time.monotonic() - start_time, 6)
        record.update(
            {
                "status": "ok" if content.strip() == probe_case.expected_exact else "content_mismatch",
                "http_status": _extract_litellm_http_status(response),
                "content_nonempty": bool(content.strip()),
                "content_preview": sanitize_text(content, secrets=secrets),
                "reasoning_content_present": extract_reasoning_content_present(message),
                "finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
                "latency_seconds": latency_seconds,
            }
        )
        record.update(classify_format_result(probe_case=probe_case, content=content))
        record["raw_response_path"] = save_raw_response_sample(
            run_dir=run_dir,
            record=record,
            raw_payload={"completion": response_json},
        )
        return record
    except Exception as exc:
        latency_seconds = round(time.monotonic() - start_time, 6)
        error_message, error_body = extract_error_message(exc, secrets=secrets)
        record.update(
            {
                "status": "timeout" if is_timeout_error(exc) else "error",
                "http_status": extract_http_status_from_error(exc),
                "latency_seconds": latency_seconds,
                "error_type": type(exc).__name__,
                "error_message_sanitized": error_message,
                "error_body_sanitized": error_body,
                "timeout": is_timeout_error(exc),
            }
        )
        record["raw_response_path"] = save_raw_response_sample(
            run_dir=run_dir,
            record=record,
            raw_payload={
                "error_type": type(exc).__name__,
                "error_message_sanitized": error_message,
                "error_body_sanitized": error_body,
            },
        )
        return record


def build_dry_run_records(
    *,
    provider_configs: list[ProviderConfig],
    probe_types: list[str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for provider_config in provider_configs:
        for probe_type in probe_types:
            for probe_case in PROBE_CASES:
                record = base_record(
                    provider_config=provider_config,
                    probe_type=probe_type,
                    probe_case=probe_case,
                )
                record["status"] = "dry_run"
                if provider_config.missing_config_reasons():
                    record["error_type"] = "ConfigPreview"
                    record["error_message_sanitized"] = "; ".join(provider_config.missing_config_reasons())
                records.append(record)
    return records


def execute_probe_plan(
    *,
    provider_configs: list[ProviderConfig],
    probe_types: list[str],
    timeout_seconds: float,
    run_dir: Path,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for provider_config in provider_configs:
        for probe_type in probe_types:
            for probe_case in PROBE_CASES:
                if probe_type == "raw_sdk":
                    record = execute_raw_sdk_probe(
                        provider_config=provider_config,
                        probe_case=probe_case,
                        timeout_seconds=timeout_seconds,
                        run_dir=run_dir,
                    )
                else:
                    record = execute_litellm_probe(
                        provider_config=provider_config,
                        probe_case=probe_case,
                        timeout_seconds=timeout_seconds,
                        run_dir=run_dir,
                    )
                records.append(record)
    return records


def summarize_provider_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (str(record["provider"]), str(record["probe_type"]))
        grouped.setdefault(key, []).append(record)

    summaries: list[dict[str, Any]] = []
    for (provider, probe_type), group in sorted(grouped.items()):
        statuses = {str(item["status"]) for item in group}
        http_statuses = {item["http_status"] for item in group if item.get("http_status") is not None}
        any_content = any(bool(item.get("content_nonempty")) for item in group)
        any_timeout = any(bool(item.get("timeout")) for item in group)
        any_success = any(str(item["status"]) == "ok" for item in group)
        any_config_missing = any(str(item["status"]) == "config_missing" for item in group)

        if any_success:
            key_status = "valid"
        elif 401 in http_statuses or 403 in http_statuses:
            key_status = "invalid"
        elif any_config_missing:
            key_status = "unknown"
        else:
            key_status = "unknown"

        model_status = "unknown"
        if 404 in http_statuses:
            model_status = "unsupported"
        elif any_success or any_content:
            model_status = "supported"

        provider_reachable = any_success or any_content
        summaries.append(
            {
                "provider": provider,
                "probe_type": probe_type,
                "provider_reachable": provider_reachable,
                "key_status": key_status,
                "model_status": model_status,
                "content_returned": any_content,
                "timeout_observed": any_timeout,
                "status_distribution": {status: sum(item["status"] == status for item in group) for status in statuses},
                "http_statuses": sorted(http_statuses),
            }
        )
    return summaries


def compare_raw_sdk_and_litellm(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    comparison: list[dict[str, Any]] = []
    by_provider: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for record in records:
        by_provider.setdefault(str(record["provider"]), {}).setdefault(str(record["probe_type"]), []).append(record)

    for provider, mapping in sorted(by_provider.items()):
        raw_records = mapping.get("raw_sdk", [])
        litellm_records = mapping.get("litellm", [])
        if not raw_records and not litellm_records:
            continue
        if not raw_records or not litellm_records:
            comparison.append(
                {
                    "provider": provider,
                    "consistent": False,
                    "reason": "missing_one_path",
                }
            )
            continue
        consistent = True
        mismatches: list[str] = []
        for probe_case in PROBE_CASES:
            raw_record = next(item for item in raw_records if item["probe_prompt_id"] == probe_case.probe_id)
            litellm_record = next(item for item in litellm_records if item["probe_prompt_id"] == probe_case.probe_id)
            if bool(raw_record["content_nonempty"]) != bool(litellm_record["content_nonempty"]):
                consistent = False
                mismatches.append(f"{probe_case.probe_id}: content_nonempty")
            if bool(raw_record["timeout"]) != bool(litellm_record["timeout"]):
                consistent = False
                mismatches.append(f"{probe_case.probe_id}: timeout")
            if str(raw_record["status"]) == "ok" and str(litellm_record["status"]) != "ok":
                consistent = False
                mismatches.append(f"{probe_case.probe_id}: raw_ok_litellm_not_ok")
            if str(litellm_record["status"]) == "ok" and str(raw_record["status"]) != "ok":
                consistent = False
                mismatches.append(f"{probe_case.probe_id}: litellm_ok_raw_not_ok")
        comparison.append(
            {
                "provider": provider,
                "consistent": consistent,
                "reason": "all_checked" if consistent else "; ".join(mismatches),
            }
        )
    return comparison


def build_run_summary(
    *,
    records: list[dict[str, Any]],
    execute: bool,
) -> dict[str, Any]:
    failures = [
        {
            "provider": record["provider"],
            "model": record["model"],
            "probe_type": record["probe_type"],
            "probe_prompt_id": record["probe_prompt_id"],
            "status": record["status"],
            "error_type": record.get("error_type"),
            "finish_reason": record.get("finish_reason"),
            "content_nonempty": record.get("content_nonempty"),
            "extracted_answer": record.get("extracted_answer"),
            "protocol_category": record.get("protocol_category"),
            "http_status": record.get("http_status"),
        }
        for record in records
        if record["status"] not in {"ok", "dry_run"}
    ]
    return {
        "generated_at": create_timestamp(),
        "mode": "execute" if execute else "dry_run",
        "record_count": len(records),
        "provider_path_summaries": summarize_provider_records(records),
        "raw_sdk_vs_litellm": compare_raw_sdk_and_litellm(records),
        "failure_cases_count": len(failures),
        "failure_cases": failures,
        **DIAGNOSTIC_FLAGS,
    }


def render_report(
    *,
    input_snapshot: dict[str, Any],
    records: list[dict[str, Any]],
    run_summary: dict[str, Any],
) -> str:
    metadata = input_snapshot["metadata"]
    lines = [
        "# Stage 4A MiMo Pro vs GLM-4.7 provider probe 结果",
        "",
        "## 定位",
        "",
        "- 本报告只记录 Stage 4A provider probe 的连通性与最小生成诊断。",
        "- 它不是 GEPA 实验。",
        "- 它不是 official_budget continuation。",
        "- 它不是 5-seed、多样本性能对比或模型排行榜。",
        "- 结论只允许停留在 reachable / content returned / timeout / path consistency 这些层级。",
        "",
        "## 边界标识",
        "",
    ]
    for key, value in metadata.items():
        if isinstance(value, bool):
            lines.append(f"- `{key} = {str(value).lower()}`")

    lines.extend(["", "## 执行状态", ""])
    if metadata["mode"] == "dry_run":
        lines.extend(
            [
                "- 当前状态：dry-run。",
                "- 本次未调用模型。",
                "- 本次未调用 GEPA。",
                "- 本次未运行新实验。",
                "",
                "## 计划检查矩阵",
                "",
                "| provider | path | probe | status | 备注 |",
                "|---|---|---|---|---|",
            ]
        )
        for record in records:
            note = record.get("error_message_sanitized") or "ready"
            lines.append(
                f"| `{record['provider']}` | `{record['probe_type']}` | `{record['probe_prompt_id']}` | "
                f"`{record['status']}` | {note} |"
            )
        lines.extend(
            [
                "",
                "## dry-run 结论",
                "",
                "- 当前只能判断配置是否齐全，不能判断 key 是否有效、模型是否支持或 provider 是否 reachable。",
                "- 若后续执行真实 probe，报告只应写 reachable / not reachable、content returned / empty、timeout / no timeout、raw SDK 与 LiteLLM 是否一致。",
                "- 当前不允许写任何 MiMo 与 GLM 的性能高低结论。",
            ]
        )
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "- 当前状态：execute 已执行。",
            "- 本报告只汇总最小 probe，不做数学能力结论。",
            "",
            "## provider / path 汇总",
            "",
            "| provider | path | reachable | key | model | content | timeout |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for summary in run_summary["provider_path_summaries"]:
        lines.append(
            f"| `{summary['provider']}` | `{summary['probe_type']}` | "
            f"`{'reachable' if summary['provider_reachable'] else 'not reachable'}` | "
            f"`{summary['key_status']}` | `{summary['model_status']}` | "
            f"`{'returned' if summary['content_returned'] else 'empty'}` | "
            f"`{'timeout' if summary['timeout_observed'] else 'no timeout'}` |"
        )

    lines.extend(
        [
            "",
            "## 逐条 probe 摘要",
            "",
            "| provider | path | probe | status | finish_reason | content_preview |",
            "|---|---|---|---|---|---|",
        ]
    )
    for record in records:
        lines.append(
            f"| `{record['provider']}` | `{record['probe_type']}` | `{record['probe_prompt_id']}` | "
            f"`{record['status']}` | `{record.get('finish_reason')}` | {record.get('content_preview') or '-'} |"
        )

    lines.extend(["", "## raw SDK vs LiteLLM 一致性", ""])
    for comparison in run_summary["raw_sdk_vs_litellm"]:
        label = "一致" if comparison["consistent"] else "不一致"
        lines.append(f"- `{comparison['provider']}`：{label}（{comparison['reason']}）")

    if run_summary["failure_cases"]:
        lines.extend(
            [
                "",
                "## failure-mode table",
                "",
                "| provider | path | probe | error_type | finish_reason | content_nonempty | extracted_answer | diagnosis |",
                "|---|---|---|---|---|---|---|---|",
            ]
        )
        for failure in run_summary["failure_cases"]:
            diagnosis = failure["protocol_category"] or failure["status"]
            lines.append(
                f"| `{failure['provider']}` | `{failure['probe_type']}` | `{failure['probe_prompt_id']}` | "
                f"`{failure['error_type']}` | `{failure['finish_reason']}` | "
                f"`{str(bool(failure['content_nonempty'])).lower()}` | `{failure['extracted_answer']}` | `{diagnosis}` |"
            )

    lines.extend(
        [
            "",
            "## 结论边界",
            "",
            "- 可以写：provider reachable / not reachable。",
            "- 可以写：key valid / invalid / unknown。",
            "- 可以写：model supported / unsupported / unknown。",
            "- 可以写：content returned / empty。",
            "- 可以写：timeout / no timeout。",
            "- 可以写：raw SDK 与 LiteLLM 是否一致。",
            "- 不能写：MiMo 比 GLM 强。",
            "- 不能写：GLM 比 MiMo 强。",
            "- 不能写：可以直接进入 GEPA official_budget。",
            "- 不能写：数学能力已经得到结论。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    if args.timeout <= 0:
        raise Stage4AProbeError("--timeout 必须大于 0。")

    provider_configs = build_provider_configs(args)
    probe_types = resolve_probe_types(args)
    output_dir = (PROJECT_ROOT / args.output_dir).resolve()
    run_dir = create_run_dir(output_dir)
    report_path = (PROJECT_ROOT / args.report_path).resolve()

    input_snapshot = build_input_snapshot(
        args=args,
        provider_configs=provider_configs,
        probe_types=probe_types,
        run_dir=run_dir,
    )
    write_json(run_dir / "input_snapshot.json", input_snapshot)

    if args.execute:
        records = execute_probe_plan(
            provider_configs=provider_configs,
            probe_types=probe_types,
            timeout_seconds=args.timeout,
            run_dir=run_dir,
        )
    else:
        records = build_dry_run_records(provider_configs=provider_configs, probe_types=probe_types)

    write_json(run_dir / "probe_results.json", {"records": records, **DIAGNOSTIC_FLAGS})
    write_jsonl(run_dir / "per_example_eval.jsonl", records)

    run_summary = build_run_summary(records=records, execute=args.execute)
    failure_cases = run_summary["failure_cases"]

    write_json(run_dir / "run_summary.json", run_summary)
    write_json(run_dir / "failure_cases.json", failure_cases)

    report_text = render_report(
        input_snapshot=input_snapshot,
        records=records,
        run_summary=run_summary,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_text(report_path, report_text)

    print(f"[DONE] Stage 4A provider probe {'execute' if args.execute else 'dry-run'} 完成")
    print(f"run_dir: {project_relative(run_dir)}")
    print(f"report: {project_relative(report_path)}")


if __name__ == "__main__":
    main()
