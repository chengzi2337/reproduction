from __future__ import annotations

import importlib
import json
import os
import copy
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.ifeval_official_adapter import official_import_path


CHECKER_SOURCE = "official_ifeval"
AGGREGATION_SOURCE = "deterministic_offline_checker"
CANONICAL_SUMMARY_SOURCE = "deterministic_offline_recheck"
LANGDETECT_SEED = 0
LLM_JUDGE_ENABLED = False
PAIRWISE_SPECS = (
    ("baseline_mhc", "baseline"),
    ("verbose_helpfulness", "baseline"),
    ("mhc_concise", "baseline_mhc"),
    ("gepa_p2_transfer", "ifbench_gepa_prompt_transfer"),
)




def checker_metadata() -> dict[str, Any]:
    determinism = configure_deterministic_checker()
    return {
        "checker_source": CHECKER_SOURCE,
        "llm_judge_enabled": LLM_JUDGE_ENABLED,
        "langdetect_seed": LANGDETECT_SEED,
        "aggregation_source": AGGREGATION_SOURCE,
        "canonical_summary_source": CANONICAL_SUMMARY_SOURCE,
        "checker_determinism_status": determinism["checker_determinism_status"],
        "checker_determinism_detail": determinism,
    }


def configure_deterministic_checker() -> dict[str, Any]:
    os.environ.setdefault("PYTHONHASHSEED", "0")
    try:
        from langdetect import DetectorFactory, detector_factory

        DetectorFactory.seed = LANGDETECT_SEED
        detector_factory.init_factory()
        if detector_factory._factory is not None:
            detector_factory._factory.seed = LANGDETECT_SEED
        return {
            "checker_determinism_status": "set",
            "langdetect_seed": LANGDETECT_SEED,
            "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
        }
    except Exception as exc:
        return {
            "checker_determinism_status": "langdetect_unavailable",
            "langdetect_seed": LANGDETECT_SEED,
            "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
            "error": f"{type(exc).__name__}: {exc}",
        }


