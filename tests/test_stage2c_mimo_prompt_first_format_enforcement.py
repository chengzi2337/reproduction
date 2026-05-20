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
    "stage2c_mimo_prompt_first_format_enforcement_script",
    PROJECT_ROOT / "scripts" / "stage2c_diagnose_mimo_prompt_first_format_enforcement.py",
)
assert SPEC is not None and SPEC.loader is not None
stage2c_prompt_first_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage2c_prompt_first_script)


def _ok_result(content: str, finish_reason: str = "stop") -> dict[str, object]:
    return {
        "ok": True,
        "elapsed_seconds": 1.0,
        "status_code": 200,
        "content_nonempty": True,
        "content_preview": content,
        "reasoning_content_nonempty": False,
        "finish_reason": finish_reason,
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "completion_tokens_details": {"reasoning_tokens": 0},
        },
        "exact_final_answer_format_present": stage2c_prompt_first_script.exact_final_answer_format_present(content),
        "first_line_matches_###_integer": stage2c_prompt_first_script.first_line_matches_final_answer(content),
        "contains_markdown_step_heading": stage2c_prompt_first_script.contains_markdown_step_heading(content),
        "truncated_before_final": stage2c_prompt_first_script.looks_truncated(content, finish_reason),
        "error_type": None,
        "error_message": None,
    }


def test_dry_run_does_not_call_network_functions(tmp_path, monkeypatch) -> None:
    called = {"direct": False, "litellm": False}

    monkeypatch.setattr(
        stage2c_prompt_first_script,
        "load_val_samples",
        lambda sample_count: ([{"input": "sample-0"}, {"input": "sample-1"}, {"input": "sample-2"}][:sample_count], "dataset-source"),
    )
    monkeypatch.setattr(
        stage2c_prompt_first_script,
        "run_direct_sdk_format_check",
        lambda **kwargs: called.__setitem__("direct", True),
    )
    monkeypatch.setattr(
        stage2c_prompt_first_script,
        "run_litellm_format_check",
        lambda **kwargs: called.__setitem__("litellm", True),
    )

    run_dir = stage2c_prompt_first_script.run_prompt_first_format_diagnostic(
        api_key="",
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        model="mimo-v2.5-pro",
        sample_count=3,
        thinking_type="disabled",
        max_completion_tokens=2048,
        timeout_seconds=120.0,
        execute=False,
        output_root=tmp_path,
    )
    snapshot = json.loads((run_dir / "stage2c_prompt_first_input_snapshot.json").read_text(encoding="utf-8"))
    assert called["direct"] is False
    assert called["litellm"] is False
    assert snapshot["path_type"] == "stage2c_mimo_prompt_first_format_enforcement_diagnostic"
    assert snapshot["sample_count"] == 3
    assert snapshot["max_completion_tokens"] == 2048
    assert len(snapshot["prompt_variants"]) == 3
    assert "stage2c_prompt_first_results.json" not in {p.name for p in run_dir.iterdir()}


def test_execute_records_results_without_api_key_leak(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        stage2c_prompt_first_script,
        "load_val_samples",
        lambda sample_count: (
            [{"input": "sample-0"}, {"input": "sample-1"}, {"input": "sample-2"}][:sample_count],
            "dataset-source",
        ),
    )

    def _variant_id_from_messages(messages):
        system_prompt = messages[0]["content"]
        for variant in stage2c_prompt_first_script.PROMPT_VARIANTS:
            if variant["system_prompt"] == system_prompt:
                return variant["variant_id"]
        raise AssertionError("未识别的 prompt variant")

    def _fake_direct(**kwargs):
        variant_id = _variant_id_from_messages(kwargs["messages"])
        if variant_id == "A":
            return _ok_result("### 7")
        if variant_id == "B":
            return _ok_result("### 8\nBrief explanation.")
        return _ok_result("### Step 1\nCompute the sum.", finish_reason="length")

    def _fake_litellm(**kwargs):
        variant_id = _variant_id_from_messages(kwargs["messages"])
        if variant_id == "A":
            return _ok_result("### 7")
        if variant_id == "B":
            return _ok_result("### 8\nExplanation.")
        return _ok_result("### Step 1\nContinue solving.", finish_reason="length")

    monkeypatch.setattr(stage2c_prompt_first_script, "run_direct_sdk_format_check", _fake_direct)
    monkeypatch.setattr(stage2c_prompt_first_script, "run_litellm_format_check", _fake_litellm)

    run_dir = stage2c_prompt_first_script.run_prompt_first_format_diagnostic(
        api_key="tp-secret-do-not-leak",
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        model="mimo-v2.5-pro",
        sample_count=3,
        thinking_type="disabled",
        max_completion_tokens=2048,
        timeout_seconds=120.0,
        execute=True,
        output_root=tmp_path,
    )
    payload_text = (run_dir / "stage2c_prompt_first_results.json").read_text(encoding="utf-8")
    payload = json.loads(payload_text)
    assert payload["path_type"] == "stage2c_mimo_prompt_first_format_enforcement_diagnostic"
    assert payload["generation_control"]["max_completion_tokens"] == 2048
    assert len(payload["results"]) == 9
    assert payload["summary_by_variant"][0]["direct_sdk_exact_format_hits"] == 3
    assert payload["summary_by_variant"][2]["direct_sdk_length_finishes"] == 3
    assert "tp-secret-do-not-leak" not in payload_text


def test_missing_api_base_raises(tmp_path) -> None:
    with pytest.raises(ValueError, match="MIMO_API_BASE"):
        stage2c_prompt_first_script.run_prompt_first_format_diagnostic(
            api_key="",
            api_base="",
            model="mimo-v2.5-pro",
            sample_count=3,
            thinking_type="disabled",
            max_completion_tokens=2048,
            timeout_seconds=120.0,
            execute=False,
            output_root=tmp_path,
        )


def test_execute_requires_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        stage2c_prompt_first_script,
        "load_val_samples",
        lambda sample_count: ([{"input": "sample-0"}], "dataset-source"),
    )
    with pytest.raises(ValueError, match="MIMO_API_KEY"):
        stage2c_prompt_first_script.run_prompt_first_format_diagnostic(
            api_key="",
            api_base="https://token-plan-cn.xiaomimimo.com/v1",
            model="mimo-v2.5-pro",
            sample_count=1,
            thinking_type="disabled",
            max_completion_tokens=2048,
            timeout_seconds=120.0,
            execute=True,
            output_root=tmp_path,
        )


def test_format_detection_helpers() -> None:
    assert stage2c_prompt_first_script.exact_final_answer_format_present("### 42") is True
    assert stage2c_prompt_first_script.exact_final_answer_format_present("### Step 1") is False
    assert stage2c_prompt_first_script.first_line_matches_final_answer("### 42\nExplanation") is True
    assert stage2c_prompt_first_script.first_line_matches_final_answer("Answer:\n### 42") is False
    assert stage2c_prompt_first_script.contains_markdown_step_heading("### Step 1\nDo this") is True
    assert stage2c_prompt_first_script.contains_markdown_step_heading("### 42") is False
    assert stage2c_prompt_first_script.looks_truncated("We continue solving", "length") is True
    assert stage2c_prompt_first_script.looks_truncated("### 42", "stop") is False
