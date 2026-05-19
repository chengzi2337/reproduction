from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SPEC = importlib.util.spec_from_file_location(
    "stage2a_mimo_strict_default_path_blocker_script",
    PROJECT_ROOT / "scripts" / "stage2a_diagnose_mimo_strict_default_path_blocker.py",
)
assert SPEC is not None and SPEC.loader is not None
stage2a_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage2a_script)


def _ok_result(content: str = "OK") -> dict[str, object]:
    return {
        "ok": True,
        "elapsed_seconds": 1.2,
        "status_code": 200,
        "content_nonempty": True,
        "content_preview": content,
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
    }


def _blocked_result(error_type: str = "HardTimeout") -> dict[str, object]:
    return {
        "ok": False,
        "elapsed_seconds": 35.0,
        "status_code": None,
        "content_nonempty": False,
        "content_preview": None,
        "reasoning_content_nonempty": False,
        "finish_reason": None,
        "usage": {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "completion_tokens_details": {"reasoning_tokens": None},
        },
        "error_type": error_type,
        "error_message": "默认 completion 调用超过硬超时窗口。",
    }


def test_build_payload_records_ok_and_aime_prompts_separately() -> None:
    payload = stage2a_script.build_stage2a_payload(
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        model="mimo-v2.5-pro",
        dataset_source="gepa.examples.aime.init_dataset()",
        sample_index=0,
        ok_prompt_results={
            "direct_sdk_result": _ok_result("OK"),
            "litellm_result": _ok_result("OK"),
        },
        aime_prompt_results={
            "direct_sdk_result": _blocked_result(),
            "litellm_result": _blocked_result(),
        },
        timeout_seconds=120.0,
        proxy_env_detected={"http_proxy_set": True, "https_proxy_set": True},
    )
    assert payload["path_type"] == "stage2a_mimo_strict_default_path_blocker"
    assert payload["provider"] == "mimo"
    assert payload["strict_default_constraints"]["no_thinking_override"] is True
    assert payload["strict_default_constraints"]["no_max_completion_tokens_override"] is True
    assert payload["interpretation"]["no_gepa_optimize_called"] is True
    assert payload["ok_prompt"]["prompt_type"] == "simple_ok_prompt"
    assert payload["aime_prompt"]["prompt_type"] == "readme_quickstart_seed_prompt_plus_real_aime_question"
    assert payload["ok_prompt"]["direct_sdk_result"]["content_nonempty"] is True
    assert payload["aime_prompt"]["direct_sdk_result"]["content_nonempty"] is False
    assert payload["interpretation"]["blocker_detected"] is True


def test_run_validation_writes_json_without_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        stage2a_script,
        "load_first_val_sample_via_init_dataset",
        lambda: ({"input": "question", "answer": "### 7"}, "gepa.examples.aime.init_dataset()"),
    )
    monkeypatch.setattr(
        stage2a_script,
        "run_prompt_pair",
        lambda **kwargs: {
            "direct_sdk_result": _ok_result("OK" if kwargs["messages"][0]["content"] == "Return exactly: OK" else "### 7"),
            "litellm_result": _ok_result("OK" if kwargs["messages"][0]["content"] == "Return exactly: OK" else "### 7"),
        },
    )
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:10808")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:10808")

    run_dir = stage2a_script.run_stage2a_blocker_diagnosis(
        api_key="tp-secret-should-not-leak",
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        model="mimo-v2.5-pro",
        timeout_seconds=120.0,
        output_root=tmp_path,
    )
    payload = json.loads((run_dir / "strict_default_path_blocker.json").read_text(encoding="utf-8"))
    text = (run_dir / "strict_default_path_blocker.json").read_text(encoding="utf-8")
    assert payload["path_type"] == "stage2a_mimo_strict_default_path_blocker"
    assert payload["interpretation"]["no_gepa_optimize_called"] is True
    assert payload["ok_prompt"]["direct_sdk_result"]["content_nonempty"] is True
    assert payload["aime_prompt"]["litellm_result"]["content_nonempty"] is True
    assert "tp-secret-should-not-leak" not in text


def test_hard_timeout_is_recorded_as_blocker() -> None:
    result = stage2a_script._hard_timeout_result(timeout_seconds=30.0)
    assert result["ok"] is False
    assert result["error_type"] == "HardTimeout"
    assert result["content_nonempty"] is False


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

    result = stage2a_script._success_result(response=_Response(), elapsed_seconds=1.2)
    assert result["ok"] is False
    assert result["content_nonempty"] is False
    assert result["reasoning_content_nonempty"] is True


def test_error_result_redacts_api_key() -> None:
    exc = RuntimeError("bad key tp-secret-value")
    result = stage2a_script._error_result(
        exc=exc,
        api_key="tp-secret-value",
        elapsed_seconds=0.5,
    )
    assert result["ok"] is False
    assert "tp-secret-value" not in result["error_message"]
