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
from src.logging_utils import create_run_dir, create_timestamp, write_json, write_text, write_yaml


try:
    import litellm
except Exception:  # pragma: no cover - 仅在依赖异常时触发
    litellm = None


DEFAULT_OUTPUT_DIR = "outputs/stage4b_fixed_prompt_aime_baseline"
DEFAULT_REPORT_PATH = "reports/stage4b_fixed_prompt_aime_baseline_result.md"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_LIMIT = 30
BACKEND_FAMILY_OPENAI_COMPATIBLE = "openai_compatible"

DIAGNOSTIC_FLAGS: dict[str, bool] = {
    "stage4b_fixed_prompt_baseline": True,
    "diagnostic_only": True,
    "not_gepa_result": True,
    "not_official_budget_baseline": True,
    "not_final_performance_claim": True,
    "not_performance_claim": True,
    "mechanism_diagnostic_only": True,
    "no_gepa_optimize_called": True,
}

PROMPTS: dict[str, str] = {
    "original_seed_prompt": (
        "You are a helpful assistant. Answer the question. "
        "Put your final answer in the format '### <answer>'"
    ),
    "strong_format_seed_prompt": "\n".join(
        [
            "Solve the problem.",
            "Your final answer must be exactly one line in this format:",
            "### N",
            "where N is the final integer answer.",
            "Do not use \\boxed{}.",
            "Do not use XML tags.",
            'Do not write "Final answer:".',
            "Do not write the final answer in any other format.",
        ]
    ),
}


class Stage4BError(RuntimeError):
    """Stage 4B fixed-prompt diagnostic 的配置或 artifact 不满足要求。"""


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
        normalized = self.model.strip()
        if normalized.startswith("openai/"):
            return normalized
        return f"openai/{normalized}"

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
class PromptSpec:
    name: str
    system_prompt: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage 4B MiMo Pro vs GLM-4.7 fixed-prompt AIME diagnostic。默认 dry-run，不调用模型。"
    )
    parser.add_argument(
        "--providers",
        nargs="+",
        choices=("mimo", "glm"),
        default=("mimo", "glm"),
        help="要评估的 provider 列表。",
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
        "--backend-path",
        choices=("raw_sdk", "litellm"),
        default="raw_sdk",
        help="Stage 4B 执行路径；默认 raw_sdk。Stage 4A 已负责双路径连通性 gate。",
    )
    parser.add_argument(
        "--prompt-variant",
        action="append",
        choices=tuple(PROMPTS.keys()),
        help="只执行指定 prompt variant；可重复传入。默认执行两个 prompt。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="AIME fixed subset 样本数。默认 30，当前禁止扩大到 150。",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="单样本请求超时秒数。",
    )
    parser.add_argument("--max-retries", type=int, default=0, help="单样本最大重试次数。")
    parser.add_argument(
        "--retry-sleep-seconds",
        type=float,
        default=2.0,
        help="单样本重试等待秒数。",
    )
    parser.add_argument("--resume", action="store_true", help="复用已有 per_example_eval.jsonl 成功记录。")
    parser.add_argument("--run-dir", default=None, help="复用已有运行目录；默认创建新目录。")
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="outputs 根目录；默认写入 outputs/stage4b_fixed_prompt_aime_baseline。",
    )
    parser.add_argument(
        "--report-path",
        default=DEFAULT_REPORT_PATH,
        help="结果报告写入路径。",
    )
    parser.add_argument("--execute", action="store_true", help="显式执行真实 30-sample 诊断；默认只 dry-run。")
    return parser.parse_args()


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def sanitize_text(text: str | None, *, secrets: list[str], limit: int = 200) -> str:
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


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            json.dump(row, handle, ensure_ascii=False)
            handle.write("\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise Stage4BError(f"JSONL 解析失败：{project_relative(path)} 第 {line_number} 行：{exc}") from exc
            if not isinstance(payload, dict):
                raise Stage4BError(f"JSONL 记录必须是对象：{project_relative(path)} 第 {line_number} 行")
            rows.append(payload)
    return rows


def normalize_answer(value: str) -> str:
    text = str(value).strip()
    text = text.strip("` \t\r\n.,;:。")
    text = text.replace(",", "")
    if re.fullmatch(r"[+-]?\d+", text):
        return str(int(text))
    return text


def extract_gold_answer(gold: str) -> str:
    match = re.search(r"###\s*([^\n\r]+)", str(gold))
    if not match:
        raise Stage4BError(f"无法从 gold 中提取 `###` 答案：{gold!r}")
    return normalize_answer(match.group(1))


def extract_relaxed_integer_answer(text: str) -> str | None:
    content = str(text or "").strip()
    if not content:
        return None
    patterns: tuple[str, ...] = (
        r"###\s*([+-]?\d+)",
        r"\\boxed\{([+-]?\d+)\}",
        r"(?i)final answer(?: is|:)?\s*([+-]?\d+)",
        r"(?i)answer is\s*([+-]?\d+)",
        r"^\s*([+-]?\d+)\s*$",
    )
    for pattern in patterns:
        matches = re.findall(pattern, content)
        if matches:
            return normalize_answer(matches[-1])
    return None


def slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value)).strip("_") or "item"


