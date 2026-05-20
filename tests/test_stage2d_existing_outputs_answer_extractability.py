from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SPEC = importlib.util.spec_from_file_location(
    "stage2d_existing_outputs_answer_extractability_script",
    PROJECT_ROOT / "scripts" / "stage2d_audit_existing_outputs_answer_extractability.py",
)
assert SPEC is not None and SPEC.loader is not None
stage2d_existing_outputs_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage2d_existing_outputs_script)


class _FakeEvaluator:
    def __call__(self, data, response):
        score = 1.0 if data["answer"] in response else 0.0
        return type("Result", (), {"score": score})()


def test_build_case_distinguishes_official_and_relaxed() -> None:
    case = stage2d_existing_outputs_script._build_case(
        evaluator=_FakeEvaluator(),
        artifact_type="stage2c_smoke",
        source_content_complete=True,
        source_path="outputs/example.json",
        sample_index=0,
        response_text="### <answer>\n72\n</answer>",
        expected_answer="### 72",
    )
    assert case["content_nonempty"] is True
    assert case["official_evaluator_compatible"] is False
    assert case["strict_regex_match_###_integer"] is False
    assert case["relaxed_human_extractable"] is True
    assert case["relaxed_extracted_answer"] == "72"
    assert case["xml_tag_placeholder_misuse"] is True
    assert case["output_protocol_violation"] is True


def test_build_summary_counts() -> None:
    cases = [
        {
            "official_evaluator_compatible": True,
            "relaxed_human_extractable": True,
            "output_protocol_violation": False,
            "xml_tag_placeholder_misuse": False,
            "markdown_heading_misuse": False,
            "final_answer_missing": False,
        },
        {
            "official_evaluator_compatible": False,
            "relaxed_human_extractable": True,
            "output_protocol_violation": True,
            "xml_tag_placeholder_misuse": True,
            "markdown_heading_misuse": False,
            "final_answer_missing": False,
        },
    ]
    summary = stage2d_existing_outputs_script.build_summary(cases)
    assert summary["total_cases"] == 2
    assert summary["official_evaluator_compatible_count"] == 1
    assert summary["relaxed_human_extractable_count"] == 2
    assert summary["xml_tag_placeholder_misuse_count"] == 1


def test_existing_outputs_audit_output_has_no_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        stage2d_existing_outputs_script,
        "discover_official_evaluator",
        lambda: {
            "evaluator_discovery_failed": False,
            "official_evaluator_class": "fake",
            "official_evaluator_source_file": "fake.py",
            "official_evaluator_contract": "contains",
            "official_evaluator_source_snippet": "fake",
            "aime_dataset_source_file": "fake_aime.py",
            "aime_answer_contract": "### + integer",
            "aime_dataset_source_snippet": "fake",
            "evaluator": _FakeEvaluator(),
        },
    )
    monkeypatch.setattr(
        stage2d_existing_outputs_script,
        "_load_expected_answers",
        lambda: ([{"answer": "### 72"}], "dataset-source"),
    )
    monkeypatch.setattr(
        stage2d_existing_outputs_script,
        "audit_smoke_outputs",
        lambda **kwargs: [
            {
                "artifact_type": "stage2c_smoke",
                "source_content_complete": True,
                "source_path": "outputs/a.json",
                "sample_index": 0,
                "expected_official_answer": "### 72",
                "content_nonempty": True,
                "official_evaluator_compatible": False,
                "strict_regex_match_###_integer": False,
                "relaxed_human_extractable": True,
                "relaxed_extracted_answer": "72",
                "normalized_score": 1.0,
                "output_protocol_violation": True,
                "xml_tag_placeholder_misuse": True,
                "markdown_heading_misuse": False,
                "final_answer_missing": False,
                "classified_failure_mode": "xml_tag_placeholder_misuse",
                "response_preview": "### <answer>\\n72\\n</answer>",
            }
        ],
    )
    monkeypatch.setattr(stage2d_existing_outputs_script, "audit_prompt_first_outputs", lambda **kwargs: [])

    run_dir, payload = stage2d_existing_outputs_script.run_existing_outputs_audit(tmp_path)
    text = (run_dir / "stage2d_existing_outputs_answer_extractability_audit.json").read_text(encoding="utf-8")
    output = json.loads(text)
    assert output["path_type"] == "stage2d_existing_outputs_answer_extractability_audit"
    assert output["not_performance_claim"] is True
    assert output["summary"]["all_cases"]["xml_tag_placeholder_misuse_count"] == 1
    assert "tp-" not in text
