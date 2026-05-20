from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.logging_utils import create_run_dir, write_json, write_text
from scripts.stage2c_run_mimo_controlled_generation_gepa_sanity import load_dataset_via_stage2c_path
from scripts.stage2d_audit_aime_evaluator_format_contract import (
    DEFAULT_OUTPUT_DIR as CONTRACT_AUDIT_OUTPUT_DIR,
)
from scripts.stage2d_audit_aime_evaluator_format_contract import (
    EXPECTED_OFFICIAL_ANSWER,
    classify_failure_mode,
    discover_official_evaluator,
    relaxed_extract_answer,
    strict_regex_match_hash_integer,
)


PATH_TYPE = "stage2d_existing_outputs_answer_extractability_audit"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "stage2d_existing_outputs_answer_extractability_audit"
SMOKE_OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "stage2c_mimo_controlled_generation_gepa_smoke"
PROMPT_FIRST_OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "stage2c_mimo_prompt_first_format_enforcement_diagnostic"


def _latest_run_dir(root: Path) -> Path:
    candidates = sorted([item for item in root.iterdir() if item.is_dir()], key=lambda p: p.name)
    if not candidates:
        raise FileNotFoundError(f"未找到输出目录：{root}")
    return candidates[-1]


def _content_nonempty(text: str | None) -> bool:
    return bool((text or "").strip())


def _output_protocol_violation(*, official_ok: bool, relaxed_ok: bool, response_text: str) -> bool:
    return (not official_ok and relaxed_ok) or ("### <answer>" in response_text) or (
        re.search(r"(?mi)^###\s*(step|part|solution|analysis)\b", response_text) is not None
    )


def _build_case(
    *,
    evaluator: Any,
    artifact_type: str,
    source_content_complete: bool,
    source_path: str,
    sample_index: int,
    response_text: str,
    expected_answer: str,
) -> dict[str, Any]:
    eval_result = evaluator({"input": "synthetic", "additional_context": {}, "answer": expected_answer}, response_text)
    official_ok = float(eval_result.score) == 1.0
    strict_ok = strict_regex_match_hash_integer(response_text)
    relaxed_answer = relaxed_extract_answer(response_text)
    relaxed_ok = relaxed_answer is not None
    xml_misuse = "### <answer>" in response_text
    step_misuse = re.search(r"(?mi)^###\s*(step|part|solution|analysis)\b", response_text) is not None
    return {
        "artifact_type": artifact_type,
        "source_content_complete": source_content_complete,
        "source_path": source_path,
        "sample_index": sample_index,
        "expected_official_answer": expected_answer,
        "content_nonempty": _content_nonempty(response_text),
        "official_evaluator_compatible": official_ok,
        "strict_regex_match_###_integer": strict_ok,
        "relaxed_human_extractable": relaxed_ok,
        "relaxed_extracted_answer": relaxed_answer,
        "normalized_score": 1.0 if relaxed_answer == expected_answer.replace("### ", "") else 0.0,
        "output_protocol_violation": _output_protocol_violation(
            official_ok=official_ok,
            relaxed_ok=relaxed_ok,
            response_text=response_text,
        ),
        "xml_tag_placeholder_misuse": xml_misuse,
        "markdown_heading_misuse": bool(step_misuse),
        "final_answer_missing": not relaxed_ok,
        "classified_failure_mode": classify_failure_mode(response_text, float(eval_result.score)),
        "response_preview": response_text[:240] + ("..." if len(response_text) > 240 else ""),
    }


def _load_expected_answers() -> tuple[list[dict[str, Any]], str]:
    _, valset, _, dataset_source = load_dataset_via_stage2c_path()
    return valset, dataset_source


def audit_smoke_outputs(*, evaluator: Any, valset: list[dict[str, Any]]) -> list[dict[str, Any]]:
    run_dir = _latest_run_dir(SMOKE_OUTPUT_ROOT)
    generated_root = run_dir / "generated_best_outputs_valset"
    results: list[dict[str, Any]] = []
    for task_dir in sorted(generated_root.glob("task_*"), key=lambda p: int(p.name.split("_")[1])):
        sample_index = int(task_dir.name.split("_")[1])
        file_path = task_dir / "iter_0_prog_0.json"
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        response_text = str(payload.get("full_assistant_response") or "")
        expected_answer = str(valset[sample_index]["answer"])
        results.append(
            _build_case(
                evaluator=evaluator,
                artifact_type="stage2c_smoke",
                source_content_complete=True,
                source_path=str(file_path.relative_to(PROJECT_ROOT)),
                sample_index=sample_index,
                response_text=response_text,
                expected_answer=expected_answer,
            )
        )
    return results


