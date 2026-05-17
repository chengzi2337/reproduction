from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tqdm import tqdm

from src.deepseek_utils import build_litellm_model_name, temporary_openai_compatible_env


def load_prompt_candidate(path: str | Path) -> dict[str, str]:
    prompt_path = Path(path).resolve()
    with prompt_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if "candidate" in payload and isinstance(payload["candidate"], dict):
        return payload["candidate"]
    if "system_prompt" in payload:
        return {"system_prompt": str(payload["system_prompt"])}
    raise ValueError(f"无法从文件解析 prompt candidate：{prompt_path}")


def evaluate_candidate(
    *,
    dataset: list[dict[str, Any]],
    candidate: dict[str, str],
    prompt_version: str,
    split_name: str,
    task_model: str,
    api_key: str,
    api_base: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from gepa.adapters.default_adapter.default_adapter import DefaultAdapter

    records: list[dict[str, Any]] = []
    with temporary_openai_compatible_env(api_key=api_key, api_base=api_base):
        adapter = DefaultAdapter(model=build_litellm_model_name(task_model))
        for sample_index, sample in enumerate(tqdm(dataset, desc=f"评估 {prompt_version}", leave=False), start=1):
            prediction = ""
            score = 0.0
            error = None
            try:
                result = adapter.evaluate([sample], candidate, capture_traces=False)
                prediction = result.outputs[0]["full_assistant_response"]
                score = float(result.scores[0])
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"

            records.append(
                {
                    "sample_id": str(sample.get("sample_id") or sample.get("id") or f"{split_name}-{sample_index}"),
                    "prompt_version": prompt_version,
                    "question": sample["input"],
                    "prediction": prediction,
                    "gold": sample["answer"],
                    "score": score,
                    "error": error,
                }
            )

    average_score = sum(record["score"] for record in records) / len(records) if records else 0.0
    return records, {
        "split": split_name,
        "num_examples": len(records),
        "average_score": average_score,
        "num_errors": sum(1 for record in records if record["error"]),
    }


def write_jsonl(path: str | Path, records: list[dict[str, Any]]) -> None:
    target = Path(path).resolve()
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            json.dump(record, handle, ensure_ascii=False)
            handle.write("\n")