def install_deterministic_langdetect_wrapper() -> dict[str, Any]:
    try:
        import langdetect
        from langdetect import DetectorFactory, detector_factory

        DetectorFactory.seed = LANGDETECT_SEED
        detector_factory.init_factory()

        def deterministic_detect(text: str) -> str:
            detector_factory.init_factory()
            if detector_factory._factory is None:
                return langdetect.detect(text)
            detector_factory._factory.seed = LANGDETECT_SEED
            detector = detector_factory._factory.create()
            detector.seed = LANGDETECT_SEED
            detector.append(text)
            return detector.detect()

        if getattr(langdetect.detect, "_ifeval_deterministic", False):
            return {"langdetect_wrapper_status": "already_installed"}
        deterministic_detect._ifeval_deterministic = True  # type: ignore[attr-defined]
        langdetect.detect = deterministic_detect
        return {"langdetect_wrapper_status": "installed"}
    except Exception as exc:
        return {"langdetect_wrapper_status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}


def purge_official_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "instruction_following_eval" or module_name.startswith("instruction_following_eval."):
            del sys.modules[module_name]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError(f"{path.name}:{line_number} 不是 JSON object。")
            rows.append(payload)
    return rows


def load_samples(dataset_path: Path, limit: int) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("IFEval 数据行不是 JSON object。")
            samples.append(payload)
            if len(samples) >= limit:
                break
    return samples


def normalize_variant(row: dict[str, Any]) -> str:
    return str(row.get("variant") or row.get("variant_id") or "")


def instruction_score(values: list[bool] | None) -> float | None:
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


def apply_deterministic_rule_overrides(
    *,
    checker_result: dict[str, Any],
    sample: dict[str, Any],
    response: str,
) -> dict[str, Any]:
    instruction_ids = list(sample.get("instruction_id_list") or [])
    kwargs_list = list(sample.get("kwargs") or [])
    for mode in ("strict", "loose"):
        payload = checker_result.get(mode)
        if not isinstance(payload, dict):
            continue
        follow_list = list(payload.get("follow_instruction_list") or [])
        for index, instruction_id in enumerate(instruction_ids):
            if instruction_id != "keywords:letter_frequency" or index >= len(follow_list):
                continue
            kwargs = kwargs_list[index] if index < len(kwargs_list) and isinstance(kwargs_list[index], dict) else {}
            letter = str(kwargs.get("letter") or "").strip().lower()
            relation = kwargs.get("let_relation")
            frequency = kwargs.get("let_frequency")
            if not letter or not isinstance(frequency, int):
                continue
            actual = response.lower().count(letter)
            if relation == "less than":
                follow_list[index] = actual < frequency
            elif relation == "at least":
                follow_list[index] = actual >= frequency
        payload["follow_instruction_list"] = follow_list
        payload["instruction_level_score"] = instruction_score(follow_list)
        payload["prompt_level_passed"] = all(follow_list) if follow_list else False
    return checker_result


def evaluate_raw_outputs(
    *,
    ifeval_root: Path,
    dataset_path: Path,
    raw_rows: list[dict[str, Any]],
    variants: list[str],
    limit: int,
) -> dict[str, Any]:
    metadata = checker_metadata()
    wrapper_status = install_deterministic_langdetect_wrapper()
    metadata["checker_determinism_detail"]["langdetect_wrapper"] = wrapper_status
    samples = load_samples(dataset_path, limit)
    prompts_in_limit = {str(sample.get("prompt", "")) for sample in samples}
    sample_by_prompt = {str(sample.get("prompt", "")): sample for sample in samples}
    checker_payloads: dict[tuple[int, str], dict[str, Any]] = {}
    rows_by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in raw_rows:
        rows_by_variant[normalize_variant(row)].append(row)

    purge_official_modules()
    configure_deterministic_checker()
    with official_import_path(ifeval_root):
        evaluation_lib = importlib.import_module("instruction_following_eval.evaluation_lib")
        inputs = list(evaluation_lib.read_prompt_list(str(dataset_path)))[: len(samples)]
        input_by_prompt = {item.prompt: item for item in inputs}
        for variant_id in variants:
            rows = sorted(rows_by_variant.get(variant_id, []), key=lambda item: int(item.get("sample_index", -1)))
            prompt_to_response = {str(row.get("prompt", "")): str(row.get("response", "")) for row in rows}
            for row in rows:
                sample_index = int(row.get("sample_index", -1))
                prompt = str(row.get("prompt", ""))
                if prompt not in prompts_in_limit or prompt not in input_by_prompt:
                    checker_payloads[(sample_index, variant_id)] = {
                        "checker_error": f"raw output prompt 不存在于 dataset limit: {sample_index}",
                    }
                    continue
                try:
                    input_example = copy.deepcopy(input_by_prompt[prompt])
                    configure_deterministic_checker()
                    strict_output = evaluation_lib.test_instruction_following_strict(input_example, prompt_to_response)
                    configure_deterministic_checker()
                    loose_output = evaluation_lib.test_instruction_following_loose(copy.deepcopy(input_by_prompt[prompt]), prompt_to_response)
                    checker_payloads[(sample_index, variant_id)] = {
                        "strict": output_to_payload(strict_output),
                        "loose": output_to_payload(loose_output),
                        "checker_error": None,
                    }
                    checker_payloads[(sample_index, variant_id)] = apply_deterministic_rule_overrides(
                        checker_result=checker_payloads[(sample_index, variant_id)],
                        sample=sample_by_prompt[prompt],
                        response=str(row.get("response", "")),
                    )
                except Exception as exc:
                    checker_payloads[(sample_index, variant_id)] = {
                        "checker_error": f"{type(exc).__name__}: {exc}",
                    }

    matrix = build_sample_matrix(samples=samples, raw_rows=raw_rows, variants=variants, checker_payloads=checker_payloads)
    per_variant = aggregate_variant_scores(matrix, variants)
    return {
        "metadata": metadata,
        "samples": samples,
        "checker_payloads": checker_payloads,
        "matrix": matrix,
        "evaluation": summarize_evaluation(per_variant, matrix, variants),
        "pairwise": build_pairwise(matrix, per_variant),
    }


def build_sample_matrix(
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
        checker_error_count = 0
        response_lengths: list[int] = []
        for row in matrix:
            payload = row["variants"][variant_id]
            response_lengths.append(int(payload.get("response_character_length") or 0))
            if payload.get("checker_error"):
                checker_error_count += 1
            if payload.get("strict_prompt_passed") is not None:
                prompt_total += 1
                if payload.get("strict_prompt_passed"):
                    prompt_correct += 1
            follow_list = payload.get("strict_follow_instruction_list")
            if isinstance(follow_list, list):
                instruction_total += len(follow_list)
                instruction_correct += sum(1 for value in follow_list if value)
        per_variant[variant_id] = {
            "sample_count": len(matrix),
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


def summarize_evaluation(per_variant: dict[str, Any], matrix: list[dict[str, Any]], variants: list[str]) -> dict[str, Any]:
    prompt_total = sum(int(payload.get("prompt_total") or 0) for payload in per_variant.values())
    prompt_correct = sum(int(payload.get("prompt_correct") or 0) for payload in per_variant.values())
    instruction_total = sum(int(payload.get("instruction_total") or 0) for payload in per_variant.values())
    instruction_correct = sum(int(payload.get("instruction_correct") or 0) for payload in per_variant.values())
    per_instruction = summarize_instruction_types(matrix, variants)
    return {
        "prompt_level_accuracy": prompt_correct / prompt_total if prompt_total else None,
        "instruction_level_accuracy": instruction_correct / instruction_total if instruction_total else None,
        "per_variant": per_variant,
        "per_instruction_type_accuracy": per_instruction,
        "pairwise_delta": build_pairwise_delta(per_variant),
        **checker_metadata(),
    }


def summarize_instruction_types(matrix: list[dict[str, Any]], variants: list[str]) -> dict[str, Any]:
    per_instruction: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    for row in matrix:
        instruction_ids = list(row.get("instruction_id_list") or [])
        for variant_id in variants:
            follow_list = row["variants"][variant_id].get("strict_follow_instruction_list")
            if not isinstance(follow_list, list):
                continue
            for instruction_id, followed in zip(instruction_ids, follow_list):
                family = str(instruction_id).split(":")[0]
                per_instruction[family]["total"] += 1
                if followed:
                    per_instruction[family]["correct"] += 1
    return {
        key: {
            "accuracy": value["correct"] / value["total"] if value["total"] else None,
            **value,
        }
        for key, value in sorted(per_instruction.items())
    }


def safe_delta(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def build_pairwise_delta(per_variant: dict[str, Any]) -> dict[str, Any]:
    deltas: dict[str, Any] = {}
    for treatment, control in PAIRWISE_SPECS:
        treatment_payload = per_variant.get(treatment) or {}
        control_payload = per_variant.get(control) or {}
        deltas[f"{treatment} - {control}"] = {
            "prompt_level_accuracy_delta": safe_delta(
                treatment_payload.get("prompt_level_accuracy"),
                control_payload.get("prompt_level_accuracy"),
            ),
            "instruction_level_accuracy_delta": safe_delta(
                treatment_payload.get("instruction_level_accuracy"),
                control_payload.get("instruction_level_accuracy"),
            ),
        }
    return deltas


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
                    "control_checker_result": checker_result_summary(control_payload),
                    "treatment_checker_result": checker_result_summary(treatment_payload),
                }
            )

    return {
        "pair": f"{treatment} - {control}",
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


def checker_result_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "strict_prompt_passed": payload.get("strict_prompt_passed"),
        "strict_instruction_score": payload.get("strict_instruction_score"),
        "loose_prompt_passed": payload.get("loose_prompt_passed"),
        "loose_instruction_score": payload.get("loose_instruction_score"),
        "checker_error": payload.get("checker_error"),
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
        if treatment in per_variant and control in per_variant
    }


def compare_aggregates(
    historical_eval_results: dict[str, Any],
    canonical_eval_results: dict[str, Any],
) -> dict[str, Any]:
    historical_per_variant = historical_eval_results.get("per_variant") or {}
    canonical_per_variant = canonical_eval_results.get("per_variant") or {}
    mismatches: dict[str, Any] = {}
    for variant_id, canonical_payload in canonical_per_variant.items():
        historical_payload = historical_per_variant.get(variant_id) or {}
        prompt_delta = safe_delta(
            canonical_payload.get("prompt_level_accuracy"),
            historical_payload.get("prompt_level_accuracy"),
        )
        instruction_delta = safe_delta(
            canonical_payload.get("instruction_level_accuracy"),
            historical_payload.get("instruction_level_accuracy"),
        )
        if prompt_delta not in (None, 0) or instruction_delta not in (None, 0):
            mismatches[variant_id] = {
                "canonical_prompt_level_accuracy": canonical_payload.get("prompt_level_accuracy"),
                "historical_prompt_level_accuracy": historical_payload.get("prompt_level_accuracy"),
                "prompt_level_delta": prompt_delta,
                "canonical_instruction_level_accuracy": canonical_payload.get("instruction_level_accuracy"),
                "historical_instruction_level_accuracy": historical_payload.get("instruction_level_accuracy"),
                "instruction_level_delta": instruction_delta,
            }
    return {
        "status": "match" if not mismatches else "mismatch",
        "mismatched_variants": mismatches,
        "historical_aggregate_source": "raw_historical_runner_aggregate",
        "canonical_summary_source": CANONICAL_SUMMARY_SOURCE,
        **checker_metadata(),
    }
