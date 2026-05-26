from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_RUNS: tuple[tuple[int, str], ...] = (
    (0, "outputs/gepa_aime_official_budget_seed0/20260522T121001+0800"),
    (1, "outputs/gepa_aime_official_budget_seed1/20260522T175103+0800"),
    (2, "outputs/gepa_aime_official_budget_seed2/20260522T221654+0800"),
    (3, "outputs/gepa_aime_official_budget_seed3/20260525T104154+0800"),
    (4, "outputs/gepa_aime_official_budget_seed4/20260525T135207+0800"),
)

PROMPT_VERSIONS: tuple[str, ...] = ("seed", "optimized")

AUDIT_FLAGS: dict[str, bool] = {
    "not_new_experiment": True,
    "diagnostic_only": True,
    "relaxed_score_not_official": True,
    "official_score_not_replaced": True,
    "no_model_called": True,
    "no_api_called": True,
    "no_gepa_optimize_called": True,
    "optimizer_not_modified": True,
    "evaluator_not_modified": True,
    "not_performance_claim": True,
}


class AuditError(RuntimeError):
    """只读审计输入缺失或 artifact 结构不符合预期。"""


@dataclass(frozen=True)
class ExtractedAnswer:
    value: str | None
    method: str


def create_timestamp() -> str:
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    return f"{timestamp[:-5]}{timestamp[-5:-2]}{timestamp[-2:]}"


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
        raise AuditError(f"无法从 gold 中提取 `###` 答案：{gold!r}")
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


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise AuditError(f"缺少必需 artifact：{path}")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise AuditError(f"JSONL 解析失败：{path} 第 {line_number} 行：{exc}") from exc
            if not isinstance(payload, dict):
                raise AuditError(f"JSONL 记录必须是 object：{path} 第 {line_number} 行")
            records.append(payload)
    if not records:
        raise AuditError(f"per_example_eval.jsonl 不能为空：{path}")
    return records


def normalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for record in records:
        sample_id = str(record.get("sample_id", ""))
        prompt_version = str(record.get("prompt_version", ""))
        key = (prompt_version, sample_id)
        if key not in latest_by_key:
            order.append(key)
        latest_by_key[key] = record
    return [latest_by_key[key] for key in order]


def require_record_field(record: dict[str, Any], key: str, source: Path) -> Any:
    if key not in record:
        raise AuditError(f"{source} 中记录缺少字段：{key}")
    return record[key]


def classify_record(record: dict[str, Any], source: Path) -> dict[str, Any]:
    sample_id = str(require_record_field(record, "sample_id", source))
    prompt_version = str(require_record_field(record, "prompt_version", source))
    if prompt_version not in PROMPT_VERSIONS:
        raise AuditError(f"{source} 中未知 prompt_version：{prompt_version}")

    score_value = require_record_field(record, "score", source)
    if isinstance(score_value, bool) or not isinstance(score_value, (int, float)):
        raise AuditError(f"{source} 中 score 必须是数字：{sample_id}")
    official_correct = float(score_value) >= 1.0

    gold_answer = extract_gold_answer(str(require_record_field(record, "gold", source)))
    prediction = str(require_record_field(record, "prediction", source) or "")
    extracted = extract_prediction_answer(prediction)
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
        "sample_id": sample_id,
        "prompt_version": prompt_version,
        "official_score": float(score_value),
        "official_correct": official_correct,
        "gold_answer": gold_answer,
        "extracted_answer": extracted.value,
        "extract_method": extracted.method,
        "extracted_correct": extracted_correct,
        "relaxed_extractable_correct": official_correct or extracted_correct,
        "category": category,
        "error": record.get("error"),
    }


def summarize_classified_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    if total == 0:
        raise AuditError("分类记录不能为空。")

    counts = {
        "official_correct_count": sum(record["category"] == "official_correct" for record in records),
        "format_loss_count": sum(record["category"] == "format_loss" for record in records),
        "reasoning_error_count": sum(record["category"] == "reasoning_error" for record in records),
        "empty_or_invalid_count": sum(record["category"] == "empty_or_invalid" for record in records),
    }
    relaxed_correct_count = sum(record["relaxed_extractable_correct"] for record in records)
    official_score = sum(record["official_score"] for record in records) / total
    relaxed_score = relaxed_correct_count / total

    return {
        "num_examples": total,
        **counts,
        "relaxed_extractable_correct_count": relaxed_correct_count,
        "official_score": round(official_score, 12),
        "relaxed_extractable_score": round(relaxed_score, 12),
        "format_loss_rate": round(counts["format_loss_count"] / total, 12),
        "reasoning_error_rate": round(counts["reasoning_error_count"] / total, 12),
        "empty_or_invalid_rate": round(counts["empty_or_invalid_count"] / total, 12),
        "relaxed_minus_official": round(relaxed_score - official_score, 12),
        "diagnostic_only": True,
        "relaxed_score_not_official": True,
    }


