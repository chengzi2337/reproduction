from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SPEC = importlib.util.spec_from_file_location(
    "stage2a_mimo_prompt_complexity_decomposition_script",
    PROJECT_ROOT / "scripts" / "stage2a_diagnose_mimo_prompt_complexity_decomposition.py",
)
assert SPEC is not None and SPEC.loader is not None
stage2a_decomposition_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage2a_decomposition_script)


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


def test_build_levels_contains_level_0_to_5() -> None:
    levels = stage2a_decomposition_script.build_decomposition_levels("AIME question")
    assert [item["level_id"] for item in levels] == [0, 1, 2, 3, 4, 5]
    assert levels[0]["prompt_type"] == "simple_ok_prompt"
    assert levels[5]["prompt_type"] == "official_aime_style_seed_prompt_plus_real_aime_question"


def test_payload_marks_first_blocked_level() -> None:
    levels = stage2a_decomposition_script.build_decomposition_levels("AIME question")
    level_results = [
        {
            "level_id": 0,
            "prompt_type": "simple_ok_prompt",
            "messages_shape": "user_only",
            "direct_sdk_result": _ok_result("OK"),
            "litellm_result": _ok_result("OK"),
            "blocked": False,
        },
        {
            "level_id": 1,
            "prompt_type": "very_short_math_prompt",
            "messages_shape": "user_only",
            "direct_sdk_result": _blocked_result(),
            "litellm_result": _blocked_result(),
            "blocked": True,
        },
    ]
    payload = stage2a_decomposition_script.build_decomposition_payload(
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        model="mimo-v2.5-pro",
        dataset_source="gepa.examples.aime.init_dataset()",
        levels=levels[:2],
        level_results=level_results,
        timeout_seconds=120.0,
        proxy_env_detected={"http_proxy_set": True, "https_proxy_set": True},
    )
    assert payload["path_type"] == "stage2a_mimo_prompt_complexity_decomposition"
    assert payload["strict_default_constraints"]["no_thinking_override"] is True
    assert payload["strict_default_constraints"]["no_max_completion_tokens_override"] is True
    assert payload["interpretation"]["no_gepa_optimize_called"] is True
    assert payload["interpretation"]["first_blocked_level"] == 1


def test_run_writes_json_without_api_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        stage2a_decomposition_script,
        "load_first_val_sample_via_init_dataset",
        lambda: ({"input": "question", "answer": "### 7"}, "gepa.examples.aime.init_dataset()"),
    )

    def _fake_run_level_diagnosis(**kwargs):
        level = kwargs["level"]
        if level["level_id"] == 0:
            return {
                "level_id": 0,
                "prompt_type": level["prompt_type"],
                "messages_shape": level["messages_shape"],
                "direct_sdk_result": _ok_result("OK"),
                "litellm_result": _ok_result("OK"),
                "blocked": False,
            }
        return {
            "level_id": level["level_id"],
            "prompt_type": level["prompt_type"],
            "messages_shape": level["messages_shape"],
            "direct_sdk_result": _blocked_result(),
            "litellm_result": _blocked_result(),
            "blocked": True,
        }

    monkeypatch.setattr(stage2a_decomposition_script, "run_level_diagnosis", _fake_run_level_diagnosis)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:10808")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:10808")

    run_dir = stage2a_decomposition_script.run_prompt_complexity_decomposition(
        api_key="tp-secret-should-not-leak",
        api_base="https://token-plan-cn.xiaomimimo.com/v1",
        model="mimo-v2.5-pro",
        timeout_seconds=120.0,
        output_root=tmp_path,
    )
    payload = json.loads((run_dir / "prompt_complexity_decomposition.json").read_text(encoding="utf-8"))
    text = (run_dir / "prompt_complexity_decomposition.json").read_text(encoding="utf-8")
    assert payload["path_type"] == "stage2a_mimo_prompt_complexity_decomposition"
    assert len(payload["levels"]) == 6
    assert payload["levels"][0]["prompt_type"] == "simple_ok_prompt"
    assert payload["levels"][4]["prompt_type"] == "readme_seed_prompt_plus_real_aime_question"
    assert payload["interpretation"]["no_gepa_optimize_called"] is True
    assert "tp-secret-should-not-leak" not in text


def test_hard_timeout_is_recorded_as_blocker() -> None:
    result = stage2a_decomposition_script._hard_timeout_result(timeout_seconds=30.0)
    assert result["ok"] is False
    assert result["error_type"] == "HardTimeout"
    assert result["content_nonempty"] is False
