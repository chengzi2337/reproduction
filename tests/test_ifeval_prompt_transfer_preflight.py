from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_PATH = PROJECT_ROOT / "scripts" / "ifeval_prompt_transfer_preflight.py"
RUNNER_PATH = PROJECT_ROOT / "scripts" / "run_ifeval_prompt_transfer.py"
VARIANT_CONFIG_PATH = PROJECT_ROOT / "configs" / "ifeval_prompt_transfer_variants.json"


def _workspace(name: str) -> Path:
    path = PROJECT_ROOT / "outputs" / "tmp_ifeval_prompt_transfer_tests" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_fake_ifeval_root(root: Path) -> Path:
    package = root / "instruction_following_eval"
    data_dir = package / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "instructions.py").write_text("class DummyInstruction:\n    pass\n", encoding="utf-8")
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
                "    items = []",
                "    with open(input_jsonl_filename, encoding='utf-8') as handle:",
                "        for line in handle:",
                "            payload = json.loads(line)",
                "            items.append(InputExample(**payload))",
                "    return items",
                "def test_instruction_following_strict(inp, prompt_to_response):",
                "    response = prompt_to_response[inp.prompt]",
                "    return OutputExample(inp.instruction_id_list, inp.prompt, response, False, [False for _ in inp.instruction_id_list])",
                "def test_instruction_following_loose(inp, prompt_to_response):",
                "    response = prompt_to_response[inp.prompt]",
                "    return OutputExample(inp.instruction_id_list, inp.prompt, response, False, [False for _ in inp.instruction_id_list])",
                "",
            ]
        ),
        encoding="utf-8",
    )
    sample = {
        "key": 1,
        "prompt": "Return the word alpha.",
        "instruction_id_list": ["keywords:existence"],
        "kwargs": [{"keywords": ["alpha"]}],
    }
    (data_dir / "input_data.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
    return package


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_variant_schema_completeness() -> None:
    module = load_module(PREFLIGHT_PATH, "ifeval_prompt_transfer_preflight_schema")
    variants = module.load_variants(VARIANT_CONFIG_PATH)

    assert len(variants) == 6
    assert [variant["display_name"] for variant in variants] == [
        "Baseline",
        "Baseline + MHC",
        "Verbose/helpfulness",
        "MHC + concise",
        "IFBench GEPA prompt transfer",
        "GEPA + P2 transfer",
    ]
    for variant in variants:
        assert set(module.REQUIRED_VARIANT_FIELDS).issubset(variant)
        assert variant["prompt_delta"]
        assert variant["risk_notes"]


def test_preflight_does_not_enable_api_calls(monkeypatch) -> None:
    module = load_module(PREFLIGHT_PATH, "ifeval_prompt_transfer_preflight_no_api")
    monkeypatch.delenv("IFEVAL_ROOT", raising=False)
    workspace = _workspace("preflight_no_api")

    result = module.build_preflight_result(
        variant_config_path=VARIANT_CONFIG_PATH,
        dataset_path=workspace / "missing.jsonl",
    )

    assert result["api_call_enabled"] is False
    assert result["full_budget_gepa_enabled"] is False
    assert result["status"] == "blocked"


def test_dataset_missing_returns_structured_status() -> None:
    module = load_module(PREFLIGHT_PATH, "ifeval_prompt_transfer_preflight_dataset")
    workspace = _workspace("dataset_missing")

    result = module.load_ifeval_dataset(workspace / "missing.jsonl")

    assert result["dataset_status"] == "dataset_missing"
    assert result["sample_count_detected"] == 0
    assert result["samples_preview"] == []
    assert result["repair_suggestion"]


def test_checker_unavailable_returns_structured_status(monkeypatch) -> None:
    module = load_module(PREFLIGHT_PATH, "ifeval_prompt_transfer_preflight_checker")
    monkeypatch.delenv("IFEVAL_ROOT", raising=False)

    result = module.inspect_rule_checker()

    assert result["checker_status"] == "checker_unavailable"
    assert result["llm_judge_enabled"] is False
    assert "ifeval-root" in result["repair_suggestion"]


def test_markdown_and_json_outputs_are_nonempty_and_parseable(monkeypatch) -> None:
    module = load_module(PREFLIGHT_PATH, "ifeval_prompt_transfer_preflight_reports")
    monkeypatch.delenv("IFEVAL_ROOT", raising=False)
    workspace = _workspace("reports")
    report_json = workspace / "preflight.json"
    report_md = workspace / "preflight.md"

    exit_code = module.main(
        [
            "--variant-config",
            str(VARIANT_CONFIG_PATH),
            "--dataset-path",
            str(workspace / "missing.jsonl"),
            "--report-json",
            str(report_json),
            "--report-md",
            str(report_md),
        ]
    )

    assert exit_code == 0
    parsed = json.loads(report_json.read_text(encoding="utf-8"))
    markdown = report_md.read_text(encoding="utf-8")
    assert parsed["dataset_status"] == "dataset_missing"
    assert parsed["checker_status"] == "checker_unavailable"
    assert markdown.strip()
    assert "不使用 LLM judge" in markdown


def test_runner_stub_defaults_to_dry_run_without_real_api(monkeypatch) -> None:
    preflight_module = load_module(PREFLIGHT_PATH, "scripts.ifeval_prompt_transfer_preflight")
    monkeypatch.delenv("IFEVAL_ROOT", raising=False)
    runner = load_module(RUNNER_PATH, "ifeval_prompt_transfer_runner_dry")
    workspace = _workspace("runner_dry")
    output_dir = workspace / "out"

    exit_code = runner.main(
        [
            "--variant-config",
            str(VARIANT_CONFIG_PATH),
            "--dataset-path",
            str(workspace / "missing.jsonl"),
            "--output-dir",
            str(output_dir),
        ]
    )

    payload = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "dry_run"
    assert payload["api_call_enabled"] is False


def test_enable_api_run_is_blocked_when_unimplemented(monkeypatch) -> None:
    preflight_module = load_module(PREFLIGHT_PATH, "scripts.ifeval_prompt_transfer_preflight")
    monkeypatch.delenv("IFEVAL_ROOT", raising=False)
    runner = load_module(RUNNER_PATH, "ifeval_prompt_transfer_runner_blocked")
    workspace = _workspace("runner_blocked")
    output_dir = workspace / "out"

    exit_code = runner.main(
        [
            "--variant-config",
            str(VARIANT_CONFIG_PATH),
            "--dataset-path",
            str(workspace / "missing.jsonl"),
            "--output-dir",
            str(output_dir),
            "--enable-api-run",
        ]
    )

    payload = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert exit_code == 2
    assert payload["status"] == "blocked"
    assert payload["api_call_enabled"] is False
    assert "preflight_not_ready" in payload["blocked_reasons"]
    assert "missing_provider_credential" in payload["blocked_reasons"]


def test_fake_ifeval_root_makes_preflight_ready(monkeypatch) -> None:
    module = load_module(PREFLIGHT_PATH, "ifeval_prompt_transfer_preflight_ready")
    monkeypatch.delenv("IFEVAL_ROOT", raising=False)
    workspace = _workspace("ready")
    ifeval_root = _write_fake_ifeval_root(workspace)
    report_json = workspace / "ready.json"
    report_md = workspace / "ready.md"

    exit_code = module.main(
        [
            "--variant-config",
            str(VARIANT_CONFIG_PATH),
            "--ifeval-root",
            str(ifeval_root),
            "--report-json",
            str(report_json),
            "--report-md",
            str(report_md),
        ]
    )

    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "ready"
    assert payload["dataset_status"] == "ok"
    assert payload["checker_status"] == "ok"
    assert payload["checker_smoke_status"] == "ok"
    assert payload["api_call_enabled"] is False
    assert payload["full_budget_gepa_enabled"] is False
    assert report_md.read_text(encoding="utf-8").strip()