def audit_prompt_first_outputs(*, evaluator: Any, valset: list[dict[str, Any]]) -> list[dict[str, Any]]:
    run_dir = _latest_run_dir(PROMPT_FIRST_OUTPUT_ROOT)
    payload = json.loads((run_dir / "stage2c_prompt_first_results.json").read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    for item in payload["results"]:
        sample_index = int(item["sample_index"])
        expected_answer = str(valset[sample_index]["answer"])
        for path_name, field_name in (("direct_sdk", "direct_sdk_result"), ("litellm", "litellm_result")):
            response_text = str(item[field_name].get("content_preview") or "")
            results.append(
                _build_case(
                    evaluator=evaluator,
                    artifact_type=f"stage2c_prompt_first_{path_name}_preview",
                    source_content_complete=False,
                    source_path=str((run_dir / "stage2c_prompt_first_results.json").relative_to(PROJECT_ROOT)),
                    sample_index=sample_index,
                    response_text=response_text,
                    expected_answer=expected_answer,
                )
                | {
                    "prompt_variant_id": item["prompt_variant"]["variant_id"],
                    "prompt_variant_name": item["prompt_variant"]["variant_name"],
                }
            )
    return results


def build_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    def _count(predicate):
        return sum(1 for case in cases if predicate(case))

    return {
        "total_cases": len(cases),
        "official_evaluator_compatible_count": _count(lambda case: case["official_evaluator_compatible"]),
        "relaxed_human_extractable_count": _count(lambda case: case["relaxed_human_extractable"]),
        "output_protocol_violation_count": _count(lambda case: case["output_protocol_violation"]),
        "xml_tag_placeholder_misuse_count": _count(lambda case: case["xml_tag_placeholder_misuse"]),
        "markdown_heading_misuse_count": _count(lambda case: case["markdown_heading_misuse"]),
        "final_answer_missing_count": _count(lambda case: case["final_answer_missing"]),
    }


def run_existing_outputs_audit(output_root: Path) -> tuple[Path, dict[str, Any]]:
    discovery = discover_official_evaluator()
    run_dir = create_run_dir(output_root)
    payload: dict[str, Any] = {
        "path_type": PATH_TYPE,
        "not_performance_claim": True,
        "not_gepa_path": True,
        "no_gepa_optimize_called": True,
        "normalized_score_is_diagnostic_only": True,
    }

    if discovery["evaluator_discovery_failed"]:
        payload.update(discovery)
        write_json(run_dir / "stage2d_existing_outputs_answer_extractability_audit.json", payload)
        write_text(run_dir / "notes.md", "# Stage 2D existing outputs answer-extractability audit\n\n- evaluator discovery failed\n")
        return run_dir, payload

    evaluator = discovery.pop("evaluator")
    valset, dataset_source = _load_expected_answers()
    smoke_cases = audit_smoke_outputs(evaluator=evaluator, valset=valset)
    prompt_first_cases = audit_prompt_first_outputs(evaluator=evaluator, valset=valset)
    all_cases = smoke_cases + prompt_first_cases

    payload.update(discovery)
    payload["dataset_source"] = dataset_source
    payload["cases"] = all_cases
    payload["summary"] = {
        "stage2c_smoke": build_summary(smoke_cases),
        "stage2c_prompt_first_preview": build_summary(prompt_first_cases),
        "all_cases": build_summary(all_cases),
    }
    write_json(run_dir / "stage2d_existing_outputs_answer_extractability_audit.json", payload)
    write_text(
        run_dir / "notes.md",
        "\n".join(
            [
                "# Stage 2D existing outputs answer-extractability audit",
                "",
                "- 本脚本只读已有 Stage 2C smoke 与 prompt-first 输出。",
                "- 本脚本不调用模型。",
                "- 本脚本不调用 `gepa.optimize()`。",
                "- prompt-first 结果仅保存 preview，相关审计只代表 preview 级别证据。",
                "",
            ]
        ),
    )
    return run_dir, payload


def main() -> None:
    run_dir, payload = run_existing_outputs_audit(DEFAULT_OUTPUT_DIR)
    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "path_type": PATH_TYPE,
                "evaluator_discovery_failed": payload.get("evaluator_discovery_failed", False),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
