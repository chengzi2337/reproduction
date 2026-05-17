from __future__ import annotations

import json
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


def _iter_batches(dataset: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    if batch_size <= 0:
        raise ValueError("batch_size 必须是大于 0 的整数。")
    return [dataset[index : index + batch_size] for index in range(0, len(dataset), batch_size)]


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
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from gepa.adapters.default_adapter.default_adapter import DefaultAdapter

    records: list[dict[str, Any]] = []
    with temporary_openai_compatible_env(api_key=api_key, api_base=api_base):
        adapter = DefaultAdapter(model=build_litellm_model_name(task_model))
        progress = tqdm(total=len(dataset), desc=f"评估 {prompt_version}", leave=False)
        try:
            for batch_start, batch in enumerate(_iter_batches(dataset, batch_size)):
                try:
                    result = adapter.evaluate(batch, candidate, capture_traces=False)
                    outputs = result.outputs
                    scores = result.scores
                    for index_within_batch, (sample, output, score) in enumerate(
                        zip(batch, outputs, scores, strict=True),
                        start=1,
                    ):
                        sample_index = batch_start * batch_size + index_within_batch
                        records.append(
                            {
                                "sample_id": str(
                                    sample.get("sample_id") or sample.get("id") or f"{split_name}-{sample_index}"
                                ),
                                "prompt_version": prompt_version,
                                "question": sample["input"],
                                "prediction": output["full_assistant_response"],
                                "gold": sample["answer"],
                                "score": float(score),
                                "error": None,
                            }
                        )
                except Exception as exc:
                    error_text = f"{type(exc).__name__}: {exc}"
                    for index_within_batch, sample in enumerate(batch, start=1):
                        sample_index = batch_start * batch_size + index_within_batch
                        records.append(
                            {
                                "sample_id": str(
                                    sample.get("sample_id") or sample.get("id") or f"{split_name}-{sample_index}"
                                ),
                                "prompt_version": prompt_version,
                                "question": sample["input"],
                                "prediction": "",
                                "gold": sample["answer"],
                                "score": 0.0,
                                "error": error_text,
                            }
                        )
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
        "average_score": average_score,
        "num_errors": sum(1 for record in records if record["error"]),
    }


def write_jsonl(path: str | Path, records: list[dict[str, Any]]) -> None:
    target = Path(path).resolve()
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            json.dump(record, handle, ensure_ascii=False)
            handle.write("\n")