def extract_message_content(message: Any) -> str:
    if message is None:
        return ""
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    parts.append(text_value)
        return "".join(parts)
    return str(content or "")


def extract_reasoning_content_present(message: Any) -> bool:
    if message is None:
        return False
    if isinstance(message, dict):
        if message.get("reasoning_content"):
            return True
        content = message.get("content")
        if isinstance(content, list):
            return any(
                isinstance(item, dict) and str(item.get("type", "")).lower().startswith("reason")
                for item in content
            )
        return False
    reasoning_content = getattr(message, "reasoning_content", None)
    if reasoning_content:
        return True
    content = getattr(message, "content", None)
    if isinstance(content, list):
        return any(
            isinstance(item, dict) and str(item.get("type", "")).lower().startswith("reason")
            for item in content
        )
    return False


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


def enforce_stage4b_limit(limit: int) -> None:
    if limit <= 0:
        raise Stage4BError("--limit 必须是大于 0 的整数。")
    if limit > DEFAULT_LIMIT:
        raise Stage4BError("Stage 4B 当前只允许 30-sample fixed-prompt diagnostic，禁止直接扩大到 150。")


def load_prompt_specs(selected_prompt_variants: list[str] | None = None) -> list[PromptSpec]:
    selected = selected_prompt_variants or list(PROMPTS.keys())
    unknown = sorted(set(selected) - set(PROMPTS))
    if unknown:
        raise Stage4BError(f"未知 prompt variant：{', '.join(unknown)}")
    return [PromptSpec(name=name, system_prompt=PROMPTS[name]) for name in selected]


def build_provider_configs(args: argparse.Namespace) -> list[ProviderConfig]:
    selected = list(dict.fromkeys(str(item) for item in args.providers))
    providers: list[ProviderConfig] = []
    if "mimo" in selected:
        key = str(os.getenv(args.mimo_api_key_env) or "").strip()
        providers.append(
            ProviderConfig(
                provider="mimo",
                api_base=str(args.mimo_api_base or "").strip(),
                api_key_env=str(args.mimo_api_key_env),
                api_key=key,
                model=str(args.mimo_model or "").strip(),
                litellm_provider_string=(
                    str(args.mimo_provider_string).strip() if args.mimo_provider_string else None
                ),
            )
        )
    if "glm" in selected:
        key = str(os.getenv(args.glm_api_key_env) or "").strip()
        providers.append(
            ProviderConfig(
                provider="glm",
                api_base=str(args.glm_api_base or "").strip(),
                api_key_env=str(args.glm_api_key_env),
                api_key=key,
                model=str(args.glm_model or "").strip(),
                litellm_provider_string=(
                    str(args.glm_provider_string).strip() if args.glm_provider_string else None
                ),
            )
        )
    return providers


