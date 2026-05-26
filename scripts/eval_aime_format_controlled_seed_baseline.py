from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_yaml_file
from src.logging_utils import create_run_dir, create_timestamp, write_json, write_text, write_yaml


PROMPT_KEYS: tuple[str, ...] = (
    "original_seed_prompt",
    "strong_format_seed_prompt",
    "answer_first_format_prompt",
)

DIAGNOSTIC_FLAGS: dict[str, bool] = {
    "format_controlled_seed_baseline": True,
    "diagnostic_only": True,
    "not_official_budget_baseline": True,
    "not_gepa_optimized": True,
    "no_optimizer_modified": True,
    "no_evaluator_modified": True,
    "not_same_model_reproduction": True,
    "not_performance_claim": True,
}


class FormatBaselineError(RuntimeError):
    """format-controlled seed baseline 的配置或执行边界不满足要求。"""


@dataclass(frozen=True)
class PromptSpec:
    name: str
    system_prompt: str


@dataclass(frozen=True)
class ExtractedAnswer:
    value: str | None
    method: str


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
        raise FormatBaselineError(f"无法从 gold 中提取 `###` 答案：{gold!r}")
    return normalize_answer(match.group(1))


def extract_prediction_answer(prediction: str) -> ExtractedAnswer:
    text = str(prediction or "")
    if not text.strip():
        return ExtractedAnswer(None, "empty")

    patterns: tuple[tuple[str, str], ...] = (
        ("protocol_hash", r"###\s*([^\n\r]+)"),
        ("boxed", r"\\boxed\{([^{}]+)\}"),
        ("final_answer", r"(?i)final answer(?: is|:)?\s*([+-]?\d+)"),
        ("answer_is", r"(?i)answer is\s*([+-]?\d+)"),
    )
    for method, pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            return ExtractedAnswer(normalize_answer(matches[-1]), method)
    return ExtractedAnswer(None, "unextractable")


def classify_eval_record(record: dict[str, Any]) -> dict[str, Any]:
    for key in ("sample_id", "prompt_version", "prediction", "gold", "score"):
        if key not in record:
            raise FormatBaselineError(f"评估记录缺少字段：{key}")

    score = record["score"]
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise FormatBaselineError(f"score 必须是数字：{record['sample_id']}")

    official_correct = float(score) >= 1.0
    gold_answer = extract_gold_answer(str(record["gold"]))
    extracted = extract_prediction_answer(str(record.get("prediction") or ""))
    extracted_correct = extracted.value == gold_answer if extracted.value is not None else False

    if official_correct:
        category = "official_correct"
    elif extracted_correct:
        category = "format_loss"
    elif extracted.value is None:
        category = "empty_or_invalid"
    else:
        category = "reasoning_error"

    return {
        "sample_id": str(record["sample_id"]),
        "prompt_version": str(record["prompt_version"]),
        "official_score": float(score),
        "official_correct": official_correct,
        "gold_answer": gold_answer,
        "extracted_answer": extracted.value,
        "extract_method": extracted.method,
        "extracted_correct": extracted_correct,
        "relaxed_extractable_correct": official_correct or extracted_correct,
        "category": category,
        "error": record.get("error"),
    }


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise FormatBaselineError("评估记录不能为空。")

    classified = [classify_eval_record(record) for record in records]
    total = len(classified)
    official_correct = sum(record["category"] == "official_correct" for record in classified)
    format_loss = sum(record["category"] == "format_loss" for record in classified)
    reasoning_error = sum(record["category"] == "reasoning_error" for record in classified)
    empty_or_invalid = sum(record["category"] == "empty_or_invalid" for record in classified)
    relaxed_correct = official_correct + format_loss

    return {
        "num_examples": total,
        "official_score": round(sum(record["official_score"] for record in classified) / total, 12),
        "relaxed_extractable_score": round(relaxed_correct / total, 12),
        "official_correct_count": official_correct,
        "format_loss_count": format_loss,
        "reasoning_error_count": reasoning_error,
        "empty_or_invalid_count": empty_or_invalid,
        "relaxed_extractable_correct_count": relaxed_correct,
    }


def require_positive_int(raw_config: dict[str, Any], key: str) -> int:
    value = raw_config.get(key)
    if not isinstance(value, int) or value <= 0:
        raise FormatBaselineError(f"{key} 必须是大于 0 的整数。")
    return value


def load_prompt_specs(raw_config: dict[str, Any]) -> list[PromptSpec]:
    prompts = raw_config.get("prompts")
    if not isinstance(prompts, dict):
        raise FormatBaselineError("配置缺少 prompts 字典。")

    specs: list[PromptSpec] = []
    for key in PROMPT_KEYS:
        value = prompts.get(key)
        if not isinstance(value, str) or not value.strip():
            raise FormatBaselineError(f"配置缺少非空 prompt：prompts.{key}")
        specs.append(PromptSpec(name=key, system_prompt=value.strip()))
    return specs


