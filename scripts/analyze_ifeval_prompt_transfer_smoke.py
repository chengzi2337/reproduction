from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ifeval_official_adapter import official_import_path
from src.ifeval_evaluation_utils import (
    CANONICAL_SUMMARY_SOURCE,
    compare_aggregates,
    evaluate_raw_outputs as evaluate_raw_outputs_common,
)
from src.logging_utils import write_json, write_text


DEFAULT_SMOKE_DIR = PROJECT_ROOT / "reports" / "ifeval_qwen3_smoke_limit20"
REQUIRED_INPUT_FILES = (
    "raw_outputs.jsonl",
    "eval_results.json",
    "summary.json",
    "provider_events.json",
    "run_config.json",
)
PAIRWISE_SPECS = (
    ("baseline_mhc", "baseline"),
    ("verbose_helpfulness", "baseline"),
    ("mhc_concise", "baseline_mhc"),
    ("gepa_p2_transfer", "ifbench_gepa_prompt_transfer"),
)
LANGDETECT_SEED = 0


class SmokeAuditError(RuntimeError):
    """离线 smoke 审计无法继续时抛出的结构化错误。"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="离线审计 IFEval prompt-transfer limit=20 smoke 结果。")
    parser.add_argument("--smoke-dir", default=str(DEFAULT_SMOKE_DIR))
    return parser.parse_args(argv)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise SmokeAuditError(f"{path.name}:{line_number} 不是 JSON object。")
            rows.append(payload)
    return rows


def validate_inputs(smoke_dir: Path) -> dict[str, Any]:
    missing = [name for name in REQUIRED_INPUT_FILES if not (smoke_dir / name).is_file()]
    return {
        "status": "ok" if not missing else "blocked",
        "missing_files": missing,
        "smoke_dir": smoke_dir.as_posix(),
    }


def normalize_variant(row: dict[str, Any]) -> str:
    return str(row.get("variant") or row.get("variant_id") or "")


def instruction_score(values: list[bool] | None) -> float | None:
    if values is None:
        return None
    if not values:
        return None
    return sum(1 for value in values if value) / len(values)


def output_to_payload(item: Any) -> dict[str, Any]:
    follow_list = [bool(value) for value in list(getattr(item, "follow_instruction_list", []))]
    return {
        "prompt_level_passed": bool(getattr(item, "follow_all_instructions", False)),
        "instruction_level_score": instruction_score(follow_list),
        "follow_instruction_list": follow_list,
        "instruction_id_list": list(getattr(item, "instruction_id_list", [])),
    }


def purge_official_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "instruction_following_eval" or module_name.startswith("instruction_following_eval."):
            del sys.modules[module_name]


def seed_language_detector() -> dict[str, Any]:
    try:
        from langdetect import DetectorFactory

        DetectorFactory.seed = LANGDETECT_SEED
        return {"langdetect_seed": LANGDETECT_SEED, "status": "set"}
    except Exception as exc:
        return {"langdetect_seed": None, "status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}


def run_official_checker(
    *,
    ifeval_root: Path,
    dataset_path: Path,
    raw_rows: list[dict[str, Any]],
    variants: list[str],
    limit: int,
) -> dict[tuple[int, str], dict[str, Any]]:
    purge_official_modules()
    seed_language_detector()
    with official_import_path(ifeval_root):
        evaluation_lib = importlib.import_module("instruction_following_eval.evaluation_lib")
        inputs = list(evaluation_lib.read_prompt_list(str(dataset_path)))[:limit]
        input_by_prompt = {item.prompt: item for item in inputs}

        checked: dict[tuple[int, str], dict[str, Any]] = {}
        rows_by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in raw_rows:
            rows_by_variant[normalize_variant(row)].append(row)

        for variant_id in variants:
            rows = sorted(rows_by_variant.get(variant_id, []), key=lambda item: int(item.get("sample_index", -1)))
            prompt_to_response = {str(row.get("prompt", "")): str(row.get("response", "")) for row in rows}
            for row in rows:
                sample_index = int(row.get("sample_index", -1))
                prompt = str(row.get("prompt", ""))
                if prompt not in input_by_prompt:
                    checked[(sample_index, variant_id)] = {
                        "checker_error": f"raw output prompt 不存在于 dataset limit: {sample_index}",
                    }
                    continue
                try:
                    input_example = input_by_prompt[prompt]
                    strict_output = evaluation_lib.test_instruction_following_strict(input_example, prompt_to_response)
                    loose_output = evaluation_lib.test_instruction_following_loose(input_example, prompt_to_response)
                    checked[(sample_index, variant_id)] = {
                        "strict": output_to_payload(strict_output),
                        "loose": output_to_payload(loose_output),
                        "checker_error": None,
                    }
                except Exception as exc:
                    checked[(sample_index, variant_id)] = {
                        "checker_error": f"{type(exc).__name__}: {exc}",
                    }
    return checked


def load_samples(dataset_path: Path, limit: int) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise SmokeAuditError("IFEval 数据行不是 JSON object。")
            samples.append(payload)
            if len(samples) >= limit:
                break
    return samples


def summarize_provider_rows(raw_rows: list[dict[str, Any]], provider_events: dict[str, Any]) -> dict[str, Any]:
    status_counts = Counter(str(row.get("provider_status") or "unknown") for row in raw_rows)
    events = [
        {
            "sample_index": row.get("sample_index"),
            "variant": normalize_variant(row),
            "provider_status": row.get("provider_status"),
            "provider_error": row.get("provider_error"),
        }
        for row in raw_rows
        if str(row.get("provider_status") or "unknown") != "ok"
    ]
    return {
        "provider_error_count": int(provider_events.get("provider_error_count", sum(status_counts.values()) - status_counts.get("ok", 0))),
        "provider_rejection_count": int(provider_events.get("provider_rejection_count", status_counts.get("provider_rejection", 0))),
        "timeout_count": int(provider_events.get("timeout_count", status_counts.get("timeout", 0))),
        "provider_status_counts": dict(status_counts),
        "events": provider_events.get("events") or events,
    }


def check_variant_sample_consistency(
    *,
    raw_rows: list[dict[str, Any]],
    variants: list[str],
    expected_sample_indexes: list[int],
) -> dict[str, Any]:
    rows_by_variant: dict[str, list[int]] = defaultdict(list)
    duplicate_rows: dict[str, list[int]] = {}
    for row in raw_rows:
        rows_by_variant[normalize_variant(row)].append(int(row.get("sample_index", -1)))

    expected_set = set(expected_sample_indexes)
    per_variant: dict[str, Any] = {}
    for variant_id in variants:
        indexes = rows_by_variant.get(variant_id, [])
        counts = Counter(indexes)
        duplicates = sorted(index for index, count in counts.items() if count > 1)
        missing = sorted(expected_set - set(indexes))
        extra = sorted(set(indexes) - expected_set)
        if duplicates:
            duplicate_rows[variant_id] = duplicates
        per_variant[variant_id] = {
            "row_count": len(indexes),
            "unique_sample_count": len(set(indexes)),
            "missing_sample_indexes": missing,
            "duplicate_sample_indexes": duplicates,
            "extra_sample_indexes": extra,
        }

    unexpected_variants = sorted(set(rows_by_variant) - set(variants))
    ok = (
        not unexpected_variants
        and all(not payload["missing_sample_indexes"] for payload in per_variant.values())
        and all(not payload["duplicate_sample_indexes"] for payload in per_variant.values())
        and all(not payload["extra_sample_indexes"] for payload in per_variant.values())
    )
    return {
        "status": "ok" if ok else "blocked",
        "expected_sample_indexes": expected_sample_indexes,
        "unexpected_variants": unexpected_variants,
        "duplicate_rows": duplicate_rows,
        "per_variant": per_variant,
    }


def build_matrix(
    *,
    samples: list[dict[str, Any]],
    raw_rows: list[dict[str, Any]],
    variants: list[str],
    checker_payloads: dict[tuple[int, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    row_lookup: dict[tuple[int, str], dict[str, Any]] = {}
    for row in raw_rows:
        row_lookup[(int(row.get("sample_index", -1)), normalize_variant(row))] = row

    matrix: list[dict[str, Any]] = []
    for sample_index, sample in enumerate(samples):
        matrix_row: dict[str, Any] = {
            "sample_index": sample_index,
            "sample_id": sample.get("key", sample_index),
            "prompt": sample.get("prompt"),
            "instruction_id_list": sample.get("instruction_id_list", []),
            "kwargs": sample.get("kwargs", []),
            "variants": {},
        }
        for variant_id in variants:
            raw_row = row_lookup.get((sample_index, variant_id), {})
            checker = checker_payloads.get((sample_index, variant_id), {"checker_error": "checker_result_missing"})
            strict = checker.get("strict") or {}
            loose = checker.get("loose") or {}
            response = str(raw_row.get("response", ""))
            matrix_row["variants"][variant_id] = {
                "raw_response": response,
                "response_character_length": len(response),
                "strict_prompt_passed": strict.get("prompt_level_passed"),
                "strict_instruction_score": strict.get("instruction_level_score"),
                "strict_follow_instruction_list": strict.get("follow_instruction_list"),
                "loose_prompt_passed": loose.get("prompt_level_passed"),
                "loose_instruction_score": loose.get("instruction_level_score"),
                "loose_follow_instruction_list": loose.get("follow_instruction_list"),
                "checker_error": checker.get("checker_error"),
                "provider_status": raw_row.get("provider_status"),
                "provider_error": raw_row.get("provider_error"),
                "finish_reason": raw_row.get("finish_reason"),
            }
        matrix.append(matrix_row)
    return matrix


def aggregate_variant_scores(matrix: list[dict[str, Any]], variants: list[str]) -> dict[str, Any]:
    per_variant: dict[str, Any] = {}
    for variant_id in variants:
        prompt_total = 0
        prompt_correct = 0
        instruction_total = 0
        instruction_correct = 0
        sample_count = 0
        checker_error_count = 0
        response_lengths: list[int] = []
        for row in matrix:
            payload = row["variants"][variant_id]
            sample_count += 1
            response_lengths.append(int(payload.get("response_character_length") or 0))
            if payload.get("checker_error"):
                checker_error_count += 1
            if payload.get("strict_prompt_passed") is not None:
                prompt_total += 1
                if payload.get("strict_prompt_passed"):
                    prompt_correct += 1
            score = payload.get("strict_instruction_score")
            follow_list = payload.get("strict_follow_instruction_list")
            if isinstance(follow_list, list):
                instruction_total += len(follow_list)
                instruction_correct += sum(1 for value in follow_list if value)
            elif score is not None:
                instruction_total += 1
                instruction_correct += float(score)
        per_variant[variant_id] = {
            "sample_count": sample_count,
            "prompt_level_accuracy": prompt_correct / prompt_total if prompt_total else None,
            "prompt_correct": prompt_correct,
            "prompt_total": prompt_total,
            "instruction_level_accuracy": instruction_correct / instruction_total if instruction_total else None,
            "instruction_correct": instruction_correct,
            "instruction_total": instruction_total,
            "checker_error_count": checker_error_count,
            "average_response_character_length": (
                sum(response_lengths) / len(response_lengths) if response_lengths else None
            ),
        }
    return per_variant


def safe_delta(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def short_text(text: str, limit: int = 360) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def compare_pair(
    *,
    matrix: list[dict[str, Any]],
    treatment: str,
    control: str,
    per_variant: dict[str, Any],
) -> dict[str, Any]:
    improved: list[int] = []
    degraded: list[int] = []
    tied: list[int] = []
    changed_audit: list[dict[str, Any]] = []

    for row in matrix:
        sample_index = int(row["sample_index"])
        control_payload = row["variants"][control]
        treatment_payload = row["variants"][treatment]
        control_prompt = control_payload.get("strict_prompt_passed")
        treatment_prompt = treatment_payload.get("strict_prompt_passed")
        control_instruction = control_payload.get("strict_instruction_score")
        treatment_instruction = treatment_payload.get("strict_instruction_score")

        prompt_delta = None
        if control_prompt is not None and treatment_prompt is not None:
            prompt_delta = int(bool(treatment_prompt)) - int(bool(control_prompt))
        instruction_delta = safe_delta(treatment_instruction, control_instruction)

        if (prompt_delta is not None and prompt_delta > 0) or (
            instruction_delta is not None and instruction_delta > 0
        ):
            improved.append(sample_index)
        elif (prompt_delta is not None and prompt_delta < 0) or (
            instruction_delta is not None and instruction_delta < 0
        ):
            degraded.append(sample_index)
        else:
            tied.append(sample_index)

        if sample_index in improved or sample_index in degraded:
            changed_audit.append(
                {
                    "sample_index": sample_index,
                    "sample_id": row.get("sample_id"),
                    "prompt": row.get("prompt"),
                    "instruction_id_list": row.get("instruction_id_list"),
                    "control_variant": control,
                    "treatment_variant": treatment,
                    "control_response": control_payload.get("raw_response"),
                    "treatment_response": treatment_payload.get("raw_response"),
                    "control_checker_result": {
                        "strict_prompt_passed": control_prompt,
                        "strict_instruction_score": control_instruction,
                        "loose_prompt_passed": control_payload.get("loose_prompt_passed"),
                        "loose_instruction_score": control_payload.get("loose_instruction_score"),
                        "checker_error": control_payload.get("checker_error"),
                    },
                    "treatment_checker_result": {
                        "strict_prompt_passed": treatment_prompt,
                        "strict_instruction_score": treatment_instruction,
                        "loose_prompt_passed": treatment_payload.get("loose_prompt_passed"),
                        "loose_instruction_score": treatment_payload.get("loose_instruction_score"),
                        "checker_error": treatment_payload.get("checker_error"),
                    },
                }
            )

    pair_key = f"{treatment} - {control}"
    return {
        "pair": pair_key,
        "treatment_variant": treatment,
        "control_variant": control,
        "improved_sample_count": len(improved),
        "degraded_sample_count": len(degraded),
        "tied_sample_count": len(tied),
        "prompt_level_delta": safe_delta(
            per_variant.get(treatment, {}).get("prompt_level_accuracy"),
            per_variant.get(control, {}).get("prompt_level_accuracy"),
        ),
        "instruction_level_delta": safe_delta(
            per_variant.get(treatment, {}).get("instruction_level_accuracy"),
            per_variant.get(control, {}).get("instruction_level_accuracy"),
        ),
        "improved_sample_ids": improved,
        "degraded_sample_ids": degraded,
        "changed_sample_audit": changed_audit,
    }


def build_pairwise(matrix: list[dict[str, Any]], per_variant: dict[str, Any]) -> dict[str, Any]:
    return {
        f"{treatment} - {control}": compare_pair(
            matrix=matrix,
            treatment=treatment,
            control=control,
            per_variant=per_variant,
        )
        for treatment, control in PAIRWISE_SPECS
    }


def compare_runner_aggregate(eval_results: dict[str, Any], variant_scores: dict[str, Any]) -> dict[str, Any]:
    runner_per_variant = eval_results.get("per_variant") or {}
    mismatches: dict[str, Any] = {}
    for variant_id, audit_payload in variant_scores.items():
        runner_payload = runner_per_variant.get(variant_id) or {}
        prompt_delta = safe_delta(
            audit_payload.get("prompt_level_accuracy"),
            runner_payload.get("prompt_level_accuracy"),
        )
        instruction_delta = safe_delta(
            audit_payload.get("instruction_level_accuracy"),
            runner_payload.get("instruction_level_accuracy"),
        )
        if prompt_delta not in (None, 0) or instruction_delta not in (None, 0):
            mismatches[variant_id] = {
                "audit_prompt_level_accuracy": audit_payload.get("prompt_level_accuracy"),
                "runner_prompt_level_accuracy": runner_payload.get("prompt_level_accuracy"),
                "prompt_level_delta": prompt_delta,
                "audit_instruction_level_accuracy": audit_payload.get("instruction_level_accuracy"),
                "runner_instruction_level_accuracy": runner_payload.get("instruction_level_accuracy"),
                "instruction_level_delta": instruction_delta,
            }
    return {
        "status": "match" if not mismatches else "mismatch",
        "mismatched_variants": mismatches,
        "note": "审计重算固定 langdetect seed；runner 原始汇总保留在 aggregate_eval_results_from_runner。",
    }


def write_matrix_csv(path: Path, matrix: list[dict[str, Any]], variants: list[str]) -> None:
    fieldnames = ["sample_index", "sample_id", "prompt", "instruction_id_list", "kwargs"]
    for variant_id in variants:
        fieldnames.extend(
            [
                f"{variant_id}_response_character_length",
                f"{variant_id}_strict_prompt_passed",
                f"{variant_id}_strict_instruction_score",
                f"{variant_id}_loose_prompt_passed",
                f"{variant_id}_loose_instruction_score",
                f"{variant_id}_provider_status",
                f"{variant_id}_provider_error",
                f"{variant_id}_checker_error",
            ]
        )

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in matrix:
            flat: dict[str, Any] = {
                "sample_index": row["sample_index"],
                "sample_id": row["sample_id"],
                "prompt": row["prompt"],
                "instruction_id_list": json.dumps(row["instruction_id_list"], ensure_ascii=False),
                "kwargs": json.dumps(row["kwargs"], ensure_ascii=False),
            }
            for variant_id in variants:
                payload = row["variants"][variant_id]
                flat[f"{variant_id}_response_character_length"] = payload["response_character_length"]
                flat[f"{variant_id}_strict_prompt_passed"] = payload["strict_prompt_passed"]
                flat[f"{variant_id}_strict_instruction_score"] = payload["strict_instruction_score"]
                flat[f"{variant_id}_loose_prompt_passed"] = payload["loose_prompt_passed"]
                flat[f"{variant_id}_loose_instruction_score"] = payload["loose_instruction_score"]
                flat[f"{variant_id}_provider_status"] = payload["provider_status"]
                flat[f"{variant_id}_provider_error"] = payload["provider_error"]
                flat[f"{variant_id}_checker_error"] = payload["checker_error"]
            writer.writerow(flat)


def render_markdown(audit: dict[str, Any], pairwise: dict[str, Any]) -> str:
    lines = [
        "# IFEval prompt-transfer limit=20 smoke 离线审计",
        "",
        "## Overview",
        "",
        f"- status: `{audit['status']}`",
        f"- total variants: `{audit.get('total_variants')}`",
        f"- total samples: `{audit.get('total_samples')}`",
        f"- expected calls: `{audit.get('expected_calls')}`",
        f"- actual raw output rows: `{audit.get('actual_raw_output_rows')}`",
        f"- provider errors/rejections/timeouts: `{audit['provider_events']['provider_error_count']}` / `{audit['provider_events']['provider_rejection_count']}` / `{audit['provider_events']['timeout_count']}`",
        f"- sample set consistency: `{audit['sample_consistency']['status']}`",
        f"- checker status: `{audit.get('checker_status')}`",
        f"- checker determinism: `{audit.get('checker_determinism')}`",
        f"- runner aggregate comparison: `{audit.get('runner_aggregate_comparison', {}).get('status')}`",
        "",
        "本报告只读取已有输出并重新运行本地 official IFEval rule checker；没有发起新的模型调用，没有启动 full IFEval，也没有启动 GEPA optimization。",
        "",
        "审计重算显式固定语言检测种子；原始 runner 汇总没有被改写，保留在 `audit.json` 的 `aggregate_eval_results_from_runner`。",
        "",
        "## Variant score table",
        "",
        "| variant | prompt-level accuracy | instruction-level accuracy | sample count | avg response chars | checker errors |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for variant_id, payload in audit["variant_scores"].items():
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                variant_id,
                payload["prompt_level_accuracy"],
                payload["instruction_level_accuracy"],
                payload["sample_count"],
                payload["average_response_character_length"],
                payload["checker_error_count"],
            )
        )

    lines.extend(
        [
            "",
            "## Pairwise delta table",
            "",
            "| pair | improved | degraded | tied | prompt delta | instruction delta |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for payload in pairwise.values():
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                payload["pair"],
                payload["improved_sample_count"],
                payload["degraded_sample_count"],
                payload["tied_sample_count"],
                payload["prompt_level_delta"],
                payload["instruction_level_delta"],
            )
        )

    comparison = audit.get("runner_aggregate_comparison", {})
    if comparison.get("status") == "mismatch":
        lines.extend(
            [
                "",
                "## Runner aggregate comparison",
                "",
                "以下差异来自本次固定语言检测种子的逐样本重算与已有 runner 汇总之间的对照，不代表新增模型调用。",
                "",
                "| variant | audit prompt | runner prompt | audit instruction | runner instruction |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for variant_id, payload in comparison.get("mismatched_variants", {}).items():
            lines.append(
                "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                    variant_id,
                    payload.get("canonical_prompt_level_accuracy", payload.get("audit_prompt_level_accuracy")),
                    payload.get("historical_prompt_level_accuracy", payload.get("runner_prompt_level_accuracy")),
                    payload.get("canonical_instruction_level_accuracy", payload.get("audit_instruction_level_accuracy")),
                    payload.get("historical_instruction_level_accuracy", payload.get("runner_instruction_level_accuracy")),
                )
            )

    lines.extend(["", "## Changed sample audit", ""])
    for payload in pairwise.values():
        lines.append(f"### {payload['pair']}")
        lines.append("")
        lines.append(f"- improved sample ids: `{payload['improved_sample_ids']}`")
        lines.append(f"- degraded sample ids: `{payload['degraded_sample_ids']}`")
        if not payload["changed_sample_audit"]:
            lines.append("- changed samples: 无")
            lines.append("")
            continue
        for item in payload["changed_sample_audit"]:
            lines.extend(
                [
                    "",
                    f"- sample `{item['sample_index']}` / `{item['sample_id']}`",
                    f"  - instructions: `{item['instruction_id_list']}`",
                    f"  - prompt: {short_text(str(item['prompt']))}",
                    f"  - control checker: `{item['control_checker_result']}`",
                    f"  - treatment checker: `{item['treatment_checker_result']}`",
                    f"  - control response excerpt: {short_text(str(item['control_response']))}",
                    f"  - treatment response excerpt: {short_text(str(item['treatment_response']))}",
                ]
            )
        lines.append("")

    lines.extend(
        [
            "## Interpretation boundary",
            "",
            "- `limit=20 smoke` 不是 full IFEval 结论。",
            "- 这轮只能说明 runner/API/checker 闭环可用，并出现与 IFBench 一致的初步迁移信号。",
            "- full IFEval run 仍然是必要下一步。",
            "- 本审计不使用 LLM judge，不新增 DashScope/Qwen 调用，不删除或改写 raw outputs。",
            "",
        ]
    )
    return "\n".join(lines)


def render_blocked_markdown(audit: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# IFEval prompt-transfer smoke 离线审计",
            "",
            f"- status: `{audit['status']}`",
            f"- blocked reasons: `{audit.get('blocked_reasons', [])}`",
            "",
            "本报告未发起任何模型调用。请补齐缺失的已有 smoke 输出后重新运行。",
            "",
        ]
    )


def build_canonical_summary(
    *,
    audit: dict[str, Any],
    pairwise: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    interpretations = {
        "gepa_p2_transfer": describe_pairwise_signal(
            pairwise,
            "gepa_p2_transfer - ifbench_gepa_prompt_transfer",
            "gepa_p2_transfer",
            "ifbench_gepa_prompt_transfer",
        ),
        "mhc_concise": describe_pairwise_signal(
            pairwise,
            "mhc_concise - baseline_mhc",
            "mhc_concise",
            "baseline_mhc",
        ),
        "baseline_mhc": describe_pairwise_signal(
            pairwise,
            "baseline_mhc - baseline",
            "baseline_mhc",
            "baseline",
        ),
        "verbose_helpfulness": describe_pairwise_signal(
            pairwise,
            "verbose_helpfulness - baseline",
            "verbose_helpfulness",
            "baseline",
        ),
    }
    return {
        "status": audit["status"],
        "canonical_summary_source": CANONICAL_SUMMARY_SOURCE,
        "scope": {
            "benchmark": "IFEval",
            "limit": audit.get("total_samples"),
            "variant_count": audit.get("total_variants"),
            "new_api_call_enabled": False,
            "full_ifeval_conclusion": False,
        },
        "checker_metadata": {
            "checker_source": evaluation.get("checker_source"),
            "llm_judge_enabled": evaluation.get("llm_judge_enabled"),
            "langdetect_seed": evaluation.get("langdetect_seed"),
            "aggregation_source": evaluation.get("aggregation_source"),
            "checker_determinism_status": evaluation.get("checker_determinism_status"),
        },
        "variant_scores": evaluation.get("per_variant", {}),
        "pairwise_comparisons": pairwise,
        "main_interpretation": interpretations,
        "boundary": [
            "limit=20 smoke 不是 full IFEval 结论。",
            "full IFEval run 仍然是必要下一步。",
            "本 summary 只来自已有 raw_outputs.jsonl 的 deterministic offline official IFEval checker 重算。",
        ],
    }


def describe_pairwise_signal(pairwise: dict[str, Any], pair_key: str, treatment: str, control: str) -> str:
    payload = pairwise.get(pair_key) or {}
    prompt_delta = payload.get("prompt_level_delta")
    instruction_delta = payload.get("instruction_level_delta")
    if prompt_delta is None or instruction_delta is None:
        return f"{treatment} 相对 {control} 没有可用的 canonical pairwise delta。"
    if prompt_delta > 0 or instruction_delta > 0:
        return f"{treatment} 相对 {control} 显示正向 smoke 信号。"
    if prompt_delta < 0 or instruction_delta < 0:
        return f"{treatment} 相对 {control} 显示负向 smoke 信号。"
    return f"{treatment} 相对 {control} 在 canonical deterministic recheck 下没有改善。"


def render_canonical_summary_md(summary: dict[str, Any]) -> str:
    lines = [
        "# IFEval prompt-transfer canonical smoke summary",
        "",
        "## Scope",
        "",
        f"- limit=20 smoke: `{summary['scope']['limit']}` samples",
        "- no new API call",
        "- deterministic offline official IFEval checker",
        f"- canonical_summary_source: `{summary['canonical_summary_source']}`",
        f"- langdetect_seed: `{summary['checker_metadata']['langdetect_seed']}`",
        f"- llm_judge_enabled: `{summary['checker_metadata']['llm_judge_enabled']}`",
        "",
        "## Variant table",
        "",
        "| variant | prompt-level accuracy | instruction-level accuracy | sample count | checker errors |",
        "|---|---:|---:|---:|---:|",
    ]
    for variant_id, payload in summary["variant_scores"].items():
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                variant_id,
                payload.get("prompt_level_accuracy"),
                payload.get("instruction_level_accuracy"),
                payload.get("sample_count"),
                payload.get("checker_error_count"),
            )
        )
    lines.extend(
        [
            "",
            "## Pairwise delta table",
            "",
            "| pair | improved | degraded | tied | prompt delta | instruction delta |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for payload in summary["pairwise_comparisons"].values():
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                payload["pair"],
                payload["improved_sample_count"],
                payload["degraded_sample_count"],
                payload["tied_sample_count"],
                payload["prompt_level_delta"],
                payload["instruction_level_delta"],
            )
        )
    lines.extend(["", "## Main interpretation", ""])
    for text in summary["main_interpretation"].values():
        lines.append(f"- {text}")
    lines.extend(["", "## Boundary", ""])
    for text in summary["boundary"]:
        lines.append(f"- {text}")
    lines.append("")
    return "\n".join(lines)


def render_markdown(audit: dict[str, Any], pairwise: dict[str, Any]) -> str:
    lines = [
        "# IFEval prompt-transfer limit=20 smoke 离线审计",
        "",
        "## Overview",
        "",
        f"- status: `{audit['status']}`",
        f"- total variants: `{audit.get('total_variants')}`",
        f"- total samples: `{audit.get('total_samples')}`",
        f"- expected calls: `{audit.get('expected_calls')}`",
        f"- actual raw output rows: `{audit.get('actual_raw_output_rows')}`",
        f"- provider errors/rejections/timeouts: `{audit['provider_events']['provider_error_count']}` / `{audit['provider_events']['provider_rejection_count']}` / `{audit['provider_events']['timeout_count']}`",
        f"- sample set consistency: `{audit['sample_consistency']['status']}`",
        f"- checker status: `{audit.get('checker_status')}`",
        f"- checker metadata: `{audit.get('checker_metadata')}`",
        f"- runner aggregate comparison: `{audit.get('runner_aggregate_comparison', {}).get('status')}`",
        "",
        "本报告只读取已有 raw outputs，并用 deterministic official IFEval rule checker 离线重算；没有新增模型调用，没有启动 full IFEval，也没有启动 GEPA optimization。",
        "原始 runner aggregate 标记为 historical/raw-runner aggregate；canonical smoke scores 以后以 deterministic audit-compatible re-evaluation 为准。",
        "",
        "## Variant score table",
        "",
        "| variant | prompt-level accuracy | instruction-level accuracy | sample count | avg response chars | checker errors |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for variant_id, payload in audit["variant_scores"].items():
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                variant_id,
                payload.get("prompt_level_accuracy"),
                payload.get("instruction_level_accuracy"),
                payload.get("sample_count"),
                payload.get("average_response_character_length"),
                payload.get("checker_error_count"),
            )
        )

    lines.extend(
        [
            "",
            "## Pairwise delta table",
            "",
            "| pair | improved | degraded | tied | prompt delta | instruction delta |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for payload in pairwise.values():
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                payload["pair"],
                payload["improved_sample_count"],
                payload["degraded_sample_count"],
                payload["tied_sample_count"],
                payload["prompt_level_delta"],
                payload["instruction_level_delta"],
            )
        )

    comparison = audit.get("runner_aggregate_comparison", {})
    if comparison.get("status") == "mismatch":
        lines.extend(
            [
                "",
                "## Runner aggregate comparison",
                "",
                "以下差异来自已有 historical/raw-runner aggregate 与本次 canonical deterministic offline recheck 的对照；这不是新增模型调用。",
                "",
                "| variant | canonical prompt | historical prompt | canonical instruction | historical instruction |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for variant_id, payload in comparison.get("mismatched_variants", {}).items():
            lines.append(
                "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                    variant_id,
                    payload.get("canonical_prompt_level_accuracy"),
                    payload.get("historical_prompt_level_accuracy"),
                    payload.get("canonical_instruction_level_accuracy"),
                    payload.get("historical_instruction_level_accuracy"),
                )
            )

    lines.extend(["", "## Changed sample audit", ""])
    for payload in pairwise.values():
        lines.append(f"### {payload['pair']}")
        lines.append("")
        lines.append(f"- improved sample ids: `{payload['improved_sample_ids']}`")
        lines.append(f"- degraded sample ids: `{payload['degraded_sample_ids']}`")
        if not payload["changed_sample_audit"]:
            lines.append("- changed samples: 无")
            lines.append("")
            continue
        for item in payload["changed_sample_audit"]:
            lines.extend(
                [
                    "",
                    f"- sample `{item['sample_index']}` / `{item['sample_id']}`",
                    f"  - instructions: `{item['instruction_id_list']}`",
                    f"  - prompt: {short_text(str(item['prompt']))}",
                    f"  - control checker: `{item['control_checker_result']}`",
                    f"  - treatment checker: `{item['treatment_checker_result']}`",
                    f"  - control response excerpt: {short_text(str(item['control_response']))}",
                    f"  - treatment response excerpt: {short_text(str(item['treatment_response']))}",
                ]
            )
        lines.append("")

    lines.extend(
        [
            "## Interpretation boundary",
            "",
            "- `limit=20 smoke` 不是 full IFEval 结论。",
            "- 这轮只能说明 runner/API/checker 闭环可用，并给出初步迁移信号。",
            "- full IFEval run 仍然是必要下一步。",
            "- 本审计不使用 LLM judge，不新增 DashScope/Qwen 调用，不删除或改写 raw outputs。",
            "",
        ]
    )
    return "\n".join(lines)


def render_blocked_markdown(audit: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# IFEval prompt-transfer smoke 离线审计",
            "",
            f"- status: `{audit['status']}`",
            f"- blocked reasons: `{audit.get('blocked_reasons', [])}`",
            "",
            "本报告未发起任何模型调用。请补齐缺失的已有 smoke 输出后重新运行。",
            "",
        ]
    )


def write_blocked_outputs(smoke_dir: Path, reasons: list[str], input_status: dict[str, Any]) -> dict[str, Any]:
    smoke_dir.mkdir(parents=True, exist_ok=True)
    audit = {
        "status": "blocked",
        "blocked_reasons": reasons,
        "input_status": input_status,
        "provider_events": {
            "provider_error_count": 0,
            "provider_rejection_count": 0,
            "timeout_count": 0,
            "provider_status_counts": {},
            "events": [],
        },
        "sample_consistency": {"status": "not_run"},
        "variant_scores": {},
    }
    write_json(smoke_dir / "audit.json", audit)
    write_text(smoke_dir / "audit.md", render_blocked_markdown(audit))
    write_json(smoke_dir / "pairwise_sample_matrix.json", {"status": "blocked", "samples": [], "pairwise_comparisons": {}})
    write_matrix_csv(smoke_dir / "pairwise_sample_matrix.csv", [], [])
    canonical_summary = {
        "status": "blocked",
        "canonical_summary_source": CANONICAL_SUMMARY_SOURCE,
        "blocked_reasons": reasons,
        "variant_scores": {},
        "pairwise_comparisons": {},
    }
    write_json(smoke_dir / "canonical_summary.json", canonical_summary)
    write_text(smoke_dir / "canonical_summary.md", render_blocked_markdown(audit))
    return audit


def analyze_smoke(smoke_dir: Path) -> dict[str, Any]:
    input_status = validate_inputs(smoke_dir)
    if input_status["status"] != "ok":
        return write_blocked_outputs(
            smoke_dir,
            [f"missing_input_file:{name}" for name in input_status["missing_files"]],
            input_status,
        )

    raw_rows = read_jsonl(smoke_dir / "raw_outputs.jsonl")
    eval_results = read_json(smoke_dir / "eval_results.json")
    summary = read_json(smoke_dir / "summary.json")
    provider_events_input = read_json(smoke_dir / "provider_events.json")
    run_config = read_json(smoke_dir / "run_config.json")

    variants = [str(item) for item in run_config.get("variants", [])]
    limit = int(run_config.get("limit") or summary.get("limit") or 0)
    dataset_path = Path(str(run_config.get("dataset_path") or ""))
    ifeval_root = Path(str(run_config.get("ifeval_root") or ""))
    if not variants:
        return write_blocked_outputs(smoke_dir, ["missing_variant_config_in_run_config"], input_status)
    if limit <= 0:
        return write_blocked_outputs(smoke_dir, ["missing_positive_limit_in_run_config"], input_status)
    if not dataset_path.is_file():
        return write_blocked_outputs(smoke_dir, ["dataset_path_unavailable"], input_status)
    if not ifeval_root.is_dir():
        return write_blocked_outputs(smoke_dir, ["ifeval_root_unavailable"], input_status)

    samples = load_samples(dataset_path, limit)
    expected_indexes = list(range(len(samples)))
    sample_consistency = check_variant_sample_consistency(
        raw_rows=raw_rows,
        variants=variants,
        expected_sample_indexes=expected_indexes,
    )

    checker_status = "ok"
    checker_error = None
    try:
        evaluation_payload = evaluate_raw_outputs_common(
            ifeval_root=ifeval_root,
            dataset_path=dataset_path,
            raw_rows=raw_rows,
            variants=variants,
            limit=len(samples),
        )
    except Exception as exc:
        checker_status = "checker_error"
        checker_error = f"{type(exc).__name__}: {exc}"
        fallback_matrix = build_matrix(
            samples=samples,
            raw_rows=raw_rows,
            variants=variants,
            checker_payloads={
                (int(row.get("sample_index", -1)), normalize_variant(row)): {"checker_error": checker_error}
                for row in raw_rows
            },
        )
        evaluation_payload = {
            "metadata": {
                "checker_source": "official_ifeval",
                "llm_judge_enabled": False,
                "langdetect_seed": 0,
                "aggregation_source": "deterministic_offline_checker",
                "checker_determinism_status": "checker_error",
            },
            "matrix": fallback_matrix,
            "evaluation": {"per_variant": aggregate_variant_scores(fallback_matrix, variants)},
            "pairwise": {},
        }

    matrix = evaluation_payload["matrix"]
    evaluation = evaluation_payload["evaluation"]
    variant_scores = evaluation.get("per_variant", {})
    pairwise = evaluation_payload["pairwise"]
    runner_aggregate_comparison = compare_aggregates(eval_results, evaluation)
    provider_events = summarize_provider_rows(raw_rows, provider_events_input)
    expected_calls = len(variants) * len(samples)
    status = "completed" if sample_consistency["status"] == "ok" and checker_status == "ok" else "blocked"
    blocked_reasons: list[str] = []
    if sample_consistency["status"] != "ok":
        blocked_reasons.append("sample_set_inconsistent")
    if checker_status != "ok":
        blocked_reasons.append("checker_error")

    audit = {
        "status": status,
        "blocked_reasons": blocked_reasons,
        "input_status": input_status,
        "total_variants": len(variants),
        "total_samples": len(samples),
        "expected_calls": expected_calls,
        "actual_raw_output_rows": len(raw_rows),
        "expected_variants": variants,
        "sample_consistency": sample_consistency,
        "checker_status": checker_status,
        "checker_error": checker_error,
        "checker_metadata": evaluation_payload["metadata"],
        "checker_determinism": evaluation_payload["metadata"],
        "provider_events": provider_events,
        "variant_scores": variant_scores,
        "runner_aggregate_comparison": runner_aggregate_comparison,
        "aggregate_eval_results_from_runner": eval_results,
        "historical_runner_aggregate_source": "raw_historical_runner_aggregate",
        "canonical_summary_source": CANONICAL_SUMMARY_SOURCE,
        "interpretation_boundary": {
            "is_full_ifeval_conclusion": False,
            "statement": "limit=20 smoke 只用于工程闭环和初步信号，不能作为 full IFEval 结论。",
        },
    }
    canonical_summary = build_canonical_summary(
        audit=audit,
        pairwise=pairwise,
        evaluation=evaluation,
    )
    metadata_update = {
        "checker_metadata": evaluation_payload["metadata"],
        "canonical_aggregation_source": evaluation_payload["metadata"]["aggregation_source"],
        "canonical_summary_source": CANONICAL_SUMMARY_SOURCE,
        "langdetect_seed": evaluation_payload["metadata"]["langdetect_seed"],
        "checker_determinism_status": evaluation_payload["metadata"]["checker_determinism_status"],
        "llm_judge_enabled": False,
        "historical_runner_aggregate_source": "raw_historical_runner_aggregate",
        "canonical_summary_path": (smoke_dir / "canonical_summary.json").as_posix(),
    }
    updated_summary = {**summary, **metadata_update}
    updated_run_config = {
        **run_config,
        **metadata_update,
        "output_dir": smoke_dir.as_posix(),
    }
    matrix_payload = {
        "status": status,
        "variants": variants,
        "sample_count": len(matrix),
        "samples": matrix,
        "pairwise_comparisons": pairwise,
        "checker_metadata": evaluation_payload["metadata"],
        "canonical_summary_source": CANONICAL_SUMMARY_SOURCE,
    }

    write_json(smoke_dir / "summary.json", updated_summary)
    write_json(smoke_dir / "run_config.json", updated_run_config)
    write_json(smoke_dir / "audit.json", audit)
    write_text(smoke_dir / "audit.md", render_markdown(audit, pairwise))
    write_json(smoke_dir / "canonical_summary.json", canonical_summary)
    write_text(smoke_dir / "canonical_summary.md", render_canonical_summary_md(canonical_summary))
    write_json(smoke_dir / "pairwise_sample_matrix.json", matrix_payload)
    write_matrix_csv(smoke_dir / "pairwise_sample_matrix.csv", matrix, variants)
    return audit


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    audit = analyze_smoke(Path(args.smoke_dir))
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