def load_official_dataset_for_execute(limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from src.gepa_official_runner import load_official_aime_dataset

    _, valset, testset, dataset_source, adaptation_notes = load_official_aime_dataset()
    if testset is not None:
        split_name = "test"
        split_label = "official test split"
        source_dataset = list(testset)
    else:
        split_name = "val"
        split_label = "validation fallback"
        source_dataset = list(valset)
    dataset = source_dataset[:limit]
    return dataset, {
        "split": split_name,
        "split_label": split_label,
        "dataset_source": dataset_source,
        "adaptation_notes": list(adaptation_notes),
        "available_source_count": len(source_dataset),
        "selected_count": len(dataset),
        "subset_selector": f"first_{limit}_items",
    }


def build_sample_id(sample: dict[str, Any], split_name: str, sample_index: int) -> str:
    return str(sample.get("sample_id") or sample.get("id") or f"{split_name}-{sample_index}")


def build_input_snapshot(
    *,
    provider_configs: list[ProviderConfig],
    prompt_specs: list[PromptSpec],
    backend_path: str,
    limit: int,
    timeout_seconds: float,
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
            "official_score_semantics": "contains_gold_substring",
            **DIAGNOSTIC_FLAGS,
        },
        "requested_execution": {
            "providers": [provider.provider for provider in provider_configs],
            "backend_path": backend_path,
            "limit": limit,
            "timeout_seconds": timeout_seconds,
            "prompt_variants": [prompt.name for prompt in prompt_specs],
            "dataset_plan": "official test split if available, else validation fallback",
        },
        "provider_configs": [
            {
                "provider": provider.provider,
                "model": provider.model,
                "api_base_present": provider.api_base_present,
                "backend_family": provider.backend_family,
                "provider_string": (
                    provider.effective_litellm_model if backend_path == "litellm" else None
                ),
                "missing_config_reasons": provider.missing_config_reasons(),
            }
            for provider in provider_configs
        ],
        "prompt_specs": [
            {
                "prompt_variant": prompt.name,
                "prompt_chars": len(prompt.system_prompt),
                "prompt_words": len(prompt.system_prompt.split()),
                "prompt_lines": len(prompt.system_prompt.splitlines()),
                "system_prompt": prompt.system_prompt,
            }
            for prompt in prompt_specs
        ],
    }


def build_record_key(record: dict[str, Any]) -> str:
    return "::".join(
        [
            str(record.get("provider")),
            str(record.get("backend_path")),
            str(record.get("prompt_variant")),
            str(record.get("sample_id")),
        ]
    )


def normalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        latest[build_record_key(record)] = record
    return list(latest.values())


def load_required_artifacts(run_dir: Path) -> dict[str, Any]:
    required = (
        run_dir / "input_snapshot.json",
        run_dir / "fixed_prompt_results.json",
        run_dir / "per_example_eval.jsonl",
        run_dir / "run_summary.json",
        run_dir / "failure_cases.json",
    )
    missing = [project_relative(path) for path in required if not path.exists()]
    if missing:
        raise Stage4BError(f"缺少必需 artifact：{', '.join(missing)}")
    return {
        "input_snapshot": json.loads((run_dir / "input_snapshot.json").read_text(encoding="utf-8")),
        "fixed_prompt_results": json.loads((run_dir / "fixed_prompt_results.json").read_text(encoding="utf-8")),
        "per_example_eval": read_jsonl(run_dir / "per_example_eval.jsonl"),
        "run_summary": json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8")),
        "failure_cases": json.loads((run_dir / "failure_cases.json").read_text(encoding="utf-8")),
    }


def classify_prediction(*, content: str, gold: str) -> dict[str, Any]:
    gold_answer = extract_gold_answer(gold)
    official_correct = gold in content
    extracted_answer = extract_relaxed_integer_answer(content)
    extracted_correct = extracted_answer == gold_answer if extracted_answer is not None else False
    if official_correct:
        diagnosis = "official_correct"
    elif extracted_correct:
        diagnosis = "format_loss"
    elif extracted_answer is None:
        diagnosis = "empty_or_invalid"
    else:
        diagnosis = "reasoning_error"
    return {
        "gold_answer": gold_answer,
        "official_score": 1.0 if official_correct else 0.0,
        "official_correct": official_correct,
        "relaxed_extractable_correct": official_correct or extracted_correct,
        "extracted_answer": extracted_answer,
        "format_loss": diagnosis == "format_loss",
        "reasoning_error": diagnosis == "reasoning_error",
        "empty_or_invalid": diagnosis == "empty_or_invalid",
        "diagnosis": diagnosis,
    }


def base_record(
    *,
    provider_config: ProviderConfig,
    backend_path: str,
    prompt_spec: PromptSpec,
    sample_id: str,
    gold: str,
) -> dict[str, Any]:
    return {
        "provider": provider_config.provider,
        "model": provider_config.model,
        "api_base_present": provider_config.api_base_present,
        "backend_family": provider_config.backend_family,
        "provider_string": (
            provider_config.effective_litellm_model if backend_path == "litellm" else None
        ),
        "backend_path": backend_path,
        "prompt_variant": prompt_spec.name,
        "sample_id": sample_id,
        "gold": gold,
        "official_score": 0.0,
        "relaxed_extractable_correct": False,
        "extracted_answer": None,
        "format_loss": False,
        "reasoning_error": False,
        "empty_or_invalid": False,
        "raw_response_preview": "",
        "full_response_path": None,
        "finish_reason": None,
        "latency_seconds": 0.0,
        "timeout": False,
        "error_type": None,
        "error_message_sanitized": None,
        "error_body_sanitized": None,
        "http_status": None,
        "content_nonempty": False,
        "reasoning_content_present": False,
        "request_completed": False,
        "diagnosis": None,
        "not_gepa_result": True,
        "not_performance_claim": True,
    }


