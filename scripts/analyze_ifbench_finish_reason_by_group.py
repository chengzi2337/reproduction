from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "reports" / "replay_aggregates"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "reports" / "ifbench_qwen3_finish_reason_by_group.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "reports" / "ifbench_qwen3_finish_reason_by_group.md"


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def mean_score(row: dict[str, Any]) -> float:
    scores = row.get("scores")
    if isinstance(scores, dict) and scores:
        return mean(as_float(value) for value in scores.values())
    value = row.get("metric_output")
    return as_float(value)


def flatten_finish_reasons(value: Any) -> list[str]:
    reasons: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            reasons.extend(flatten_finish_reasons(item))
    elif isinstance(value, list):
        for item in value:
            reasons.extend(flatten_finish_reasons(item))
    elif value is not None:
        reasons.append(str(value))
    return reasons


def count_parse_failures(value: Any) -> int:
    if isinstance(value, dict):
        return sum(1 for item in value.values() if bool(item))
    if isinstance(value, list):
        return sum(1 for item in value if bool(item))
    return int(bool(value))


def infer_variant(path: Path, aggregate: dict[str, Any]) -> str:
    haystack = " ".join(
        str(part).lower()
        for part in [
            path.name,
            aggregate.get("replay_tag"),
            aggregate.get("replay_kind"),
            aggregate.get("source_run_dir"),
        ]
    )
    if "p2" in haystack:
        return "p2"
    if "mhc" in haystack:
        return "mhc"
    if "baseline" in haystack:
        return "baseline"
    if "gepa" in haystack or "optimized" in haystack:
        return "gepa"
    return "unknown"


def infer_program_name(path: Path) -> str:
    parts = path.stem.split("_")
    for part in parts:
        if part.endswith("Program"):
            return part
    return "unknown"


def make_empty_aggregate(path: Path, error: str) -> dict[str, Any]:
    return {
        "aggregate": path.name,
        "path": str(path),
        "status": "empty_or_unreadable",
        "error": error,
        "program": infer_program_name(path),
        "replay_tag": None,
        "temperature": None,
        "top_p": None,
        "repetitions": None,
        "replay_kind": None,
        "variant": "unknown",
        "finish_reason_capture_status": "unknown",
        "finish_reason_captured": False,
        "total_stop": 0,
        "total_length": 0,
        "total_other_finish_reason": 0,
        "provider_rejection_events": 0,
        "parse_failure_count": 0,
        "length_groups": [],
        "groups": {},
    }


def summarize_group_entry(entry: dict[str, Any]) -> dict[str, Any]:
    length_scores = entry.pop("_length_scores")
    return {
        "sample_count": entry["sample_count"],
        "stop_count": entry["stop_count"],
        "length_count": entry["length_count"],
        "other_finish_reason_count": entry["other_finish_reason_count"],
        "length_sample_ids": entry["length_sample_ids"],
        "length_sample_scores": entry["length_sample_scores"],
        "length_sample_average_score": round(mean(length_scores), 6)
        if length_scores
        else None,
    }


