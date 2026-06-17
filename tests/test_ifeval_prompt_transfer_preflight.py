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
    monkeypatch.setattr(module.importlib.util, "find_spec", lambda _name: None)
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
    monkeypatch.setattr(module.importlib.util, "find_spec", lambda _name: None)

    result = module.inspect_rule_checker()

    assert result["checker_status"] == "checker_unavailable"
    assert result["llm_judge_enabled"] is False
    assert result["mock_prediction_probe"]["structured_result"]["prompt_level_passed"] is False


def test_markdown_and_json_outputs_are_nonempty_and_parseable(monkeypatch) -> None:
    module = load_module(PREFLIGHT_PATH, "ifeval_prompt_transfer_preflight_reports")
    monkeypatch.setattr(module.importlib.util, "find_spec", lambda _name: None)
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
    monkeypatch.setattr(preflight_module.importlib.util, "find_spec", lambda _name: None)
    runner = load_module(RUNNER_PATH, "ifeval_prompt_transfer_runner_dry")
    workspace = _workspace("runner_dry")
    output_json = workspace / "runner.json"

    exit_code = runner.main(
        [
            "--variant-config",
            str(VARIANT_CONFIG_PATH),
            "--dataset-path",
            str(workspace / "missing.jsonl"),
            "--output-json",
            str(output_json),
        ]
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "dry_run"
    assert payload["api_call_enabled"] is False


def test_enable_api_run_is_blocked_when_unimplemented(monkeypatch) -> None:
    preflight_module = load_module(PREFLIGHT_PATH, "scripts.ifeval_prompt_transfer_preflight")
    monkeypatch.setattr(preflight_module.importlib.util, "find_spec", lambda _name: None)
    runner = load_module(RUNNER_PATH, "ifeval_prompt_transfer_runner_blocked")
    workspace = _workspace("runner_blocked")
    output_json = workspace / "runner_blocked.json"

    exit_code = runner.main(
        [
            "--variant-config",
            str(VARIANT_CONFIG_PATH),
            "--dataset-path",
            str(workspace / "missing.jsonl"),
            "--output-json",
            str(output_json),
            "--enable-api-run",
        ]
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert exit_code == 2
    assert payload["status"] == "blocked"
    assert payload["api_call_enabled"] is False
    assert payload["real_run_implemented"] is False