def save_full_response(
    *,
    run_dir: Path,
    record: dict[str, Any],
    payload: dict[str, Any],
) -> str:
    raw_dir = run_dir / "raw_responses"
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_name = "__".join(
        [
            slugify(record["provider"]),
            slugify(record["backend_path"]),
            slugify(record["prompt_variant"]),
            slugify(record["sample_id"]),
        ]
    )
    raw_path = raw_dir / f"{file_name}.json"
    write_json(raw_path, payload)
    return project_relative(raw_path)


def _extract_litellm_http_status(response: Any) -> int | None:
    hidden = getattr(response, "_hidden_params", None)
    if isinstance(hidden, dict):
        candidate = hidden.get("status_code") or hidden.get("http_status")
        if isinstance(candidate, int):
            return candidate
    return None


def _execute_raw_sdk_request(
    *,
    provider_config: ProviderConfig,
    prompt_spec: PromptSpec,
    question: str,
    timeout_seconds: float,
) -> tuple[Any, Any, str, int | None]:
    # 诊断超时必须对应单次请求预算，不能被 SDK 默认重试放大。
    client = OpenAI(
        api_key=provider_config.api_key,
        base_url=provider_config.api_base,
        timeout=timeout_seconds,
        max_retries=0,
    )
    raw_response = client.chat.completions.with_raw_response.create(
        model=provider_config.model,
        messages=[
            {"role": "system", "content": prompt_spec.system_prompt},
            {"role": "user", "content": question},
        ],
        temperature=0,
        timeout=timeout_seconds,
    )
    completion = raw_response.parse()
    choice = completion.choices[0] if getattr(completion, "choices", None) else None
    message = getattr(choice, "message", None) if choice is not None else None
    return completion, message, getattr(choice, "finish_reason", None), getattr(raw_response, "status_code", None)


def _execute_litellm_request(
    *,
    provider_config: ProviderConfig,
    prompt_spec: PromptSpec,
    question: str,
    timeout_seconds: float,
) -> tuple[Any, Any, str | None, int | None]:
    if litellm is None:
        raise ImportError("litellm 未安装或导入失败。")
    response = litellm.completion(
        model=provider_config.effective_litellm_model,
        messages=[
            {"role": "system", "content": prompt_spec.system_prompt},
            {"role": "user", "content": question},
        ],
        api_key=provider_config.api_key,
        base_url=provider_config.api_base,
        timeout=timeout_seconds,
        temperature=0,
    )
    response_json = to_jsonable(response)
    choices = response_json.get("choices") if isinstance(response_json, dict) else None
    choice = choices[0] if choices else {}
    message = choice.get("message") if isinstance(choice, dict) else {}
    finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
    return response_json, message, finish_reason, _extract_litellm_http_status(response)


