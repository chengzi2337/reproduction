from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = PROJECT_ROOT / "scripts" / "run_ifeval_prompt_transfer.py"
VARIANT_CONFIG_PATH = PROJECT_ROOT / "configs" / "ifeval_prompt_transfer_variants.json"


def _workspace(name: str) -> Path:
    path = PROJECT_ROOT / "outputs" / "tmp_run_ifeval_prompt_transfer_tests" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_ifeval_prompt_transfer_test_module", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_fake_ifeval_root(root: Path, sample_count: int = 2) -> Path:
    package = root / "instruction_following_eval"
    data_dir = package / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "instructions.py").write_text("", encoding="utf-8")
    (package / "instructions_registry.py").write_text("INSTRUCTION_DICT = {}\n", encoding="utf-8")
    (package / "instructions_util.py").write_text("", encoding="utf-8")
    (package / "evaluation_lib.py").write_text(
        "\n".join(
            [
                "from dataclasses import dataclass",
                "import json",
                "@dataclass",
                "class InputExample:",
                "    key: int",
                "    instruction_id_list: list",
                "    prompt: str",
                "    kwargs: list",
                "@dataclass",
                "class OutputExample:",
                "    instruction_id_list: list",
                "    prompt: str",
                "    response: str",
                "    follow_all_instructions: bool",
                "    follow_instruction_list: list",
                "def read_prompt_list(input_jsonl_filename):",
                "    with open(input_jsonl_filename, encoding='utf-8') as handle:",
                "        return [InputExample(**json.loads(line)) for line in handle if line.strip()]",
                "def test_instruction_following_strict(inp, prompt_to_response):",
                "    followed = bool(prompt_to_response[inp.prompt])",
                "    return OutputExample(inp.instruction_id_list, inp.prompt, prompt_to_response[inp.prompt], followed, [followed for _ in inp.instruction_id_list])",
                "def test_instruction_following_loose(inp, prompt_to_response):",
                "    return test_instruction_following_strict(inp, prompt_to_response)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    rows = []
    for index in range(sample_count):
        rows.append(
            {
                "key": index,
                "prompt": f"Say test {index}.",
                "instruction_id_list": ["keywords:existence"],
                "kwargs": [{"keywords": ["test"]}],
            }
        )
    (data_dir / "input_data.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return package


def test_dry_run_does_not_call_api(monkeypatch) -> None:
    runner = _load_runner()
    workspace = _workspace("dry_run")
    ifeval_root = _write_fake_ifeval_root(workspace)

    def fail_call_provider(**_kwargs):
        raise AssertionError("dry-run 不应调用 provider")

    monkeypatch.setattr(runner, "call_provider", fail_call_provider)
    exit_code = runner.main(
        [
            "--ifeval-root",
            str(ifeval_root),
            "--limit",
            "20",
            "--output-dir",
            str(workspace / "out"),
            "--dry-run",
        ]
    )

    summary = json.loads((workspace / "out" / "summary.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert summary["status"] == "dry_run"
    assert summary["api_call_enabled"] is False
    assert summary["canonical_aggregation_source"] == "deterministic_offline_checker"
    assert summary["langdetect_seed"] == 0
    assert summary["llm_judge_enabled"] is False


def test_api_run_requires_explicit_limit(monkeypatch) -> None:
    runner = _load_runner()
    workspace = _workspace("missing_limit")
    ifeval_root = _write_fake_ifeval_root(workspace)
    monkeypatch.setenv("IFEVAL_TEST_CREDENTIAL", "dummy")

    exit_code = runner.main(
        [
            "--ifeval-root",
            str(ifeval_root),
            "--credential-env",
            "IFEVAL_TEST_CREDENTIAL",
            "--disable-dspy-cache",
            "--enable-api-run",
            "--mock-provider",
            "--output-dir",
            str(workspace / "out"),
        ]
    )

    summary = json.loads((workspace / "out" / "summary.json").read_text(encoding="utf-8"))
    assert exit_code == 2
    assert "missing_explicit_limit" in summary["blocked_reasons"]


def test_mock_provider_generates_outputs_and_summary(monkeypatch) -> None:
    runner = _load_runner()
    workspace = _workspace("mock_provider")
    ifeval_root = _write_fake_ifeval_root(workspace)
    monkeypatch.setenv("IFEVAL_TEST_CREDENTIAL", "dummy")

    exit_code = runner.main(
        [
            "--ifeval-root",
            str(ifeval_root),
            "--credential-env",
            "IFEVAL_TEST_CREDENTIAL",
            "--limit",
            "20",
            "--disable-dspy-cache",
            "--enable-api-run",
            "--mock-provider",
            "--output-dir",
            str(workspace / "out"),
        ]
    )

    raw_lines = (workspace / "out" / "raw_outputs.jsonl").read_text(encoding="utf-8").splitlines()
    summary = json.loads((workspace / "out" / "summary.json").read_text(encoding="utf-8"))
    eval_results = json.loads((workspace / "out" / "eval_results.json").read_text(encoding="utf-8"))
    markdown = (workspace / "out" / "summary.md").read_text(encoding="utf-8")
    assert exit_code == 0
    assert len(raw_lines) == 12
    assert summary["status"] == "completed"
    assert summary["canonical_aggregation_source"] == "deterministic_offline_checker"
    assert summary["checker_determinism_status"] in {"set", "langdetect_unavailable"}
    assert eval_results["aggregation_source"] == "deterministic_offline_checker"
    assert eval_results["llm_judge_enabled"] is False
    assert eval_results["prompt_level_accuracy"] is not None
    assert markdown.strip()


def test_provider_error_sample_is_not_deleted(monkeypatch) -> None:
    runner = _load_runner()
    workspace = _workspace("provider_error")
    ifeval_root = _write_fake_ifeval_root(workspace, sample_count=1)
    monkeypatch.setenv("IFEVAL_TEST_CREDENTIAL", "dummy")

    def failing_call_provider(**_kwargs):
        raise TimeoutError("timeout without secret")

    monkeypatch.setattr(runner, "call_provider", failing_call_provider)
    exit_code = runner.main(
        [
            "--ifeval-root",
            str(ifeval_root),
            "--credential-env",
            "IFEVAL_TEST_CREDENTIAL",
            "--limit",
            "20",
            "--disable-dspy-cache",
            "--enable-api-run",
            "--output-dir",
            str(workspace / "out"),
        ]
    )

    raw_rows = [
        json.loads(line)
        for line in (workspace / "out" / "raw_outputs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert exit_code == 0
    assert len(raw_rows) == 6
    assert all(row["provider_status"] == "timeout" for row in raw_rows)
    assert all(row["score_policy"] == "official_checker_on_empty_response" for row in raw_rows)
