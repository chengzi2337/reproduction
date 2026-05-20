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
    "stage2c_mimo_parameter_adjustment_script",
    PROJECT_ROOT / "scripts" / "stage2c_diagnose_mimo_parameter_adjustment.py",
)
assert SPEC is not None and SPEC.loader is not None
stage2c_parameter_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage2c_parameter_script)


def _ok_result(content: str) -> dict[str, object]:
    return {
        "ok": True,
        "elapsed_seconds": 1.0,
        "status_code": 200,
        "content_nonempty": True,
        "content_preview": content,
        "contains_hash_heading": "###" in content,
        "contains_final_answer_format": "### <answer>" in content,
        "looks_truncated": False,
        "reasoning_content_nonempty": False,
        "finish_reason": "stop",
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "completion_tokens_details": {"reasoning_tokens": 0},
        },
        "error_type": None,
        "error_message": None,
    }


def test_parse_token_caps() -> None:
    assert stage2c_parameter_script.parse_token_caps("1024, 2048") == [1024, 2048]


def test_dry_run_does_not_call_network_functions(tmp_path, monkeypatch) -> None:
    called = {"direct": False, "litellm": False}

    monkeypatch.setattr(
        stage2c_parameter_script,
        "load_first_val_sample_via_init_dataset",
        lambda: ({"input": "question"}, "dataset-source"),
    )
    monkeypatch.setattr(
        stage2c_parameter_script,
        "run_direct_sdk_controlled_generation",
        lambda **kwargs: called.__setitem__("direct", True),
    )
    monkeypatch.setattr(
        stage2c_parameter_script,
        "run_litellm_controlled_generation",
        lambda **kwargs: called.__setitem__("litellm", True),
    )

    run_dir = stage2c_parameter_script.run_parameter_adjustment_diagnostic(
        api_key="",
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        model="mimo-v2.5-pro",
        thinking_type="disabled",
        token_caps=[1024, 2048],
        timeout_seconds=120.0,
        execute=False,
        output_root=tmp_path,
    )
    snapshot = json.loads((run_dir / "stage2c_parameter_adjustment_input_snapshot.json").read_text(encoding="utf-8"))
    assert called["direct"] is False
    assert called["litellm"] is False
    assert snapshot["path_type"] == "stage2c_mimo_parameter_adjustment_diagnostic"
    assert snapshot["token_caps"] == [1024, 2048]
    assert snapshot["not_gepa_path"] is True
    assert "stage2c_parameter_adjustment_results.json" not in {p.name for p in run_dir.iterdir()}


def test_execute_records_results_without_api_key_leak(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        stage2c_parameter_script,
        "load_first_val_sample_via_init_dataset",
        lambda: ({"input": "question"}, "dataset-source"),
    )

    def _fake_direct(**kwargs):
        cap = kwargs["max_completion_tokens"]
        if cap == 1024:
            return _ok_result("### <answer>\n### 7")
        return _ok_result("Step 1...\nStep 2...\n### <answer>\n### 7")

    def _fake_litellm(**kwargs):
        cap = kwargs["max_completion_tokens"]
        if cap == 1024:
            return _ok_result("### <answer>\n### 7")
        return _ok_result("### <answer>\n### 9")

    monkeypatch.setattr(stage2c_parameter_script, "run_direct_sdk_controlled_generation", _fake_direct)
    monkeypatch.setattr(stage2c_parameter_script, "run_litellm_controlled_generation", _fake_litellm)

    run_dir = stage2c_parameter_script.run_parameter_adjustment_diagnostic(
        api_key="tp-secret-do-not-leak",
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        model="mimo-v2.5-pro",
        thinking_type="disabled",
        token_caps=[1024, 2048],
        timeout_seconds=120.0,
        execute=True,
        output_root=tmp_path,
    )
    payload_text = (run_dir / "stage2c_parameter_adjustment_results.json").read_text(encoding="utf-8")
    payload = json.loads(payload_text)
    assert payload["path_type"] == "stage2c_mimo_parameter_adjustment_diagnostic"
    assert payload["parameter_adjustment_scope"]["token_caps"] == [1024, 2048]
    assert len(payload["results_by_token_cap"]) == 2
    assert payload["results_by_token_cap"][0]["direct_sdk_result"]["contains_final_answer_format"] is True
    assert "tp-secret-do-not-leak" not in payload_text


def test_missing_api_base_raises(tmp_path) -> None:
    with pytest.raises(ValueError, match="MIMO_API_BASE"):
        stage2c_parameter_script.run_parameter_adjustment_diagnostic(
            api_key="",
            api_base="",
            model="mimo-v2.5-pro",
            thinking_type="disabled",
            token_caps=[1024],
            timeout_seconds=120.0,
            execute=False,
            output_root=tmp_path,
        )


def test_execute_requires_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        stage2c_parameter_script,
        "load_first_val_sample_via_init_dataset",
        lambda: ({"input": "question"}, "dataset-source"),
    )
    with pytest.raises(ValueError, match="MIMO_API_KEY"):
        stage2c_parameter_script.run_parameter_adjustment_diagnostic(
            api_key="",
            api_base="https://token-plan-cn.xiaomimimo.com/v1",
            model="mimo-v2.5-pro",
            thinking_type="disabled",
            token_caps=[1024],
            timeout_seconds=120.0,
            execute=True,
            output_root=tmp_path,
        )


def test_final_answer_detection_and_truncation_heuristic() -> None:
    assert stage2c_parameter_script._contains_final_answer_format("### <answer>\n### 7") is True
    assert stage2c_parameter_script._contains_final_answer_format("### Step 1") is False
    assert stage2c_parameter_script._looks_truncated("Thus, $P(0)+Q(0) =") is True
    assert stage2c_parameter_script._looks_truncated("Sum = 1684.") is False