def audit_run(project_root: Path, seed: int, run_dir_text: str) -> dict[str, Any]:
    run_dir = project_root / run_dir_text
    if not run_dir.exists() or not run_dir.is_dir():
        raise AuditError(f"运行目录不存在或不是目录：{run_dir_text}")
    source = run_dir / "per_example_eval.jsonl"
    raw_records = normalize_records(read_jsonl(source))
    classified = [classify_record(record, source) for record in raw_records]

    by_prompt_version: dict[str, dict[str, Any]] = {}
    for prompt_version in PROMPT_VERSIONS:
        prompt_records = [
            record for record in classified if record["prompt_version"] == prompt_version
        ]
        if not prompt_records:
            raise AuditError(f"{source} 缺少 prompt_version={prompt_version} 的记录")
        by_prompt_version[prompt_version] = summarize_classified_records(prompt_records)

    return {
        "seed": seed,
        "run_dir": run_dir_text,
        "artifact": "per_example_eval.jsonl",
        "by_prompt_version": by_prompt_version,
    }


def build_overall_analysis(run_records: list[dict[str, Any]]) -> dict[str, Any]:
    analysis: dict[str, Any] = {}
    for prompt_version in PROMPT_VERSIONS:
        summaries = [
            run_record["by_prompt_version"][prompt_version] for run_record in run_records
        ]
        total_examples = sum(summary["num_examples"] for summary in summaries)
        if total_examples == 0:
            raise AuditError(f"{prompt_version} 总样本数为 0")
        official_correct = sum(summary["official_correct_count"] for summary in summaries)
        format_loss = sum(summary["format_loss_count"] for summary in summaries)
        reasoning_error = sum(summary["reasoning_error_count"] for summary in summaries)
        empty_or_invalid = sum(summary["empty_or_invalid_count"] for summary in summaries)
        relaxed_correct = official_correct + format_loss
        analysis[prompt_version] = {
            "num_examples": total_examples,
            "official_correct_count": official_correct,
            "format_loss_count": format_loss,
            "reasoning_error_count": reasoning_error,
            "empty_or_invalid_count": empty_or_invalid,
            "relaxed_extractable_correct_count": relaxed_correct,
            "official_score": round(official_correct / total_examples, 12),
            "relaxed_extractable_score": round(relaxed_correct / total_examples, 12),
            "format_loss_rate": round(format_loss / total_examples, 12),
            "relaxed_minus_official": round(
                (relaxed_correct - official_correct) / total_examples,
                12,
            ),
        }

    seed_analysis = analysis["seed"]
    optimized_analysis = analysis["optimized"]
    return {
        "by_prompt_version": analysis,
        "seed_format_loss_count_minus_optimized": (
            seed_analysis["format_loss_count"] - optimized_analysis["format_loss_count"]
        ),
        "official_score_gain": round(
            optimized_analysis["official_score"] - seed_analysis["official_score"],
            12,
        ),
        "relaxed_extractable_score_gain": round(
            optimized_analysis["relaxed_extractable_score"]
            - seed_analysis["relaxed_extractable_score"],
            12,
        ),
        "score_gain_is_not_pure_reasoning_improvement": True,
        "official_score_remains_primary": True,
    }


def build_audit_payload(project_root: Path, runs: tuple[tuple[int, str], ...]) -> dict[str, Any]:
    run_records = [audit_run(project_root, seed, run_dir_text) for seed, run_dir_text in runs]
    return {
        "metadata": {
            "audit_name": "aime_official_budget_answer_extractability_audit",
            "generated_at": create_timestamp(),
            **AUDIT_FLAGS,
        },
        "runs": run_records,
        "analysis": build_overall_analysis(run_records),
    }


def render_bool(value: bool) -> str:
    return "`true`" if value else "`false`"


