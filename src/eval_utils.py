from __future__ import annotations

import json
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from tqdm import tqdm

from src.deepseek_utils import build_litellm_model_name, temporary_openai_compatible_env

DEFAULT_EVAL_BATCH_SIZE = 25


def load_prompt_candidate(path: str | Path) -> dict[str, str]:
    prompt_path = Path(path).resolve()
    with prompt_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if "candidate" in payload and isinstance(payload["candidate"], dict):
        return payload["candidate"]
    if "system_prompt" in payload:
        return {"system_prompt": str(payload["system_prompt"])}
    raise ValueError(f"无法从文件解析 prompt candidate：{prompt_path}")


def _iter_batches(items: list[Any], batch_size: int) -> list[list[Any]]:
    if batch_size <= 0:
        raise ValueError("batch_size 必须是大于 0 的整数。")
    return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]


def _build_sample_id(sample: dict[str, Any], split_name: str, sample_index: int) -> str:
    return str(sample.get("sample_id") or sample.get("id") or f"{split_name}-{sample_index}")


def normalize_default_adapter_sample(sample: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(sample)
    normalized["input"] = str(sample.get("input", ""))
    normalized["answer"] = str(sample.get("answer", ""))

    additional_context = sample.get("additional_context")
    if isinstance(additional_context, dict):
        normalized["additional_context"] = {
            str(key): str(value) for key, value in additional_context.items()
        }
    else:
        normalized["additional_context"] = {}

    return normalized


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path).resolve()
    if not target.exists():
        return []

    records: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL 解析失败：{target} 第 {line_number} 行：{exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"JSONL 记录必须是对象：{target} 第 {line_number} 行")
            records.append(payload)
    return records


def append_jsonl(path: str | Path, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    target = Path(path).resolve()
    with target.open("a", encoding="utf-8") as handle:
        for record in records:
            json.dump(record, handle, ensure_ascii=False)
            handle.write("\n")


def build_record_key(sample_id: str, prompt_version: str) -> str:
    return f"{prompt_version}::{sample_id}"


def normalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_key: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for record in records:
        key = build_record_key(str(record["sample_id"]), str(record["prompt_version"]))
        latest_by_key[key] = record
    return list(latest_by_key.values())


def split_effective_records(
    records: list[dict[str, Any]],
    *,
    prompt_version: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    effective_records = [
        record for record in normalize_records(records) if record.get("prompt_version") == prompt_version
    ]
    successful_records = [record for record in effective_records if not record.get("error")]
    failed_records = [record for record in effective_records if record.get("error")]
    return successful_records, failed_records


def _evaluate_batch_with_retry(
    *,
    adapter: Any,
    batch: list[dict[str, Any]],
    candidate: dict[str, str],
    max_retries: int,
    retry_sleep_seconds: float,
) -> tuple[Any, int]:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return adapter.evaluate(batch, candidate, capture_traces=False), attempt + 1
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                raise
            if retry_sleep_seconds > 0:
                time.sleep(retry_sleep_seconds)
    assert last_error is not None
    raise last_error


def evaluate_candidate(
    *,
    dataset: list[dict[str, Any]],
    candidate: dict[str, str],
    prompt_version: str,
    split_name: str,
    task_model: str,
    api_key: str,
    api_base: str,
    batch_size: int = DEFAULT_EVAL_BATCH_SIZE,
    existing_prompt_records: list[dict[str, Any]] | None = None,
    checkpoint_path: str | Path | None = None,
    max_retries: int = 0,
    retry_sleep_seconds: float = 0.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from gepa.adapters.default_adapter.default_adapter import DefaultAdapter

    existing_prompt_records = list(existing_prompt_records or [])
    completed_sample_ids = {str(record["sample_id"]) for record in existing_prompt_records}
    pending_items = [
        (sample_index, sample)
        for sample_index, sample in enumerate(dataset, start=1)
        if _build_sample_id(sample, split_name, sample_index) not in completed_sample_ids
    ]

    records: list[dict[str, Any]] = list(existing_prompt_records)
    with temporary_openai_compatible_env(api_key=api_key, api_base=api_base):
        adapter = DefaultAdapter(model=build_litellm_model_name(task_model))
        progress = tqdm(total=len(dataset), desc=f"评估 {prompt_version}", leave=False)
        progress.update(len(existing_prompt_records))
        try:
            for batch_items in _iter_batches(pending_items, batch_size):
                batch = [normalize_default_adapter_sample(sample) for _, sample in batch_items]
                try:
                    result, attempt_count = _evaluate_batch_with_retry(
                        adapter=adapter,
                        batch=batch,
                        candidate=candidate,
                        max_retries=max_retries,
                        retry_sleep_seconds=retry_sleep_seconds,
                    )
                    outputs = result.outputs
                    scores = result.scores
                    new_records: list[dict[str, Any]] = []
                    for index_within_batch, (sample, output, score) in enumerate(
                        zip(batch, outputs, scores, strict=True),
                        start=1,
                    ):
                        sample_index = batch_items[index_within_batch - 1][0]
                        new_records.append(
                            {
                                "sample_id": _build_sample_id(sample, split_name, sample_index),
                                "prompt_version": prompt_version,
                                "question": sample["input"],
                                "prediction": output["full_assistant_response"],
                                "gold": sample["answer"],
                                "score": float(score),
                                "error": None,
                                "attempt_count": attempt_count,
                            }
                        )
                    records.extend(new_records)
                    if checkpoint_path is not None:
                        append_jsonl(checkpoint_path, new_records)
                except Exception as exc:
                    error_text = f"{type(exc).__name__} after {max_retries + 1} attempts: {exc}"
                    error_records: list[dict[str, Any]] = []
                    for index_within_batch, sample in enumerate(batch, start=1):
                        sample_index = batch_items[index_within_batch - 1][0]
                        error_records.append(
                            {
                                "sample_id": _build_sample_id(sample, split_name, sample_index),
                                "prompt_version": prompt_version,
                                "question": sample["input"],
                                "prediction": "",
                                "gold": sample["answer"],
                                "score": 0.0,
                                "error": error_text,
                                "attempt_count": max_retries + 1,
                            }
                        )
                    records.extend(error_records)
                    if checkpoint_path is not None:
                        append_jsonl(checkpoint_path, error_records)
                finally:
                    progress.update(len(batch))
        finally:
            progress.close()

    average_score = sum(record["score"] for record in records) / len(records) if records else 0.0
    return records, {
        "split": split_name,
        "eval_model": task_model,
        "num_examples": len(records),
        "evaluated_sample_count": len(records),
        "requested_sample_count": len(dataset),
        "average_score": average_score,
        "num_errors": sum(1 for record in records if record["error"]),
        "completed_from_resume": len(existing_prompt_records),
        "num_new_records": len(records) - len(existing_prompt_records),
        "used_resume": bool(existing_prompt_records),
        "is_complete": len(records) == len(dataset),
    }


def write_jsonl(path: str | Path, records: list[dict[str, Any]]) -> None:
    target = Path(path).resolve()
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            json.dump(record, handle, ensure_ascii=False)
            handle.write("\n")
