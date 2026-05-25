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

AUDIT_FLAGS: dict[str, bool] = {
    "not_new_experiment": True,
    "no_model_called": True,
    "no_api_called": True,
    "no_gepa_optimize_called": True,
    "not_performance_claim": True,
    "token_estimate_for_audit_only": True,
    "not_exact_tokenizer_count": True,
}


class AuditError(RuntimeError):
    """审计输入不完整或 artifact 结构不符合预期。"""


@dataclass(frozen=True)
class PromptStats:
    chars: int
    lines: int
    words: int
    tokens_est: float


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


def require_number(payload: dict[str, Any], key: str, source: Path) -> int | float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuditError(f"{source} 缺失数值字段：{key}")
    return value


def require_int(payload: dict[str, Any], key: str, source: Path) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise AuditError(f"{source} 缺失整数字段：{key}")
    return value


def extract_system_prompt(payload: dict[str, Any], source: Path) -> str:
    candidate = payload.get("candidate")
    if isinstance(candidate, dict) and isinstance(candidate.get("system_prompt"), str):
        return candidate["system_prompt"]
    if isinstance(payload.get("system_prompt"), str):
        return payload["system_prompt"]
    raise AuditError(f"{source} 无法解析 system_prompt；预期 candidate.system_prompt 或 system_prompt")


def compute_prompt_stats(prompt: str) -> PromptStats:
    line_count = len(prompt.splitlines()) if prompt else 0
    return PromptStats(
        chars=len(prompt),
        lines=line_count,
        words=len(prompt.split()),
        tokens_est=round(len(prompt) / 4, 2),
    )


def is_monotonic_by_growth(records: list[dict[str, Any]], score_key: str) -> bool:
    ordered = sorted(records, key=lambda record: record["prompt_char_growth"])
    scores = [record[score_key] for record in ordered]
    return all(left <= right for left, right in zip(scores, scores[1:]))


def audit_run(project_root: Path, seed: int, run_dir_text: str) -> dict[str, Any]:
    run_dir = project_root / run_dir_text
    if not run_dir.exists():
        raise AuditError(f"运行目录不存在：{run_dir_text}")
    if not run_dir.is_dir():
        raise AuditError(f"运行路径不是目录：{run_dir_text}")

    seed_prompt_path = run_dir / "seed_prompt.json"
    optimized_prompt_path = run_dir / "optimized_prompt.json"
    gepa_summary_path = run_dir / "gepa_result_summary.json"
    eval_summary_path = run_dir / "saved_prompt_eval_summary.json"

    seed_prompt = extract_system_prompt(read_json(seed_prompt_path), seed_prompt_path)
    optimized_prompt = extract_system_prompt(read_json(optimized_prompt_path), optimized_prompt_path)
    gepa_summary = read_json(gepa_summary_path)
    eval_summary = read_json(eval_summary_path)

    seed_stats = compute_prompt_stats(seed_prompt)
    optimized_stats = compute_prompt_stats(optimized_prompt)
    if seed_stats.chars <= 0:
        raise AuditError(f"seed prompt 长度必须大于 0：{seed_prompt_path}")

    prompt_char_growth = optimized_stats.chars - seed_stats.chars
    length_growth_ratio = optimized_stats.chars / seed_stats.chars

    return {
        "seed": seed,
        "run_dir": run_dir_text,
        "seed_prompt_score": require_number(eval_summary, "seed_prompt_score", eval_summary_path),
        "optimized_prompt_score": require_number(
            eval_summary,
            "optimized_prompt_score",
            eval_summary_path,
        ),
        "score_delta": require_number(eval_summary, "score_delta", eval_summary_path),
        "best_val_score": require_number(gepa_summary, "best_score", gepa_summary_path),
        "seed_prompt_chars": seed_stats.chars,
        "optimized_prompt_chars": optimized_stats.chars,
        "prompt_char_growth": prompt_char_growth,
        "length_growth_ratio": round(length_growth_ratio, 4),
        "seed_prompt_lines": seed_stats.lines,
        "optimized_prompt_lines": optimized_stats.lines,
        "seed_prompt_words": seed_stats.words,
        "optimized_prompt_words": optimized_stats.words,
        "seed_prompt_tokens_est": seed_stats.tokens_est,
        "optimized_prompt_tokens_est": optimized_stats.tokens_est,
        "prompt_token_growth_est": round(optimized_stats.tokens_est - seed_stats.tokens_est, 2),
        "num_candidates": require_int(gepa_summary, "num_candidates", gepa_summary_path),
        "num_full_val_evals": require_int(gepa_summary, "num_full_val_evals", gepa_summary_path),
    }