def load_smoke_config(config_path: Path) -> dict[str, Any]:
    raw_config = load_yaml_file(config_path)
    if raw_config.get("diagnostic_type") != "format_controlled_seed_baseline":
        raise FormatBaselineError("diagnostic_type 必须为 format_controlled_seed_baseline。")
    require_positive_int(raw_config, "smoke_sample_count")
    require_positive_int(raw_config, "batch_size")
    load_prompt_specs(raw_config)
    output_dir = str(raw_config.get("output_dir") or "").strip()
    if not output_dir:
        raise FormatBaselineError("配置缺少 output_dir。")
    return raw_config


def enforce_smoke_limit(limit: int, *, allow_larger_smoke: bool) -> None:
    if limit <= 0:
        raise FormatBaselineError("smoke 样本数必须大于 0。")
    if limit > 45 and not allow_larger_smoke:
        raise FormatBaselineError(
            "format-controlled baseline 当前只允许小范围 smoke；"
            "如需超过 45 题，必须显式传入 --allow-larger-smoke。"
        )


def build_dry_run_payload(
    *,
    raw_config: dict[str, Any],
    config_path: Path,
    limit: int,
    batch_size: int,
    run_dir: Path,
) -> dict[str, Any]:
    prompt_specs = load_prompt_specs(raw_config)
    return {
        "metadata": {
            "run_name": "aime_format_controlled_seed_baseline_smoke",
            "generated_at": create_timestamp(),
            "mode": "dry_run",
            "config_path": str(config_path),
            "run_dir": str(run_dir),
            "model_called": False,
            "api_called": False,
            "gepa_optimize_called": False,
            "new_experiment_executed": False,
            **DIAGNOSTIC_FLAGS,
        },
        "requested_execution": {
            "sample_limit": limit,
            "batch_size": batch_size,
            "prompt_versions": [spec.name for spec in prompt_specs],
        },
        "prompts": [
            {
                "prompt_version": spec.name,
                "prompt_chars": len(spec.system_prompt),
                "prompt_words": len(spec.system_prompt.split()),
                "prompt_lines": len(spec.system_prompt.splitlines()),
                "system_prompt": spec.system_prompt,
            }
            for spec in prompt_specs
        ],
        "result": None,
    }


def load_official_dataset_for_execute() -> tuple[list[dict[str, Any]], str, str]:
    from src.gepa_official_runner import load_official_aime_dataset

    _, valset, testset, _, _ = load_official_aime_dataset()
    if testset is not None:
        return list(testset), "test", "test split"
    return list(valset), "val", "validation sanity check only"


def run_execute(
    *,
    raw_config: dict[str, Any],
    config_path: Path,
    limit: int,
    batch_size: int,
    run_dir: Path,
    max_retries: int,
    retry_sleep_seconds: float,
) -> dict[str, Any]:
    from src.config import load_experiment_config
    from src.eval_utils import evaluate_candidate, normalize_records, write_jsonl

    experiment_config = load_experiment_config(config_path, project_root=PROJECT_ROOT)
    dataset, split_name, split_label = load_official_dataset_for_execute()
    dataset = dataset[:limit]
    prompt_specs = load_prompt_specs(raw_config)

    per_example_path = run_dir / "per_example_eval.jsonl"
    all_records: list[dict[str, Any]] = []
    summaries: dict[str, dict[str, Any]] = {}
    for spec in prompt_specs:
        records, _ = evaluate_candidate(
            dataset=dataset,
            candidate={"system_prompt": spec.system_prompt},
            prompt_version=spec.name,
            split_name=split_name,
            task_model=experiment_config.task_model,
            api_key=experiment_config.api_key,
            api_base=experiment_config.api_base,
            batch_size=batch_size,
            checkpoint_path=per_example_path,
            max_retries=max_retries,
            retry_sleep_seconds=retry_sleep_seconds,
        )
        all_records.extend(records)
        summaries[spec.name] = summarize_records(records)

    all_records = normalize_records(all_records)
    write_jsonl(per_example_path, all_records)
    return {
        "metadata": {
            "run_name": "aime_format_controlled_seed_baseline_smoke",
            "generated_at": create_timestamp(),
            "mode": "execute",
            "config_path": str(config_path),
            "run_dir": str(run_dir),
            "model_called": True,
            "api_called": True,
            "gepa_optimize_called": False,
            "new_experiment_executed": True,
            **DIAGNOSTIC_FLAGS,
        },
        "execution": {
            "split": split_name,
            "split_label": split_label,
            "sample_limit": limit,
            "batch_size": batch_size,
            "max_retries": max_retries,
            "retry_sleep_seconds": retry_sleep_seconds,
        },
        "summaries": summaries,
    }