def execute_sample(
    *,
    provider_config: ProviderConfig,
    backend_path: str,
    prompt_spec: PromptSpec,
    sample: dict[str, Any],
    split_name: str,
    sample_index: int,
    timeout_seconds: float,
    run_dir: Path,
    max_retries: int,
    retry_sleep_seconds: float,
) -> dict[str, Any]:
    sample_id = build_sample_id(sample, split_name, sample_index)
    gold = str(sample.get("answer") or "")
    question = str(sample.get("input") or "")
    record = base_record(
        provider_config=provider_config,
        backend_path=backend_path,
        prompt_spec=prompt_spec,
        sample_id=sample_id,
        gold=gold,
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
            }
        )
        return record

    secrets = [provider_config.api_key]
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        start_time = time.monotonic()
        try:
            if backend_path == "raw_sdk":
                raw_payload, message, finish_reason, http_status = _execute_raw_sdk_request(
                    provider_config=provider_config,
                    prompt_spec=prompt_spec,
                    question=question,
                    timeout_seconds=timeout_seconds,
                )
                raw_artifact = {"http_status": http_status, "completion": to_jsonable(raw_payload)}
            else:
                raw_payload, message, finish_reason, http_status = _execute_litellm_request(
                    provider_config=provider_config,
                    prompt_spec=prompt_spec,
                    question=question,
                    timeout_seconds=timeout_seconds,
                )
                raw_artifact = {"http_status": http_status, "completion": raw_payload}

            content = extract_message_content(message)
            latency_seconds = round(time.monotonic() - start_time, 6)
            record.update(
                {
                    "status": "ok",
                    "request_completed": True,
                    "http_status": http_status,
                    "content_nonempty": bool(content.strip()),
                    "raw_response_preview": sanitize_text(content, secrets=secrets, limit=240),
                    "reasoning_content_present": extract_reasoning_content_present(message),
                    "finish_reason": finish_reason,
                    "latency_seconds": latency_seconds,
                }
            )
            record.update(classify_prediction(content=content, gold=gold))
            record["full_response_path"] = save_full_response(
                run_dir=run_dir,
                record=record,
                payload={
                    "provider": provider_config.provider,
                    "backend_path": backend_path,
                    "prompt_variant": prompt_spec.name,
                    "sample_id": sample_id,
                    "question": question,
                    "gold": gold,
                    "content": content,
                    "reasoning_content_present": record["reasoning_content_present"],
                    "finish_reason": finish_reason,
                    "http_status": http_status,
                    "raw_payload": raw_artifact,
                },
            )
            return record
        except Exception as exc:  # pragma: no cover - 真实 provider 异常路径由单元测试覆盖分类
            last_exc = exc
            if attempt < max_retries and retry_sleep_seconds > 0:
                time.sleep(retry_sleep_seconds)
                continue
            latency_seconds = round(time.monotonic() - start_time, 6)
            error_message, error_body = extract_error_message(exc, secrets=secrets)
            timeout = is_timeout_error(exc)
            record.update(
                {
                    "status": "timeout" if timeout else "error",
                    "latency_seconds": latency_seconds,
                    "timeout": timeout,
                    "empty_or_invalid": True,
                    "error_type": type(exc).__name__,
                    "error_message_sanitized": error_message,
                    "error_body_sanitized": error_body,
                    "http_status": extract_http_status_from_error(exc),
                    "diagnosis": "timeout" if timeout else "provider_error",
                }
            )
            record["full_response_path"] = save_full_response(
                run_dir=run_dir,
                record=record,
                payload={
                    "provider": provider_config.provider,
                    "backend_path": backend_path,
                    "prompt_variant": prompt_spec.name,
                    "sample_id": sample_id,
                    "gold": gold,
                    "error_type": type(exc).__name__,
                    "error_message_sanitized": error_message,
                    "error_body_sanitized": error_body,
                },
            )
            return record
    if last_exc is not None:
        raise last_exc
    raise AssertionError("不可达分支")


def summarize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (
            str(record["provider"]),
            str(record["model"]),
            str(record["backend_path"]),
            str(record["prompt_variant"]),
        )
        grouped.setdefault(key, []).append(record)

    summaries: list[dict[str, Any]] = []
    for (provider, model, backend_path, prompt_variant), group in sorted(grouped.items()):
        total = len(group)
        completed_count = sum(bool(item.get("request_completed")) for item in group)
        official_score = round(sum(float(item.get("official_score", 0.0)) for item in group) / total, 12)
        relaxed_score = round(
            sum(1.0 if item.get("relaxed_extractable_correct") else 0.0 for item in group) / total,
            12,
        )
        finish_reason_distribution: dict[str, int] = {}
        for item in group:
            finish_reason = str(item.get("finish_reason") or "null")
            finish_reason_distribution[finish_reason] = finish_reason_distribution.get(finish_reason, 0) + 1
        summaries.append(
            {
                "provider": provider,
                "model": model,
                "backend_path": backend_path,
                "prompt_variant": prompt_variant,
                "completed_count": completed_count,
                "sample_count": total,
                "official_score": official_score,
                "relaxed_extractable_score": relaxed_score,
                "official_minus_relaxed_gap": round(official_score - relaxed_score, 12),
                "format_loss_count": sum(bool(item.get("format_loss")) for item in group),
                "reasoning_error_count": sum(bool(item.get("reasoning_error")) for item in group),
                "empty_or_invalid_count": sum(bool(item.get("empty_or_invalid")) for item in group),
                "timeout_count": sum(bool(item.get("timeout")) for item in group),
                "error_total": sum(str(item.get("status")) in {"timeout", "error", "config_missing"} for item in group),
                "avg_latency_seconds": round(
                    (
                        sum(float(item.get("latency_seconds", 0.0)) for item in group if item.get("request_completed"))
                        / completed_count
                    )
                    if completed_count
                    else 0.0,
                    6,
                ),
                "finish_reason_distribution": finish_reason_distribution,
                **DIAGNOSTIC_FLAGS,
            }
        )
    return summaries