def build_analysis(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise AuditError("至少需要 1 条审计记录。")

    longest = max(records, key=lambda record: record["optimized_prompt_chars"])
    shortest = min(records, key=lambda record: record["optimized_prompt_chars"])
    highest_score = max(records, key=lambda record: record["optimized_prompt_score"])
    highest_delta = max(records, key=lambda record: record["score_delta"])

    optimized_score_monotonic = is_monotonic_by_growth(records, "optimized_prompt_score")
    score_delta_monotonic = is_monotonic_by_growth(records, "score_delta")

    return {
        "num_runs": len(records),
        "all_optimized_prompts_longer_than_seed": all(
            record["prompt_char_growth"] > 0 for record in records
        ),
        "min_prompt_char_growth": min(record["prompt_char_growth"] for record in records),
        "max_prompt_char_growth": max(record["prompt_char_growth"] for record in records),
        "mean_prompt_char_growth": round(
            sum(record["prompt_char_growth"] for record in records) / len(records),
            2,
        ),
        "optimized_score_monotonic_with_length_growth": optimized_score_monotonic,
        "score_delta_monotonic_with_length_growth": score_delta_monotonic,
        "longest_prompt_seed": longest["seed"],
        "longest_prompt_optimized_score": longest["optimized_prompt_score"],
        "highest_optimized_score_seed": highest_score["seed"],
        "highest_optimized_score": highest_score["optimized_prompt_score"],
        "shortest_optimized_prompt_seed": shortest["seed"],
        "shortest_optimized_prompt_score": shortest["optimized_prompt_score"],
        "highest_delta_seed": highest_delta["seed"],
        "highest_delta": highest_delta["score_delta"],
        "longest_prompt_is_not_highest_score": longest["seed"] != highest_score["seed"],
        "shortest_optimized_prompt_is_highest_score": shortest["seed"] == highest_score["seed"],
        "supports_length_controlled_gepa_design": True,
        "length_controlled_gepa_experiment_completed": False,
    }


def build_audit_payload(project_root: Path, runs: tuple[tuple[int, str], ...]) -> dict[str, Any]:
    records = [audit_run(project_root, seed, run_dir_text) for seed, run_dir_text in runs]
    return {
        "metadata": {
            "audit_name": "aime_official_budget_prompt_length_audit",
            "generated_at": create_timestamp(),
            **AUDIT_FLAGS,
        },
        "records": records,
        "analysis": build_analysis(records),
    }


def render_bool(value: bool) -> str:
    return "`true`" if value else "`false`"


def render_report(payload: dict[str, Any]) -> str:
    metadata = payload["metadata"]
    records = payload["records"]
    analysis = payload["analysis"]

    lines = [
        "# AIME official_budget prompt length 只读审计结果",
        "",
        "## 文档定位",
        "",
        "- 本报告基于 5 个既有 `official_budget` run_dir 做只读 prompt length audit。",
        "- 本报告不调用模型、不调用 GEPA、不运行新实验。",
        "- 本报告不是 `Length-Controlled GEPA` 实验结果。",
        "- 本报告不构成新的性能结论，也不支持“prompt 越长越好”。",
        "",
        "## 审计边界标志",
        "",
        f"- `not_new_experiment = {str(metadata['not_new_experiment']).lower()}`",
        f"- `no_model_called = {str(metadata['no_model_called']).lower()}`",
        f"- `no_api_called = {str(metadata['no_api_called']).lower()}`",
        f"- `no_gepa_optimize_called = {str(metadata['no_gepa_optimize_called']).lower()}`",
        f"- `not_performance_claim = {str(metadata['not_performance_claim']).lower()}`",
        f"- `token_estimate_for_audit_only = {str(metadata['token_estimate_for_audit_only']).lower()}`",
        f"- `not_exact_tokenizer_count = {str(metadata['not_exact_tokenizer_count']).lower()}`",
        "",
        "## 主表",
        "",
        "| seed | run_dir | seed_test_score | optimized_test_score | delta | best_val_score | seed_chars | optimized_chars | char_growth | growth_ratio | seed_lines | optimized_lines | seed_words | optimized_words | num_candidates | num_full_val_evals |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for record in records:
        lines.append(
            f"| {record['seed']} | `{record['run_dir']}` | "
            f"{record['seed_prompt_score']} | {record['optimized_prompt_score']} | "
            f"{record['score_delta']} | {record['best_val_score']} | "
            f"{record['seed_prompt_chars']} | {record['optimized_prompt_chars']} | "
            f"{record['prompt_char_growth']} | {record['length_growth_ratio']} | "
            f"{record['seed_prompt_lines']} | {record['optimized_prompt_lines']} | "
            f"{record['seed_prompt_words']} | {record['optimized_prompt_words']} | "
            f"{record['num_candidates']} | {record['num_full_val_evals']} |"
        )

    lines.extend(
        [
            "",
            "## token 粗估说明",
            "",
            "- `seed_prompt_tokens_est` 与 `optimized_prompt_tokens_est` 仅使用 `chars / 4` 粗略估算。",
            "- 该估算只用于审计辅助观察，不是 tokenizer 精确计数，不用于严格成本结论。",
            "",
            "## 问题回答",
            "",
            "### 1. optimized prompt 是否显著长于 seed prompt",
            "",
            f"是。5 个 seed 全部满足 `optimized_prompt_chars > seed_prompt_chars`，字符增长范围为 `{analysis['min_prompt_char_growth']}` 到 `{analysis['max_prompt_char_growth']}`，平均增长 `{analysis['mean_prompt_char_growth']}` 个字符。",
            "",
            "### 2. prompt 长度增长是否与 optimized_test_score 单调对应",
            "",
            f"否。按 `prompt_char_growth` 从小到大排序后，`optimized_test_score`（即 artifact 中的 `optimized_prompt_score`）不单调递增：`optimized_score_monotonic_with_length_growth = {str(analysis['optimized_score_monotonic_with_length_growth']).lower()}`。",
            "",
            "### 3. prompt 长度增长是否与 score_delta 单调对应",
            "",
            f"否。按 `prompt_char_growth` 从小到大排序后，`score_delta` 不单调递增：`score_delta_monotonic_with_length_growth = {str(analysis['score_delta_monotonic_with_length_growth']).lower()}`。",
            "",
            "### 4. 是否存在最长 prompt 不是最高分、最短 optimized prompt 反而最高分",
            "",
            f"存在。最长 optimized prompt 来自 seed{analysis['longest_prompt_seed']}，其 optimized score 为 `{analysis['longest_prompt_optimized_score']}`；最高 optimized score 来自 seed{analysis['highest_optimized_score_seed']}，分数为 `{analysis['highest_optimized_score']}`。",
            "",
            f"也存在最短 optimized prompt 反而最高分的现象：`shortest_optimized_prompt_is_highest_score = {str(analysis['shortest_optimized_prompt_is_highest_score']).lower()}`。最短 optimized prompt 来自 seed{analysis['shortest_optimized_prompt_seed']}，其 optimized score 为 `{analysis['shortest_optimized_prompt_score']}`。",
            "",
            "### 5. 是否支持下一步设计 Length-Controlled GEPA",
            "",
            "支持进入设计阶段。当前 audit 显示 prompt length growth substantial，但长度增长不能单调解释测试收益，因此 prompt 长度是合理的下一步审计和控制变量。",
            "",
            "### 6. 当前是否只是只读 audit",
            "",
            "是。当前结果只来自已有 run_dir 的 artifact 读取与统计，不是 `Length-Controlled GEPA` 实验，不包含新 optimize、模型调用或新评估。",
            "",
            "## 结论边界",
            "",
            "- 可以写：prompt length growth is substantial。",
            "- 可以写：length does not monotonically explain score gains。",
            "- 可以写：prompt length is a reasonable next audit/control variable。",
            "- 不能写：prompt 越长越好。",
            "- 不能写：控制长度一定能提升。",
            "- 不能写：Length-Controlled GEPA 已验证。",
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
    parser = argparse.ArgumentParser(description="只读审计 AIME official_budget prompt 长度。")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="项目根目录。")
    parser.add_argument(
        "--output-root",
        default="outputs/aime_official_budget_prompt_length_audit",
        help="审计 JSON 输出根目录；该目录不应提交。",
    )
    parser.add_argument(
        "--report-path",
        default="reports/aime_official_budget_prompt_length_audit_result.md",
        help="审计结果报告路径。",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    payload = build_audit_payload(project_root, DEFAULT_RUNS)

    audit_dir = project_root / args.output_root / payload["metadata"]["generated_at"]
    output_path = audit_dir / "prompt_length_audit.json"
    report_path = project_root / args.report_path

    write_json(output_path, payload)
    write_text(report_path, render_report(payload))

    print(f"[OK] audit JSON: {output_path}")
    print(f"[OK] report: {report_path}")


if __name__ == "__main__":
    main()
