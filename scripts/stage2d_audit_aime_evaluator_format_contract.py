from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.logging_utils import create_run_dir, write_json, write_text


PATH_TYPE = "stage2d_aime_evaluator_format_contract_audit"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "stage2d_aime_evaluator_format_contract_audit"
SYNTHETIC_SEMANTIC_ANSWER = 72
EXPECTED_OFFICIAL_ANSWER = "### 72"


def strict_regex_match_hash_integer(response_text: str) -> bool:
    return re.search(r"(?m)^###\s*\d+\s*$", response_text) is not None


def relaxed_extract_answer(response_text: str) -> str | None:
    patterns = [
        r"(?m)^###\s*(\d+)\s*$",
        r"###\s*<answer>\s*(\d+)\s*</answer>",
        r"###\s*<answer>\s*(\d+)",
        r"(?i)final answer:\s*(\d+)",
        r"\\boxed\{(\d+)\}",
        r"(?i)the answer is\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, response_text, re.DOTALL)
        if match:
            return match.group(1)
    return None


def classify_failure_mode(response_text: str, official_score: float) -> str:
    if official_score == 1.0:
        return "official_contract_pass"
    if "### <answer>" in response_text and "</answer>" in response_text:
        return "xml_tag_placeholder_misuse"
    if re.search(r"(?mi)^###\s*(step|part|solution|analysis)\b", response_text):
        return "markdown_heading_misuse"
    if "\\boxed{" in response_text:
        return "boxed_only"
    if re.search(r"(?i)final answer:\s*\d+", response_text):
        return "plain_final_answer_only"
    if re.search(r"(?i)the answer is\s*\d+", response_text):
        return "plain_sentence_answer_only"
    if relaxed_extract_answer(response_text):
        return "relaxed_extractable_but_not_official"
    return "final_answer_missing"


def discover_official_evaluator() -> dict[str, Any]:
    try:
        from gepa.adapters.default_adapter.default_adapter import ContainsAnswerEvaluator
        from gepa.examples import aime as aime_example
    except Exception as exc:
        return {
            "evaluator_discovery_failed": True,
            "discovery_error_type": type(exc).__name__,
            "discovery_error_message": str(exc),
        }

    evaluator = ContainsAnswerEvaluator()
    source_file = inspect.getsourcefile(ContainsAnswerEvaluator)
    source_snippet = inspect.getsource(ContainsAnswerEvaluator)
    aime_source_file = inspect.getsourcefile(aime_example.init_dataset)
    aime_source_snippet = inspect.getsource(aime_example.init_dataset)

    return {
        "evaluator_discovery_failed": False,
        "official_evaluator_class": "gepa.adapters.default_adapter.default_adapter.ContainsAnswerEvaluator",
        "official_evaluator_source_file": source_file,
        "official_evaluator_contract": "score=1.0 iff data['answer'] in response else failure_score",
        "official_evaluator_source_snippet": source_snippet,
        "aime_dataset_source_file": aime_source_file,
        "aime_answer_contract": '"answer" is built as "### " + str(x["answer"])',
        "aime_dataset_source_snippet": aime_source_snippet,
        "evaluator": evaluator,
    }


def build_synthetic_cases() -> list[dict[str, str]]:
    return [
        {"case_name": "exact_contract", "response_text": "### 72"},
        {"case_name": "xml_placeholder_multiline", "response_text": "### <answer>\n72\n</answer>"},
        {"case_name": "xml_placeholder_inline", "response_text": "### <answer> 72"},
        {"case_name": "plain_sentence", "response_text": "The answer is 72."},
        {"case_name": "final_answer_prefix", "response_text": "Final answer: 72."},
        {"case_name": "boxed_answer", "response_text": "\\boxed{72}"},
        {"case_name": "reasoning_then_exact_final", "response_text": "先分析题意。\n最后一行给出答案。\n### 72"},
        {
            "case_name": "markdown_heading_then_plain_final",
            "response_text": "### Step 1\n先做分析。\nFinal answer: 72",
        },
    ]


def run_contract_audit(output_root: Path) -> tuple[Path, dict[str, Any]]:
    discovery = discover_official_evaluator()
    run_dir = create_run_dir(output_root)

    payload: dict[str, Any] = {
        "path_type": PATH_TYPE,
        "provider": "mimo",
        "not_performance_claim": True,
        "not_gepa_path": True,
        "no_gepa_optimize_called": True,
        "normalized_score_is_diagnostic_only": True,
        "semantic_answer": SYNTHETIC_SEMANTIC_ANSWER,
    }

    if discovery["evaluator_discovery_failed"]:
        payload.update(discovery)
        write_json(run_dir / "stage2d_aime_evaluator_contract_audit.json", payload)
        write_text(
            run_dir / "notes.md",
            "# Stage 2D AIME evaluator format contract audit\n\n- official evaluator discovery failed\n",
        )
        return run_dir, payload

    evaluator = discovery.pop("evaluator")
    cases = []
    for case in build_synthetic_cases():
        response_text = case["response_text"]
        data = {"input": "synthetic", "additional_context": {}, "answer": EXPECTED_OFFICIAL_ANSWER}
        result = evaluator(data, response_text)
        official_score = float(result.score)
        exact_match = strict_regex_match_hash_integer(response_text)
        relaxed_answer = relaxed_extract_answer(response_text)
        cases.append(
            {
                "case_name": case["case_name"],
                "response_text": response_text,
                "semantic_answer": SYNTHETIC_SEMANTIC_ANSWER,
                "official_metric_score": official_score,
                "official_extracted_answer": EXPECTED_OFFICIAL_ANSWER if official_score == 1.0 else None,
                "strict_regex_match_###_integer": exact_match,
                "normalized_score": 1.0 if relaxed_answer == str(SYNTHETIC_SEMANTIC_ANSWER) else 0.0,
                "normalized_extracted_answer": relaxed_answer,
                "classified_failure_mode": classify_failure_mode(response_text, official_score),
            }
        )

    payload.update(discovery)
    payload["expected_official_answer"] = EXPECTED_OFFICIAL_ANSWER
    payload["cases"] = cases
    write_json(run_dir / "stage2d_aime_evaluator_contract_audit.json", payload)
    write_text(
        run_dir / "notes.md",
        "\n".join(
            [
                "# Stage 2D AIME evaluator format contract audit",
                "",
                "- 本脚本不调用模型。",
                "- 本脚本不调用 `gepa.optimize()`。",
                "- 本脚本只审计 official evaluator 对 synthetic responses 的计分契约。",
                "",
            ]
        ),
    )
    return run_dir, payload


def main() -> None:
    run_dir, payload = run_contract_audit(DEFAULT_OUTPUT_DIR)
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
