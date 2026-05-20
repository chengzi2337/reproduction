from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SPEC = importlib.util.spec_from_file_location(
    "stage2d_official_contract_prompt_adaptation_script",
    PROJECT_ROOT / "scripts" / "stage2d_diagnose_official_contract_prompt_adaptation.py",
)
assert SPEC is not None and SPEC.loader is not None
stage2d_prompt_adaptation_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage2d_prompt_adaptation_script)


def _samples(count: int) -> tuple[list[dict[str, str]], str]:
    base = [
        {"input": "sample-0", "answer": "### 42"},
        {"input": "sample-1", "answer": "### 73"},
        {"input": "sample-2", "answer": "### 104"},
        {"input": "sample-3", "answer": "### 215"},
        {"input": "sample-4", "answer": "### 386"},
    ]
    return base[:count], "dataset-source"


def test_prompt_variants_are_stage2d_d_e_f() -> None:
    variants = stage2d_prompt_adaptation_script.PROMPT_VARIANTS
    assert [variant["variant_id"] for variant in variants] == ["D", "E", "F"]
    assert "### 123" in variants[0]["system_prompt"]
    assert "### N" in variants[1]["system_prompt"]
    assert "grader only checks" in variants[2]["system_prompt"]
    assert all("<answer>" not in variant["system_prompt"].split("It must match this pattern:")[0] for variant in variants)


def test_evaluate_response_text_distinguishes_official_and_normalized() -> None:
    exact = stage2d_prompt_adaptation_script.evaluate_response_text("### 72", "### 72")
    assert exact["official_evaluator_compatible"] is True
    assert exact["official_score"] == 1.0
    assert exact["normalized_score"] == 1.0

    xml = stage2d_prompt_adaptation_script.evaluate_response_text("### <answer>\n72\n</answer>", "### 72")
    assert xml["official_evaluator_compatible"] is False
    assert xml["contains_xml_tag_placeholder"] is True
    assert xml["relaxed_human_extractable"] is True
    assert xml["normalized_extracted_answer"] == "72"
    assert xml["normalized_score"] == 1.0

    heading = stage2d_prompt_adaptation_script.evaluate_response_text("### Step 1\nFinal answer: 72", "### 72")
    assert heading["official_evaluator_compatible"] is False
    assert heading["contains_markdown_heading_misuse"] is True
    assert heading["classified_failure_mode"] == "markdown_heading_misuse"


def test_dry_run_does_not_call_model_functions(tmp_path, monkeypatch) -> None:
    called = {"direct": False, "litellm": False}
    monkeypatch.setattr(stage2d_prompt_adaptation_script, "load_val_samples", _samples)
    monkeypatch.setattr(
        stage2d_prompt_adaptation_script,
        "run_direct_sdk_completion",
        lambda **kwargs: called.__setitem__("direct", True),
    )
    monkeypatch.setattr(
        stage2d_prompt_adaptation_script,
        "run_litellm_completion",
        lambda **kwargs: called.__setitem__("litellm", True),
    )

    report_path = tmp_path / "result.md"
    run_dir, payload = stage2d_prompt_adaptation_script.run_official_contract_prompt_adaptation(
        api_key="",
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        model="mimo-v2.5-pro",
        sample_count=5,
        thinking_type="disabled",
        max_completion_tokens=2048,
        timeout_seconds=120.0,
        execute=False,
        output_root=tmp_path,
        result_report_path=report_path,
    )

    assert called["direct"] is False
    assert called["litellm"] is False
    assert payload["execute_diagnostic"] is False
    assert payload["model_invocation_attempted"] is False
    assert payload["sample_count"] == 5
    assert payload["summary"]["dry_run_only"] is True
    assert (run_dir / "stage2d_official_contract_prompt_adaptation_input_snapshot.json").exists()
    assert not (run_dir / "stage2d_official_contract_prompt_adaptation_results.json").exists()
    assert "没有调用模型" in report_path.read_text(encoding="utf-8")


def test_execute_records_summary_without_key_leak(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(stage2d_prompt_adaptation_script, "load_val_samples", _samples)

    def _answer_for_message(messages):
        user_text = messages[1]["content"]
        return {
            "sample-0": "42",
            "sample-1": "73",
            "sample-2": "104",
            "sample-3": "215",
            "sample-4": "386",
        }[user_text]

    def _fake_direct(**kwargs):
        answer = _answer_for_message(kwargs["messages"])
        return stage2d_prompt_adaptation_script.build_model_result(
            content=f"### {answer}",
            finish_reason="stop",
            elapsed_seconds=0.1,
        )

    def _fake_litellm(**kwargs):
        answer = _answer_for_message(kwargs["messages"])
        return stage2d_prompt_adaptation_script.build_model_result(
            content=f"### {answer}",
            finish_reason="stop",
            elapsed_seconds=0.1,
        )

    monkeypatch.setattr(stage2d_prompt_adaptation_script, "run_direct_sdk_completion", _fake_direct)
    monkeypatch.setattr(stage2d_prompt_adaptation_script, "run_litellm_completion", _fake_litellm)

    report_path = tmp_path / "result.md"
    run_dir, payload = stage2d_prompt_adaptation_script.run_official_contract_prompt_adaptation(
        api_key="tp-secret-do-not-leak",
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        model="mimo-v2.5-pro",
        sample_count=5,
        thinking_type="disabled",
        max_completion_tokens=2048,
        timeout_seconds=120.0,
        execute=True,
        output_root=tmp_path,
        result_report_path=report_path,
    )

    result_text = (run_dir / "stage2d_official_contract_prompt_adaptation_results.json").read_text(encoding="utf-8")
    output = json.loads(result_text)
    variant_d = output["summary"]["summary_by_variant"][0]
    assert output["path_type"] == "stage2d_official_contract_prompt_adaptation_diagnostic"
    assert len(output["cases"]) == 30
    assert variant_d["transport_paths"]["direct_sdk"]["official_evaluator_compatible_count"] == 5
    assert variant_d["transport_paths"]["litellm"]["official_evaluator_compatible_count"] == 5
    assert variant_d["both_paths_pass_gate"] is True
    assert output["summary"]["passing_variants"] == ["D", "E", "F"]
    assert "tp-secret-do-not-leak" not in result_text
    assert "tp-secret-do-not-leak" not in report_path.read_text(encoding="utf-8")


def test_missing_api_base_raises(tmp_path) -> None:
    with pytest.raises(ValueError, match="MIMO_API_BASE"):
        stage2d_prompt_adaptation_script.run_official_contract_prompt_adaptation(
            api_key="",
            api_base="",
            model="mimo-v2.5-pro",
            sample_count=5,
            thinking_type="disabled",
            max_completion_tokens=2048,
            timeout_seconds=120.0,
            execute=False,
            output_root=tmp_path,
        )


def test_execute_requires_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(stage2d_prompt_adaptation_script, "load_val_samples", _samples)
    with pytest.raises(ValueError, match="MIMO_API_KEY"):
        stage2d_prompt_adaptation_script.run_official_contract_prompt_adaptation(
            api_key="",
            api_base="https://token-plan-cn.xiaomimimo.com/v1",
            model="mimo-v2.5-pro",
            sample_count=5,
            thinking_type="disabled",
            max_completion_tokens=2048,
            timeout_seconds=120.0,
            execute=True,
            output_root=tmp_path,
        )


def test_script_does_not_reference_gepa_optimize() -> None:
    script_text = (PROJECT_ROOT / "scripts" / "stage2d_diagnose_official_contract_prompt_adaptation.py").read_text(
        encoding="utf-8"
    )
    assert "gepa.optimize" not in script_text