def analyze_aggregate(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size == 0:
            return make_empty_aggregate(path, "文件为空")
        with path.open("r", encoding="utf-8") as handle:
            aggregate = json.load(handle)
        if not isinstance(aggregate, dict):
            return make_empty_aggregate(path, "JSON 顶层不是对象")
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return make_empty_aggregate(path, f"{type(exc).__name__}: {exc}")

    rows = aggregate.get("sample_level_score_matrix")
    if not isinstance(rows, list):
        return make_empty_aggregate(path, "缺少 sample_level_score_matrix")

    groups: dict[str, dict[str, Any]] = {}
    total_stop = 0
    total_length = 0
    total_other = 0
    parse_failure_count = 0

    for row in rows:
        if not isinstance(row, dict):
            continue
        group = str(row.get("instruction_group") or "unknown")
        sample_id = row.get("example_key", row.get("idx_in_split"))
        score = mean_score(row)
        reasons = flatten_finish_reasons(row.get("finish_reasons"))
        reason_counts = Counter(reasons)
        stop_count = int(reason_counts.get("stop", 0))
        length_count = int(reason_counts.get("length", 0))
        other_count = len(reasons) - stop_count - length_count
        parse_failure_count += count_parse_failures(row.get("parse_failures"))
        total_stop += stop_count
        total_length += length_count
        total_other += other_count

        entry = groups.setdefault(
            group,
            {
                "sample_count": 0,
                "stop_count": 0,
                "length_count": 0,
                "other_finish_reason_count": 0,
                "length_sample_ids": [],
                "length_sample_scores": [],
                "_length_scores": [],
            },
        )
        entry["sample_count"] += 1
        entry["stop_count"] += stop_count
        entry["length_count"] += length_count
        entry["other_finish_reason_count"] += other_count
        if length_count > 0:
            entry["length_sample_ids"].append(sample_id)
            entry["length_sample_scores"].append(
                {
                    "sample_id": sample_id,
                    "mean_score": round(score, 6),
                    "length_count": length_count,
                }
            )
            entry["_length_scores"].append(score)

    summarized_groups = {
        group: summarize_group_entry(entry)
        for group, entry in sorted(groups.items())
    }
    length_groups = [
        group
        for group, entry in summarized_groups.items()
        if entry["length_count"] > 0
    ]
    capture_status = str(aggregate.get("finish_reason_capture_status") or "unknown")
    return {
        "aggregate": path.name,
        "path": str(path),
        "status": "ok",
        "program": infer_program_name(path),
        "replay_tag": aggregate.get("replay_tag"),
        "temperature": aggregate.get("temperature"),
        "top_p": aggregate.get("top_p"),
        "repetitions": aggregate.get("repetitions"),
        "replay_kind": aggregate.get("replay_kind"),
        "variant": infer_variant(path, aggregate),
        "finish_reason_capture_status": capture_status,
        "finish_reason_captured": capture_status == "captured",
        "total_stop": total_stop,
        "total_length": total_length,
        "total_other_finish_reason": total_other,
        "provider_rejection_events": int(aggregate.get("provider_rejection_events") or 0),
        "parse_failure_count": parse_failure_count,
        "length_groups": length_groups,
        "groups": summarized_groups,
    }


def sample_score_by_length_status(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("sample_level_score_matrix")
    if not isinstance(rows, list):
        return {
            "length_sample_count": 0,
            "non_length_sample_count": 0,
            "length_sample_average_score": None,
            "non_length_sample_average_score": None,
        }
    length_scores: list[float] = []
    non_length_scores: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        score = mean_score(row)
        has_length = "length" in flatten_finish_reasons(row.get("finish_reasons"))
        if has_length:
            length_scores.append(score)
        else:
            non_length_scores.append(score)
    return {
        "length_sample_count": len(length_scores),
        "non_length_sample_count": len(non_length_scores),
        "length_sample_average_score": round(mean(length_scores), 6)
        if length_scores
        else None,
        "non_length_sample_average_score": round(mean(non_length_scores), 6)
        if non_length_scores
        else None,
    }


def build_p2_audit(aggregates: list[dict[str, Any]]) -> dict[str, Any]:
    p2_rows = [
        row
        for row in aggregates
        if row.get("status") == "ok" and row.get("variant") == "p2"
    ]
    if not p2_rows:
        return {
            "status": "not_found",
            "message": "未找到 P2 aggregate。",
        }
    p2 = max(p2_rows, key=lambda row: int(row.get("total_length") or 0))
    group_lengths = {
        group: entry["length_count"]
        for group, entry in p2["groups"].items()
        if entry["length_count"] > 0
    }
    score_status = sample_score_by_length_status(Path(str(p2["path"])))
    total_length = int(p2.get("total_length") or 0)
    dominant_group = None
    dominant_share = None
    if group_lengths and total_length:
        dominant_group, dominant_length = max(group_lengths.items(), key=lambda item: item[1])
        dominant_share = round(dominant_length / total_length, 6)
    length_avg = score_status["length_sample_average_score"]
    non_length_avg = score_status["non_length_sample_average_score"]
    score_gap = (
        round(float(length_avg) - float(non_length_avg), 6)
        if length_avg is not None and non_length_avg is not None
        else None
    )
    return {
        "status": "ok",
        "aggregate": p2["aggregate"],
        "total_length_events": total_length,
        "length_groups": group_lengths,
        "dominant_length_group": dominant_group,
        "dominant_length_group_share": dominant_share,
        **score_status,
        "length_minus_non_length_average_score": score_gap,
    }


def build_report(input_dir: Path) -> dict[str, Any]:
    aggregate_paths = sorted(input_dir.glob("*.json"))
    aggregates = [analyze_aggregate(path) for path in aggregate_paths]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_dir": str(input_dir),
        "aggregate_count": len(aggregates),
        "aggregates": aggregates,
        "p2_length_event_audit": build_p2_audit(aggregates),
    }


def format_optional(value: Any) -> str:
    return "None" if value is None else str(value)


def write_markdown(report: dict[str, Any], output_path: Path) -> None:
    lines = [
        "# IFBench/Qwen3 finish_reason 分组审计",
        "",
        "本报告只读取 `reports/replay_aggregates/*.json`，不调用模型 API，不修改实验原始数据。",
        "",
        "## 汇总表",
        "",
        "| aggregate | variant | temperature | repetitions | stop | length | provider rejects | parse failures | length groups |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report["aggregates"]:
        lines.append(
            "| {aggregate} | {variant} | {temperature} | {repetitions} | {stop} | {length} | {rejects} | {parse} | {groups} |".format(
                aggregate=row["aggregate"],
                variant=row["variant"],
                temperature=format_optional(row.get("temperature")),
                repetitions=format_optional(row.get("repetitions")),
                stop=row["total_stop"],
                length=row["total_length"],
                rejects=row["provider_rejection_events"],
                parse=row["parse_failure_count"],
                groups=", ".join(row["length_groups"]) if row["length_groups"] else "-",
            )
        )

    lines.extend(
        [
            "",
            "## P2 length event audit",
            "",
        ]
    )
    p2 = report["p2_length_event_audit"]
    if p2["status"] != "ok":
        lines.append(f"- 状态：`{p2['status']}`，{p2.get('message', '')}")
    else:
        lines.extend(
            [
                f"- P2 aggregate：`{p2['aggregate']}`",
                f"- length 事件总数：`{p2['total_length_events']}`",
                f"- length 涉及 group：`{p2['length_groups']}`",
                f"- length 最多的 group：`{p2['dominant_length_group']}`，占比 `{p2['dominant_length_group_share']}`",
                f"- 含 length 样本均分：`{p2['length_sample_average_score']}`，非 length 样本均分：`{p2['non_length_sample_average_score']}`",
                f"- 含 length 样本均分差：`{p2['length_minus_non_length_average_score']}`",
                "- 解释边界：这些数字只能说明 length 事件在当前 aggregate 中的分布和同批样本得分差异，不能单独证明截断是低分的因果原因。",
            ]
        )

    lines.extend(
        [
            "",
            "## 分组明细",
            "",
        ]
    )
    for row in report["aggregates"]:
        lines.extend(
            [
                f"### {row['aggregate']}",
                "",
                f"- 状态：`{row['status']}`",
                f"- finish_reason 捕获状态：`{row['finish_reason_capture_status']}`",
                "",
                "| group | samples | stop | length | other | length sample average | length sample ids |",
                "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for group, entry in row["groups"].items():
            ids = ", ".join(str(item) for item in entry["length_sample_ids"])
            lines.append(
                f"| {group} | {entry['sample_count']} | {entry['stop_count']} | {entry['length_count']} | "
                f"{entry['other_finish_reason_count']} | {format_optional(entry['length_sample_average_score'])} | {ids or '-'} |"
            )
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按 instruction group 审计 IFBench/Qwen3 finish_reason。")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(Path(args.input_dir))
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report, Path(args.output_md))
    print(
        json.dumps(
            {
                "output_json": str(output_json),
                "output_md": str(Path(args.output_md)),
                "aggregate_count": report["aggregate_count"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