def render_summary_table(payload: dict[str, Any]) -> list[str]:
    lines = [
        "| prompt_version | examples | official_score | relaxed_extractable_score | relaxed_minus_official | official_correct | format_loss | reasoning_error | empty_or_invalid |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for prompt_version in PROMPT_VERSIONS:
        summary = payload["analysis"]["by_prompt_version"][prompt_version]
        lines.append(
            f"| {prompt_version} | {summary['num_examples']} | "
            f"{summary['official_score']} | {summary['relaxed_extractable_score']} | "
            f"{summary['relaxed_minus_official']} | {summary['official_correct_count']} | "
            f"{summary['format_loss_count']} | {summary['reasoning_error_count']} | "
            f"{summary['empty_or_invalid_count']} |"
        )
    return lines


def render_run_table(payload: dict[str, Any]) -> list[str]:
    lines = [
        "| seed | prompt_version | examples | official_score | relaxed_extractable_score | format_loss | reasoning_error | empty_or_invalid |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for run_record in payload["runs"]:
        for prompt_version in PROMPT_VERSIONS:
            summary = run_record["by_prompt_version"][prompt_version]
            lines.append(
                f"| {run_record['seed']} | {prompt_version} | "
                f"{summary['num_examples']} | {summary['official_score']} | "
                f"{summary['relaxed_extractable_score']} | {summary['format_loss_count']} | "
                f"{summary['reasoning_error_count']} | {summary['empty_or_invalid_count']} |"
            )
    return lines


def render_report(payload: dict[str, Any]) -> str:
    metadata = payload["metadata"]
    analysis = payload["analysis"]
    lines = [
        "# AIME official_budget answer extractability 只读审计结果",
        "",
        "## 文档定位",
        "",
        "- 本报告只读分析既有 `per_example_eval.jsonl`。",
        "- 本报告不调用模型、不调用 API、不调用 GEPA、不运行新实验。",
        "- 本报告不修改 official evaluator，也不替换 official score。",
        "- `relaxed_extractable_score` 仅用于诊断 reasoning ability 与 output-protocol adherence 的混合问题。",
        "",
        "## 审计边界标识",
        "",
    ]
    for key, value in metadata.items():
        if isinstance(value, bool):
            lines.append(f"- `{key} = {str(value).lower()}`")

    lines.extend(
        [
            "",
            "## 分类定义",
            "",
            "- `official_correct`: official score 为 1。",
            "- `format_loss`: official score 为 0，但保守提取出的最终答案与 gold 一致。",
            "- `reasoning_error`: official score 为 0，且可提取答案与 gold 不一致。",
            "- `empty_or_invalid`: official score 为 0，且 prediction 为空或无法提取最终答案。",
            "- `relaxed_extractable_score = (official_correct + format_loss) / examples`。",
            "",
            "注意：`relaxed_extractable_score` 是 diagnostic only，不是 official GEPA score。",
            "",
            "## 总体结果",
            "",
        ]
    )
    lines.extend(render_summary_table(payload))
    lines.extend(
        [
            "",
            "## 按 seed 明细",
            "",
        ]
    )
    lines.extend(render_run_table(payload))
    lines.extend(
        [
            "",
            "## 结果解释",
            "",
            f"- `official_score_gain = {analysis['official_score_gain']}`",
            f"- `relaxed_extractable_score_gain = {analysis['relaxed_extractable_score_gain']}`",
            f"- `seed_format_loss_count_minus_optimized = {analysis['seed_format_loss_count_minus_optimized']}`",
            f"- `score_gain_is_not_pure_reasoning_improvement = {str(analysis['score_gain_is_not_pure_reasoning_improvement']).lower()}`",
            f"- `official_score_remains_primary = {str(analysis['official_score_remains_primary']).lower()}`",
            "",
            "这说明 official score 可以作为当前 GEPA/AIME evaluator 下的正式任务分数使用，但不能直接解释为纯数学推理能力。分数提升同时包含任务求解行为改进和输出协议遵循改进。",
            "",
            "## 结论边界",
            "",
            "- 可以写：official score 衡量的是当前 evaluator 下的任务表现。",
            "- 可以写：seed prompt 的 format loss 明显多于 optimized prompt。",
            "- 可以写：observed score gain should not be interpreted as pure reasoning improvement。",
            "- 不能写：relaxed score 是 official GEPA score。",
            "- 不能写：relaxed score 可以替代 official score。",
            "- 不能写：所有提升都来自格式。",
            "- 不能写：所有提升都来自推理能力。",
            "- 不能写：这是新实验或新性能评估。",
        ]
    )
    return "\n".join(lines) + "\n"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="只读审计 AIME official_budget answer extractability 与 score decomposition。"
    )
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="项目根目录。")
    parser.add_argument(
        "--output-root",
        default="outputs/aime_official_budget_answer_extractability_audit",
        help="审计 JSON 输出根目录；该目录不应提交。",
    )
    parser.add_argument(
        "--report-path",
        default="reports/aime_official_budget_answer_extractability_audit_result.md",
        help="审计结果报告路径。",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    payload = build_audit_payload(project_root, DEFAULT_RUNS)

    audit_dir = project_root / args.output_root / payload["metadata"]["generated_at"]
    output_path = audit_dir / "answer_extractability_audit.json"
    report_path = project_root / args.report_path

    write_json(output_path, payload)
    write_text(report_path, render_report(payload))

    print(f"[OK] audit JSON: {output_path}")
    print(f"[OK] report: {report_path}")


if __name__ == "__main__":
    main()
