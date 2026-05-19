from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SPEC = importlib.util.spec_from_file_location(
    "mimo_controlled_generation_path_script",
    PROJECT_ROOT / "scripts" / "02_validate_mimo_controlled_generation_path.py",
)
assert SPEC is not None and SPEC.loader is not None
stage2b_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage2b_script)


def test_build_payload_marks_stage2b_non_strict_and_no_gepa() -> None:
    payload = stage2b_script.build_controlled_generation_payload(
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        model="mimo-v2.5-pro",
        dataset_source="gepa.examples.aime.init_dataset()",
        sample_index=0,
        direct_sdk_result={
            "ok": True,
            "elapsed_seconds": 1.2,
            "status_code": None,
            "content_nonempty": True,
            "content_preview": "### 1",
            "reasoning_content_nonempty": False,
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 2,
                "total_tokens": 3,
                "completion_tokens_details": {"reasoning_tokens": 0},
            },
            "error_type": None,
            "error_message": None,
        },
        litellm_result={
            "ok": True,
            "elapsed_seconds": 1.3,
            "status_code": None,
            "content_nonempty": True,
            "content_preview": "### 1",
            "reasoning_content_nonempty": False,
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 2,
                "total_tokens": 3,
                "completion_tokens_details": {"reasoning_tokens": 0},
            },
            "error_type": None,
            "error_message": None,
        },
        thinking_type="disabled",
        max_completion_tokens=512,
        timeout_seconds=120.0,
        proxy_env_detected={"http_proxy_set": True, "https_proxy_set": True},
    )
    assert payload["path_type"] == "stage2b_mimo_controlled_generation_diagnostic_path"
    assert payload["provider"] == "mimo"
    assert payload["generation_control"]["thinking_type"] == "disabled"
    assert payload["generation_control"]["max_completion_tokens"] == 512
    assert payload["interpretation"]["no_gepa_optimize_called"] is True
    assert payload["interpretation"]["not_strict_official_path"] is True


def test_run_validation_writes_json_without_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        stage2b_script,
        "load_first_val_sample_via_init_dataset",
        lambda: ({"input": "question", "answer": "### 7"}, "gepa.examples.aime.init_dataset()"),
    )
    monkeypatch.setattr(
        stage2b_script,
        "run_direct_sdk_controlled_generation",
        lambda **kwargs: {
            "ok": True,
            "elapsed_seconds": 1.0,
            "status_code": 200,
            "content_nonempty": True,
            "content_preview": "### 7",
            "reasoning_content_nonempty": False,
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 2,
                "total_tokens": 3,
                "completion_tokens_details": {"reasoning_tokens": 0},
            },
            "error_type": None,
            "error_message": None,
        },
    )
    monkeypatch.setattr(
        stage2b_script,
        "run_litellm_controlled_generation",
        lambda **kwargs: {
            "ok": True,
            "elapsed_seconds": 1.1,
            "status_code": 200,
            "content_nonempty": True,
            "content_preview": "### 7",
            "reasoning_content_nonempty": False,
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 2,
                "total_tokens": 3,
                "completion_tokens_details": {"reasoning_tokens": 0},
            },
            "error_type": None,
            "error_message": None,
        },
    )
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:10808")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:10808")

    run_dir = stage2b_script.run_controlled_generation_validation(
        api_key="tp-secret-should-not-leak",
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        model="mimo-v2.5-pro",
        thinking_type="disabled",
        max_completion_tokens=512,
        timeout_seconds=120.0,
        output_root=tmp_path,
    )
    payload = json.loads((run_dir / "controlled_generation_results.json").read_text(encoding="utf-8"))
    text = (run_dir / "controlled_generation_results.json").read_text(encoding="utf-8")
    assert payload["path_type"] == "stage2b_mimo_controlled_generation_diagnostic_path"
    assert payload["provider"] == "mimo"
    assert payload["interpretation"]["not_strict_official_path"] is True
    assert payload["interpretation"]["no_gepa_optimize_called"] is True
    assert "tp-secret-should-not-leak" not in text


def test_success_result_with_empty_content_is_not_ok() -> None:
    class _Choice:
        finish_reason = "stop"
        message = type("Msg", (), {"content": "", "reasoning_content": "trace"})()

    class _Response:
        status_code = 200
        choices = [_Choice()]
        usage = type(
            "Usage",
            (),
            {
                "prompt_tokens": 10,
                "completion_tokens": 11,
                "total_tokens": 21,
                "completion_tokens_details": type("Details", (), {"reasoning_tokens": 9})(),
            },
        )()

    result = stage2b_script._success_result(response=_Response(), elapsed_seconds=1.2)
    assert result["ok"] is False
    assert result["content_nonempty"] is False
    assert result["reasoning_content_nonempty"] is True


def test_error_result_redacts_api_key() -> None:
    exc = RuntimeError("bad key tp-secret-value")
    result = stage2b_script._error_result(
        exc=exc,
        api_key="tp-secret-value",
        elapsed_seconds=0.5,
    )
    assert result["ok"] is False
    assert "tp-secret-value" not in result["error_message"]