def build_failure_cases(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for record in records:
        if (
            str(record.get("status")) == "ok"
            and not record.get("format_loss")
            and not record.get("reasoning_error")
            and not record.get("empty_or_invalid")
        ):
            continue
        failures.append(
            {
                "provider": record["provider"],
                "model": record["model"],
                "backend_path": record["backend_path"],
                "prompt_variant": record["prompt_variant"],
                "sample_id": record["sample_id"],
                "error_type": record.get("error_type"),
                "finish_reason": record.get("finish_reason"),
                "content_nonempty": record.get("content_nonempty"),
                "extracted_answer": record.get("extracted_answer"),
                "official_score": record.get("official_score"),
                "relaxed_correct": record.get("relaxed_extractable_correct"),
                "diagnosis": record.get("diagnosis"),
            }
        )
    return failures


def build_run_summary(*, records: list[dict[str, Any]], execute: bool) -> dict[str, Any]:
    failures = build_failure_cases(records) if execute else []
    return {
        "generated_at": create_timestamp(),
        "mode": "execute" if execute else "dry_run",
        "record_count": len(records),
        "group_summaries": summarize_records(records) if execute else [],
        "failure_cases_count": len(failures),
        "failure_cases": failures,
        **DIAGNOSTIC_FLAGS,
    }


def build_dry_run_records(
    *,
    provider_configs: list[ProviderConfig],
    prompt_specs: list[PromptSpec],
    backend_path: str,
    limit: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for provider_config in provider_configs:
        missing = provider_config.missing_config_reasons()
        for prompt_spec in prompt_specs:
            for sample_index in range(1, limit + 1):
                record = base_record(
                    provider_config=provider_config,
                    backend_path=backend_path,
                    prompt_spec=prompt_spec,
                    sample_id=f"planned-{sample_index}",
                    gold="### <gold>",
                )
                record.update(
                    {
                        "status": "dry_run",
                        "error_type": "ConfigPreview" if missing else None,
                        "error_message_sanitized": "; ".join(missing) if missing else None,
                        "diagnosis": "config_missing" if missing else "planned_only",
                    }
                )
                records.append(record)
    return records


def run_execute(
    *,
    provider_configs: list[ProviderConfig],
    prompt_specs: list[PromptSpec],
    backend_path: str,
    limit: int,
    timeout_seconds: float,
    run_dir: Path,
    max_retries: int,
    retry_sleep_seconds: float,
    resume: bool,
) -> dict[str, Any]:
    if max_retries < 0:
        raise Stage4BError("--max-retries 不能小于 0。")
    if retry_sleep_seconds < 0:
        raise Stage4BError("--retry-sleep-seconds 不能小于 0。")

    dataset, dataset_meta = load_official_dataset_for_execute(limit)
    per_example_path = run_dir / "per_example_eval.jsonl"
    existing_records = normalize_records(read_jsonl(per_example_path)) if resume else []
    existing_success_keys = {
        build_record_key(record)
        for record in existing_records
        if str(record.get("status")) == "ok" and not record.get("error_type")
    }
    all_records: list[dict[str, Any]] = list(existing_records)

    for provider_config in provider_configs:
        for prompt_spec in prompt_specs:
            for sample_index, sample in enumerate(dataset, start=1):
                sample_id = build_sample_id(sample, dataset_meta["split"], sample_index)
                preview_record = base_record(
                    provider_config=provider_config,
                    backend_path=backend_path,
                    prompt_spec=prompt_spec,
                    sample_id=sample_id,
                    gold=str(sample.get("answer") or ""),
                )
                record_key = build_record_key(preview_record)
                if record_key in existing_success_keys:
                    continue
                record = execute_sample(
                    provider_config=provider_config,
                    backend_path=backend_path,
                    prompt_spec=prompt_spec,
                    sample=sample,
                    split_name=dataset_meta["split"],
                    sample_index=sample_index,
                    timeout_seconds=timeout_seconds,
                    run_dir=run_dir,
                    max_retries=max_retries,
                    retry_sleep_seconds=retry_sleep_seconds,
                )
                all_records.append(record)
                append_jsonl(per_example_path, [record])

    normalized_records = normalize_records(all_records)
    write_jsonl(per_example_path, normalized_records)
    summaries = summarize_records(normalized_records)
    failure_cases = build_failure_cases(normalized_records)
    payload = {
        "metadata": {
            "generated_at": create_timestamp(),
            "mode": "execute",
            "run_dir": project_relative(run_dir),
            "model_called": True,
            "api_called": True,
            "new_experiment_executed": True,
            "official_score_semantics": "contains_gold_substring",
            **DIAGNOSTIC_FLAGS,
        },
        "execution": {
            **dataset_meta,
            "backend_path": backend_path,
            "limit": limit,
            "timeout_seconds": timeout_seconds,
            "max_retries": max_retries,
            "retry_sleep_seconds": retry_sleep_seconds,
            "resume": resume,
        },
        "records_count": len(normalized_records),
        "group_summaries": summaries,
        "failure_cases_count": len(failure_cases),
    }
    return {
        "payload": payload,
        "records": normalized_records,
        "summaries": summaries,
        "failure_cases": failure_cases,
    }


def render_report(payload: dict[str, Any], records: list[dict[str, Any]], run_summary: dict[str, Any]) -> str:
    metadata = payload["metadata"]
    lines = [
        "# Stage 4B MiMo Pro vs GLM-4.7 fixed-prompt AIME diagnostic 结果",
        "",
        "## 定位",
        "",
        "- 本报告只记录 Stage 4B 的 fixed-prompt 30-sample 机制诊断。",
        "- 它不是 GEPA。",
        "- 它不是 `official_budget` baseline。",
        "- 它不是 5-seed、多模型排行榜或最终性能比较。",
        "- `official_score` 在这里沿用当前仓库 `DefaultAdapter/ContainsAnswerEvaluator` 的口径：gold 字符串被完整包含在响应中即计分。",
        "- `relaxed_extractable_score` 只用于诊断 output protocol 与可提取性，不替代 official evaluator。",
        "",
        "## 边界标识",
        "",
    ]
    for key, value in metadata.items():
        if isinstance(value, bool):
            lines.append(f"- `{key} = {str(value).lower()}`")

    lines.extend(["", "## 执行状态", ""])
    if metadata["mode"] == "dry_run":
        requested = payload["requested_execution"]
        lines.extend(
            [
                "- 当前状态：dry-run manifest 已生成，30-sample diagnostic 尚未执行。",
                f"- provider：`{', '.join(requested['providers'])}`",
                f"- backend path：`{requested['backend_path']}`",
                f"- 计划样本数：`{requested['limit']}`",
                f"- prompt variants：`{', '.join(requested['prompt_variants'])}`",
                "- 本次未调用模型、未调用 API、未运行新实验。",
                "",
                "## Prompt 版本",
                "",
                "| prompt_variant | chars | words | lines |",
                "|---|---:|---:|---:|",
            ]
        )
        for prompt in payload["prompt_specs"]:
            lines.append(
                f"| {prompt['prompt_variant']} | {prompt['prompt_chars']} | "
                f"{prompt['prompt_words']} | {prompt['prompt_lines']} |"
            )
        lines.extend(
            [
                "",
                "## dry-run 结论",
                "",
                "- 当前只能确认 Stage 4B 执行计划、配置预览和 artifact schema。",
                "- 当前不能判断 official / relaxed / format loss / timeout 的真实分布。",
                "- 当前不能写任何 MiMo 与 GLM 的能力高低结论。",
            ]
        )
        return "\n".join(lines) + "\n"

    execution = payload["execution"]
    lines.extend(
        [
            "- 当前状态：30-sample fixed-prompt diagnostic 已执行。",
            f"- split：`{execution['split_label']}`",
            f"- subset：`{execution['subset_selector']}`",
            f"- backend path：`{execution['backend_path']}`",
            "",
            "## 分组汇总",
            "",
            "| provider | path | prompt | completed | official | relaxed | gap | format_loss | reasoning_error | empty_or_invalid | timeout |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for summary in run_summary["group_summaries"]:
        lines.append(
            f"| `{summary['provider']}` | `{summary['backend_path']}` | `{summary['prompt_variant']}` | "
            f"{summary['completed_count']} | {summary['official_score']} | "
            f"{summary['relaxed_extractable_score']} | {summary['official_minus_relaxed_gap']} | "
            f"{summary['format_loss_count']} | {summary['reasoning_error_count']} | "
            f"{summary['empty_or_invalid_count']} | {summary['timeout_count']} |"
        )

    if run_summary["failure_cases"]:
        lines.extend(
            [
                "",
                "## failure-mode table",
                "",
                "| provider | path | prompt | sample_id | error_type | finish_reason | content_nonempty | extracted_answer | official_score | relaxed_correct | diagnosis |",
                "|---|---|---|---|---|---|---|---|---:|---|---|",
            ]
        )
        for failure in run_summary["failure_cases"]:
            lines.append(
                f"| `{failure['provider']}` | `{failure['backend_path']}` | `{failure['prompt_variant']}` | "
                f"`{failure['sample_id']}` | `{failure['error_type']}` | `{failure['finish_reason']}` | "
                f"`{str(bool(failure['content_nonempty'])).lower()}` | `{failure['extracted_answer']}` | "
                f"{failure['official_score']} | `{str(bool(failure['relaxed_correct'])).lower()}` | "
                f"`{failure['diagnosis']}` |"
            )

    representative_records = [
        record
        for record in records
        if str(record.get("status")) == "ok"
    ][:6]
    if representative_records:
        lines.extend(
            [
                "",
                "## 代表性输出片段",
                "",
                "| provider | path | prompt | sample_id | finish_reason | preview |",
                "|---|---|---|---|---|---|",
            ]
        )
        for record in representative_records:
            lines.append(
                f"| `{record['provider']}` | `{record['backend_path']}` | `{record['prompt_variant']}` | "
                f"`{record['sample_id']}` | `{record['finish_reason']}` | {record['raw_response_preview'] or '-'} |"
            )

    lines.extend(
        [
            "",
            "## 结论边界",
            "",
            "- 可以写：某模型在当前 30-sample fixed-prompt diagnostic 中输出更稳定。",
            "- 可以写：某模型的 `format_loss` 更少。",
            "- 可以写：某模型的 `relaxed_extractable_score` 更高。",
            "- 可以写：`strong_format_seed_prompt` 对某模型的 `official_score` 更敏感。",
            "- 不能写：MiMo Pro 综合强于 GLM-4.7。",
            "- 不能写：GLM-4.7 综合强于 MiMo Pro。",
            "- 不能写：谁的数学能力更强。",
            "- 不能写：谁更适合 `official_budget` 或已经完成 GEPA 复现。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    enforce_stage4b_limit(args.limit)
    if args.timeout <= 0:
        raise Stage4BError("--timeout 必须大于 0。")

    provider_configs = build_provider_configs(args)
    prompt_specs = load_prompt_specs(args.prompt_variant)

    if args.run_dir:
        run_dir = (PROJECT_ROOT / args.run_dir).resolve()
        if not run_dir.exists():
            raise Stage4BError(f"--run-dir 指向的目录不存在：{run_dir}")
    else:
        output_dir = (PROJECT_ROOT / args.output_dir).resolve()
        run_dir = create_run_dir(output_dir)

    input_snapshot = build_input_snapshot(
        provider_configs=provider_configs,
        prompt_specs=prompt_specs,
        backend_path=args.backend_path,
        limit=args.limit,
        timeout_seconds=args.timeout,
        run_dir=run_dir,
        execute=args.execute,
    )
    write_json(run_dir / "input_snapshot.json", input_snapshot)
    write_yaml(run_dir / "input_snapshot.yaml", input_snapshot)

    report_path = (PROJECT_ROOT / args.report_path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    if args.execute:
        execute_result = run_execute(
            provider_configs=provider_configs,
            prompt_specs=prompt_specs,
            backend_path=args.backend_path,
            limit=args.limit,
            timeout_seconds=args.timeout,
            run_dir=run_dir,
            max_retries=args.max_retries,
            retry_sleep_seconds=args.retry_sleep_seconds,
            resume=args.resume,
        )
        payload = execute_result["payload"]
        records = execute_result["records"]
        run_summary = build_run_summary(records=records, execute=True)
        failure_cases = execute_result["failure_cases"]
    else:
        records = build_dry_run_records(
            provider_configs=provider_configs,
            prompt_specs=prompt_specs,
            backend_path=args.backend_path,
            limit=args.limit,
        )
        payload = input_snapshot
        run_summary = build_run_summary(records=records, execute=False)
        failure_cases = run_summary["failure_cases"]
        write_jsonl(run_dir / "per_example_eval.jsonl", records)

    fixed_prompt_results = {
        "metadata": payload["metadata"],
        "records_count": len(records),
        "group_summaries": run_summary["group_summaries"],
        **DIAGNOSTIC_FLAGS,
    }
    write_json(run_dir / "fixed_prompt_results.json", fixed_prompt_results)
    write_json(run_dir / "run_summary.json", run_summary)
    write_json(run_dir / "failure_cases.json", failure_cases)
    if args.execute:
        write_jsonl(run_dir / "per_example_eval.jsonl", records)
    report_text = render_report(payload, records, run_summary)
    write_text(report_path, report_text)
    print(
        json.dumps(
            {
                "run_dir": project_relative(run_dir),
                "report_path": project_relative(report_path),
                "mode": payload["metadata"]["mode"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
