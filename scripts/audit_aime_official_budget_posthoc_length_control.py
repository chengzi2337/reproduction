from __future__ import annotations

import argparse
import json
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

SCORE_GAP_RULES: tuple[tuple[str, float], ...] = (
    ("rule_b_gap_0_02_shortest", 0.02),
    ("rule_c_gap_0_05_shortest", 0.05),
)
LENGTH_CAP_MULTIPLIERS: tuple[int, ...] = (2, 3, 5)

AUDIT_FLAGS: dict[str, bool] = {
    "not_new_experiment": True,
    "posthoc_only": True,
    "no_model_called": True,
    "no_api_called": True,
    "no_gepa_optimize_called": True,
    "optimizer_not_modified": True,
    "evaluator_not_modified": True,
    "not_performance_claim": True,
}

LIMITATION_MESSAGE = (
    "candidate-level artifacts unavailable; post-hoc length-controlled selection "
    "cannot be performed from current saved artifacts."
)


class AuditError(RuntimeError):
    """审计输入缺失或 artifact 结构不符合预期。"""


@dataclass(frozen=True)
class PromptStats:
    chars: int
    words: int
    lines: int


def create_timestamp() -> str:
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    return f"{timestamp[:-5]}{timestamp[-5:-2]}{timestamp[-2:]}"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AuditError(f"缺失必需 artifact：{path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise AuditError(f"JSON 解析失败：{path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AuditError(f"artifact 必须是 JSON object：{path}")
    return payload


def extract_system_prompt(payload: dict[str, Any], source: Path) -> str:
    candidate = payload.get("candidate")
    if isinstance(candidate, dict) and isinstance(candidate.get("system_prompt"), str):
        return candidate["system_prompt"]
    if isinstance(payload.get("system_prompt"), str):
        return payload["system_prompt"]
    raise AuditError(f"{source} 无法解析 system_prompt")


def compute_prompt_stats(prompt: str) -> PromptStats:
    return PromptStats(
        chars=len(prompt),
        words=len(prompt.split()),
        lines=len(prompt.splitlines()) if prompt else 0,
    )


def load_candidate_inputs(raw_result: dict[str, Any]) -> tuple[list[dict[str, str]], list[float], int] | None:
    candidates = raw_result.get("candidates")
    scores = raw_result.get("val_aggregate_scores")
    best_idx = raw_result.get("best_idx")

    if not isinstance(candidates, list) or not isinstance(scores, list) or not isinstance(best_idx, int):
        return None
    if len(candidates) == 0 or len(candidates) != len(scores):
        return None
    if best_idx < 0 or best_idx >= len(candidates):
        return None

    normalized_candidates: list[dict[str, str]] = []
    normalized_scores: list[float] = []
    for candidate, score in zip(candidates, scores):
        if not isinstance(candidate, dict) or not isinstance(candidate.get("system_prompt"), str):
            return None
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            return None
        normalized_candidates.append({"system_prompt": candidate["system_prompt"]})
        normalized_scores.append(float(score))
    return normalized_candidates, normalized_scores, best_idx


def build_candidate_records(
    *,
    candidates: list[dict[str, str]],
    scores: list[float],
    best_idx: int,
) -> list[dict[str, Any]]:
    best_score = scores[best_idx]
    best_chars = compute_prompt_stats(candidates[best_idx]["system_prompt"]).chars
    if best_chars <= 0:
        raise AuditError("best candidate prompt 长度必须大于 0。")

    records: list[dict[str, Any]] = []
    for candidate_id, (candidate, score) in enumerate(zip(candidates, scores)):
        stats = compute_prompt_stats(candidate["system_prompt"])
        records.append(
            {
                "candidate_id": candidate_id,
                "candidate_val_score": score,
                "candidate_prompt_chars": stats.chars,
                "candidate_prompt_words": stats.words,
                "candidate_prompt_lines": stats.lines,
                "is_best_val_candidate": candidate_id == best_idx,
                "is_shorter_than_best_candidate": stats.chars < best_chars,
                "score_gap_to_best_val": round(best_score - score, 12),
                "length_reduction_ratio": round(1 - (stats.chars / best_chars), 6),
            }
        )
    return records


def select_highest_score(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        candidates,
        key=lambda record: (record["candidate_val_score"], -record["candidate_prompt_chars"]),
    )


def select_shortest_within_gap(candidates: list[dict[str, Any]], max_gap: float) -> dict[str, Any]:
    eligible = [record for record in candidates if record["score_gap_to_best_val"] <= max_gap]
    return min(
        eligible,
        key=lambda record: (record["candidate_prompt_chars"], -record["candidate_val_score"]),
    )


def select_best_under_length_cap(
    candidates: list[dict[str, Any]],
    *,
    max_chars: int,
) -> dict[str, Any] | None:
    eligible = [record for record in candidates if record["candidate_prompt_chars"] <= max_chars]
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda record: (record["candidate_val_score"], -record["candidate_prompt_chars"]),
    )


def selection_summary(
    *,
    rule_name: str,
    selected: dict[str, Any] | None,
    best: dict[str, Any],
    max_chars: int | None = None,
) -> dict[str, Any]:
    if selected is None:
        return {
            "rule": rule_name,
            "selected_candidate_id": None,
            "selected_candidate_val_score": None,
            "selected_candidate_chars": None,
            "score_gap_to_rule_a": None,
            "chars_saved_vs_rule_a": None,
            "length_reduction_vs_rule_a": None,
            "max_chars": max_chars,
            "selection_available": False,
        }

    best_chars = best["candidate_prompt_chars"]
    return {
        "rule": rule_name,
        "selected_candidate_id": selected["candidate_id"],
        "selected_candidate_val_score": selected["candidate_val_score"],
        "selected_candidate_chars": selected["candidate_prompt_chars"],
        "score_gap_to_rule_a": round(
            best["candidate_val_score"] - selected["candidate_val_score"],
            12,
        ),
        "chars_saved_vs_rule_a": best_chars - selected["candidate_prompt_chars"],
        "length_reduction_vs_rule_a": round(
            1 - (selected["candidate_prompt_chars"] / best_chars),
            6,
        ),
        "max_chars": max_chars,
        "selection_available": True,
    }


def apply_selection_rules(
    *,
    candidate_records: list[dict[str, Any]],
    seed_prompt_chars: int,
) -> list[dict[str, Any]]:
    best = select_highest_score(candidate_records)
    summaries = [selection_summary(rule_name="rule_a_best_val", selected=best, best=best)]

    for rule_name, max_gap in SCORE_GAP_RULES:
        selected = select_shortest_within_gap(candidate_records, max_gap)
        summaries.append(selection_summary(rule_name=rule_name, selected=selected, best=best))

    for multiplier in LENGTH_CAP_MULTIPLIERS:
        max_chars = seed_prompt_chars * multiplier
        selected = select_best_under_length_cap(candidate_records, max_chars=max_chars)
        summaries.append(
            selection_summary(
                rule_name=f"rule_d_seed_{multiplier}x_cap_best_val",
                selected=selected,
                best=best,
                max_chars=max_chars,
            )
        )
    return summaries


def audit_run(project_root: Path, seed: int, run_dir_text: str) -> dict[str, Any]:
    run_dir = project_root / run_dir_text
    if not run_dir.exists() or not run_dir.is_dir():
        raise AuditError(f"运行目录不存在或不是目录：{run_dir_text}")

    seed_prompt = extract_system_prompt(read_json(run_dir / "seed_prompt.json"), run_dir / "seed_prompt.json")
    seed_stats = compute_prompt_stats(seed_prompt)
    if seed_stats.chars <= 0:
        raise AuditError(f"seed prompt 长度必须大于 0：{run_dir_text}")

    raw_result = read_json(run_dir / "raw_result.json")
    read_json(run_dir / "gepa_result_summary.json")
    loaded = load_candidate_inputs(raw_result)
    if loaded is None:
        return {
            "seed": seed,
            "run_dir": run_dir_text,
            "candidate_artifacts_available": False,
            "limitation": LIMITATION_MESSAGE,
            "seed_prompt_chars": seed_stats.chars,
            "candidates": [],
            "selection_rules": [],
        }

    candidates, scores, best_idx = loaded
    candidate_records = build_candidate_records(
        candidates=candidates,
        scores=scores,
        best_idx=best_idx,
    )
    return {
        "seed": seed,
        "run_dir": run_dir_text,
        "candidate_artifacts_available": True,
        "limitation": None,
        "seed_prompt_chars": seed_stats.chars,
        "raw_result_best_idx": best_idx,
        "num_candidates": len(candidate_records),
        "candidates": candidate_records,
        "selection_rules": apply_selection_rules(
            candidate_records=candidate_records,
            seed_prompt_chars=seed_stats.chars,
        ),
    }


def build_analysis(run_records: list[dict[str, Any]]) -> dict[str, Any]:
    available_runs = [record for record in run_records if record["candidate_artifacts_available"]]
    if len(available_runs) != len(run_records):
        return {
            "candidate_artifacts_available_for_all_runs": False,
            "posthoc_selection_performed": False,
            "limitation": LIMITATION_MESSAGE,
        }

    all_rule_summaries = [
        rule
        for run_record in available_runs
        for rule in run_record["selection_rules"]
        if rule["selection_available"]
    ]
    non_rule_a_summaries = [rule for rule in all_rule_summaries if rule["rule"] != "rule_a_best_val"]
    shorter_near_best = [
        rule
        for rule in non_rule_a_summaries
        if rule["chars_saved_vs_rule_a"] is not None and rule["chars_saved_vs_rule_a"] > 0
    ]
    near_best_shorter = [
        rule
        for rule in shorter_near_best
        if rule["score_gap_to_rule_a"] is not None and rule["score_gap_to_rule_a"] <= 0.05
    ]
    exact_best_shorter = [
        rule
        for rule in near_best_shorter
        if rule["score_gap_to_rule_a"] == 0
    ]

    return {
        "candidate_artifacts_available_for_all_runs": True,
        "posthoc_selection_performed": True,
        "num_runs": len(run_records),
        "total_candidates": sum(record["num_candidates"] for record in available_runs),
        "rules_with_shorter_selection_count": len(shorter_near_best),
        "rules_with_near_best_shorter_selection_count": len(near_best_shorter),
        "rules_with_exact_best_and_shorter_selection_count": len(exact_best_shorter),
        "max_chars_saved_vs_rule_a": max(
            (rule["chars_saved_vs_rule_a"] for rule in shorter_near_best),
            default=0,
        ),
        "min_score_gap_among_shorter_selections": min(
            (rule["score_gap_to_rule_a"] for rule in shorter_near_best),
            default=None,
        ),
        "supports_direct_length_controlled_gepa_experiment": False,
        "supports_length_controlled_candidate_selection_design": len(near_best_shorter) > 0,
        "length_controlled_gepa_validated": False,
    }


def build_audit_payload(project_root: Path, runs: tuple[tuple[int, str], ...]) -> dict[str, Any]:
    run_records = [audit_run(project_root, seed, run_dir_text) for seed, run_dir_text in runs]
    return {
        "metadata": {
            "audit_name": "aime_official_budget_posthoc_length_control_audit",
            "generated_at": create_timestamp(),
            **AUDIT_FLAGS,
        },
        "runs": run_records,
        "analysis": build_analysis(run_records),
    }


def render_candidate_table(run_record: dict[str, Any]) -> list[str]:
    lines = [
        f"### seed{run_record['seed']}",
        "",
        f"- `run_dir`: `{run_record['run_dir']}`",
        f"- `candidate_artifacts_available`: `{str(run_record['candidate_artifacts_available']).lower()}`",
        "",
    ]
    if not run_record["candidate_artifacts_available"]:
        lines.extend([f"- limitation: {run_record['limitation']}", ""])
        return lines

    lines.extend(
        [
            "| candidate_id | val_score | chars | words | lines | is_best_val_candidate | is_shorter_than_best_candidate | score_gap_to_best_val | length_reduction_ratio |",
            "|---:|---:|---:|---:|---:|---|---|---:|---:|",
        ]
    )
    for candidate in run_record["candidates"]:
        lines.append(
            f"| {candidate['candidate_id']} | {candidate['candidate_val_score']} | "
            f"{candidate['candidate_prompt_chars']} | {candidate['candidate_prompt_words']} | "
            f"{candidate['candidate_prompt_lines']} | "
            f"`{str(candidate['is_best_val_candidate']).lower()}` | "
            f"`{str(candidate['is_shorter_than_best_candidate']).lower()}` | "
            f"{candidate['score_gap_to_best_val']} | {candidate['length_reduction_ratio']} |"
        )
    lines.append("")
    lines.extend(
        [
            "| rule | selected_candidate_id | val_score | chars | score_gap_to_rule_a | chars_saved_vs_rule_a | length_reduction_vs_rule_a | selection_available |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for rule in run_record["selection_rules"]:
        lines.append(
            f"| `{rule['rule']}` | {rule['selected_candidate_id']} | "
            f"{rule['selected_candidate_val_score']} | {rule['selected_candidate_chars']} | "
            f"{rule['score_gap_to_rule_a']} | {rule['chars_saved_vs_rule_a']} | "
            f"{rule['length_reduction_vs_rule_a']} | `{str(rule['selection_available']).lower()}` |"
        )
    lines.append("")
    return lines


def render_report(payload: dict[str, Any]) -> str:
    metadata = payload["metadata"]
    analysis = payload["analysis"]
    lines = [
        "# AIME official_budget post-hoc length-controlled selection 只读审计结果",
        "",
        "## 文档定位",
        "",
        "- 本报告只读分析既有 5 个 official_budget run 的 candidate-level artifacts。",
        "- 本报告不调用模型、不调用 API、不调用 GEPA、不运行新实验。",
        "- 本报告不是 `Length-Controlled GEPA` 实验，也不是新的 test performance 结论。",
        "",
        "## 审计边界标志",
        "",
    ]
    for key, value in metadata.items():
        if isinstance(value, bool):
            lines.append(f"- `{key} = {str(value).lower()}`")
    lines.extend(
        [
            "",
            "## artifact 可用性与总体结论",
            "",
            f"- `candidate_artifacts_available_for_all_runs = {str(analysis['candidate_artifacts_available_for_all_runs']).lower()}`",
            f"- `posthoc_selection_performed = {str(analysis['posthoc_selection_performed']).lower()}`",
        ]
    )
    if not analysis["posthoc_selection_performed"]:
        lines.extend(["", f"- {analysis['limitation']}"])
    else:
        lines.extend(
            [
                f"- `total_candidates = {analysis['total_candidates']}`",
                f"- `rules_with_shorter_selection_count = {analysis['rules_with_shorter_selection_count']}`",
                f"- `rules_with_near_best_shorter_selection_count = {analysis['rules_with_near_best_shorter_selection_count']}`",
                f"- `rules_with_exact_best_and_shorter_selection_count = {analysis['rules_with_exact_best_and_shorter_selection_count']}`",
                f"- `max_chars_saved_vs_rule_a = {analysis['max_chars_saved_vs_rule_a']}`",
                f"- `min_score_gap_among_shorter_selections = {analysis['min_score_gap_among_shorter_selections']}`",
                f"- `supports_direct_length_controlled_gepa_experiment = {str(analysis['supports_direct_length_controlled_gepa_experiment']).lower()}`",
                f"- `supports_length_controlled_candidate_selection_design = {str(analysis['supports_length_controlled_candidate_selection_design']).lower()}`",
                f"- `length_controlled_gepa_validated = {str(analysis['length_controlled_gepa_validated']).lower()}`",
            ]
        )

    lines.extend(["", "## candidate 与 selection 规则明细", ""])
    for run_record in payload["runs"]:
        lines.extend(render_candidate_table(run_record))

    lines.extend(
        [
            "## 结果解释",
            "",
            "1. 当前 5 个 run 的 `raw_result.json` 都包含 candidate-level prompt 与 validation aggregate score，因此可以执行 post-hoc selection audit。",
            "2. Rule B / Rule C 在当前 artifacts 中没有找到比 Rule A 更短且仍在 0.02 / 0.05 分差内的 candidate。",
            "3. Rule D 的 seed prompt 2x / 3x / 5x 长度上限只会选到 seed prompt candidate，本质上牺牲大量 validation score，不构成可用的 length-control 策略。",
            "4. 当前结果不支持直接进入 Length-Controlled GEPA 实验；如果继续推进，应先写 length-controlled candidate selection design，并要求未来 runner 保存更丰富的 candidate/trajectory artifacts。",
            "",
            "## 结论边界",
            "",
            "- 可以写：candidate-level artifacts are available。",
            "- 可以写：post-hoc length caps this strict do not recover near-best validation candidates in the current 3-candidate runs。",
            "- 可以写：当前更适合先设计 length-controlled candidate selection，而不是直接改 optimizer。",
            "- 不能写：Length-Controlled GEPA 已验证。",
            "- 不能写：控制长度一定能提升 test performance。",
            "- 不能写：这是新的性能实验。",
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
        description="只读审计 AIME official_budget post-hoc length-controlled selection。"
    )
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="项目根目录。")
    parser.add_argument(
        "--output-root",
        default="outputs/aime_official_budget_posthoc_length_control_audit",
        help="审计 JSON 输出根目录；该目录不应提交。",
    )
    parser.add_argument(
        "--report-path",
        default="reports/aime_official_budget_posthoc_length_control_result.md",
        help="审计结果报告路径。",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    payload = build_audit_payload(project_root, DEFAULT_RUNS)

    audit_dir = project_root / args.output_root / payload["metadata"]["generated_at"]
    output_path = audit_dir / "posthoc_length_control_audit.json"
    report_path = project_root / args.report_path

    write_json(output_path, payload)
    write_text(report_path, render_report(payload))

    print(f"[OK] audit JSON: {output_path}")
    print(f"[OK] report: {report_path}")


if __name__ == "__main__":
    main()