def render_report(payload: dict[str, Any]) -> str:
    metadata = payload["metadata"]
    lines = [
        "# AIME format-controlled seed baseline smoke 结果",
        "",
        "## 文档定位",
        "",
        "- 本报告记录 format-controlled seed baseline 的 guarded smoke 状态。",
        "- 本任务不是 GEPA 优化，不修改 optimizer，不修改 evaluator。",
        "- `official_score` 仍是 official evaluator 下的主指标；`relaxed_extractable_score` 只用于诊断。",
        "- 本结果不能写成 official_budget baseline、same-model reproduction 或新 GEPA result。",
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
                "- 当前状态：dry-run manifest 已生成，smoke 尚未执行。",
                f"- 计划样本数：`{requested['sample_limit']}`",
                f"- batch size：`{requested['batch_size']}`",
                f"- prompt versions：`{', '.join(requested['prompt_versions'])}`",
                "- 本次未调用模型、未调用 API、未运行新实验。",
                "",
                "## Prompt 版本",
                "",
                "| prompt_version | chars | words | lines |",
                "|---|---:|---:|---:|",
            ]
        )
        for prompt in payload["prompts"]:
            lines.append(
                f"| {prompt['prompt_version']} | {prompt['prompt_chars']} | "
                f"{prompt['prompt_words']} | {prompt['prompt_lines']} |"
            )
    else:
        execution = payload["execution"]
        lines.extend(
            [
                "- 当前状态：guarded smoke 已执行。",
                f"- split：`{execution['split_label']}`",
                f"- 样本数：`{execution['sample_limit']}`",
                f"- batch size：`{execution['batch_size']}`",
                "",
                "## 诊断指标",
                "",
                "| prompt_version | examples | official_score | relaxed_extractable_score | format_loss | reasoning_error | empty_or_invalid |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for prompt_version, summary in payload["summaries"].items():
            lines.append(
                f"| {prompt_version} | {summary['num_examples']} | "
                f"{summary['official_score']} | {summary['relaxed_extractable_score']} | "
                f"{summary['format_loss_count']} | {summary['reasoning_error_count']} | "
                f"{summary['empty_or_invalid_count']} |"
            )

    lines.extend(
        [
            "",
            "## 结论边界",
            "",
            "- 可以写：这是 format-controlled baseline diagnostic。",
            "- 可以写：该 smoke 用于估计更强格式约束本身对 official score 的影响。",
            "- 不能写：这是新的 GEPA result。",
            "- 不能写：这是 official_budget baseline。",
            "- 不能写：它已经证明或否定 GEPA 的数学推理收益。",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AIME format-controlled seed baseline guarded smoke runner。")
    parser.add_argument(
        "--config",
        default="configs/aime_format_controlled_seed_baseline_smoke.yaml",
        help="format-controlled seed baseline 配置文件。",
    )
    parser.add_argument(
        "--report-path",
        default="reports/aime_format_controlled_seed_baseline_smoke_result.md",
        help="写入 smoke 结果报告的位置。",
    )
    parser.add_argument("--execute", action="store_true", help="显式执行模型评估；默认只 dry-run。")
    parser.add_argument("--limit", type=int, default=None, help="覆盖配置中的 smoke_sample_count。")
    parser.add_argument("--batch-size", type=int, default=None, help="覆盖配置中的 batch_size。")
    parser.add_argument(
        "--allow-larger-smoke",
        action="store_true",
        help="允许超过 45 题；默认禁止直接扩大到完整 test set。",
    )
    parser.add_argument("--max-retries", type=int, default=0, help="执行模式下的批次重试次数。")
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0, help="执行模式下的重试等待秒数。")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = (PROJECT_ROOT / args.config).resolve()
    raw_config = load_smoke_config(config_path)
    limit = args.limit if args.limit is not None else require_positive_int(raw_config, "smoke_sample_count")
    batch_size = args.batch_size if args.batch_size is not None else require_positive_int(raw_config, "batch_size")

    enforce_smoke_limit(limit, allow_larger_smoke=args.allow_larger_smoke)
    if batch_size <= 0:
        raise FormatBaselineError("--batch-size 必须是大于 0 的整数。")
    if args.max_retries < 0:
        raise FormatBaselineError("--max-retries 不能小于 0。")
    if args.retry_sleep_seconds < 0:
        raise FormatBaselineError("--retry-sleep-seconds 不能小于 0。")

    output_dir = (PROJECT_ROOT / str(raw_config["output_dir"])).resolve()
    run_dir = create_run_dir(output_dir)
    write_yaml(run_dir / "config_resolved.yaml", raw_config)

    if args.execute:
        payload = run_execute(
            raw_config=raw_config,
            config_path=config_path,
            limit=limit,
            batch_size=batch_size,
            run_dir=run_dir,
            max_retries=args.max_retries,
            retry_sleep_seconds=args.retry_sleep_seconds,
        )
        output_name = "format_controlled_seed_baseline_smoke_result.json"
    else:
        payload = build_dry_run_payload(
            raw_config=raw_config,
            config_path=config_path,
            limit=limit,
            batch_size=batch_size,
            run_dir=run_dir,
        )
        output_name = "format_controlled_seed_baseline_smoke_dry_run.json"

    write_json(run_dir / output_name, payload)
    report_path = (PROJECT_ROOT / args.report_path).resolve()
    write_text(report_path, render_report(payload))
    print(json.dumps({"run_dir": str(run_dir), "report_path": str(report_path), "mode": payload["metadata"]["mode"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
