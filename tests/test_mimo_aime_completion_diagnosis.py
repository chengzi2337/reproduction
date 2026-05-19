from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SPEC = importlib.util.spec_from_file_location(
    "mimo_aime_completion_diagnosis_script",
    PROJECT_ROOT / "scripts" / "01_diagnose_mimo_aime_completion_latency.py",
)
assert SPEC is not None and SPEC.loader is not None
diagnosis_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnosis_script)


class _FakeDetails:
    reasoning_tokens = 77


class _FakeUsage:
    prompt_tokens = 11
    completion_tokens = 22
    total_tokens = 33
    completion_tokens_details = _FakeDetails()


class _FakeMessage:
    def __init__(self, content: str | None, reasoning_content: str | None) -> None:
        self.content = content
        self.reasoning_content = reasoning_content


def test_build_diagnosis_cases_builds_runner_model_matrix() -> None:
    cases = diagnosis_script.build_diagnosis_cases(
        models=["mimo-v2.5-pro"],
        thinking_types=["disabled", "enabled"],
        max_completion_tokens_values=[128, 256],
    )
    assert len(cases) == 8
    assert cases[0] == {
        "runner": "openai_sdk",
        "model": "mimo-v2.5-pro",
        "thinking_type": "disabled",
        "max_completion_tokens": 128,
    }
    assert cases[-1] == {
        "runner": "litellm",
        "model": "mimo-v2.5-pro",
        "thinking_type": "enabled",
        "max_completion_tokens": 256,
    }


def test_extract_message_fields_handles_content_and_reasoning_content() -> None:
    content, reasoning_content = diagnosis_script._extract_message_fields(
        _FakeMessage(content="### 42", reasoning_content="推理")
    )
    assert content == "### 42"
    assert reasoning_content == "推理"


def test_usage_payload_extracts_reasoning_tokens() -> None:
    payload = diagnosis_script._usage_payload(_FakeUsage())
    assert payload["prompt_tokens"] == 11
    assert payload["completion_tokens"] == 22
    assert payload["total_tokens"] == 33
    assert payload["completion_tokens_details"]["reasoning_tokens"] == 77


def test_summarize_results_counts_success_timeout_and_non_empty_content() -> None:
    summary = diagnosis_script.summarize_results(
        [
            {
                "ok": True,
                "timed_out": False,
                "content_empty": False,
                "reasoning_content_empty": True,
            },
            {
                "ok": False,
                "timed_out": True,
                "content_empty": True,
                "reasoning_content_empty": True,
            },
            {
                "ok": True,
                "timed_out": False,
                "content_empty": True,
                "reasoning_content_empty": False,
            },
        ]
    )
    assert summary == {
        "total_cases": 3,
        "ok_count": 2,
        "error_count": 1,
        "timeout_count": 1,
        "content_non_empty_count": 1,
        "reasoning_content_non_empty_count": 1,
    }
