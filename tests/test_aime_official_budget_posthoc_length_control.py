from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "audit_aime_official_budget_posthoc_length_control.py"

SPEC = importlib.util.spec_from_file_location("posthoc_length_control_script", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
audit_script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit_script
SPEC.loader.exec_module(audit_script)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_run(
    project_root: Path,
    run_dir_text: str,
    *,
    candidates: list[str] | None = None,
    scores: list[float] | None = None,
    best_idx: int = 1,
) -> None:
    run_dir = project_root / run_dir_text
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "seed_prompt.json", {"candidate": {"system_prompt": "seed prompt"}})
    _write_json(run_dir / "gepa_result_summary.json", {"best_score": 0.8})
    if candidates is None or scores is None:
        _write_json(run_dir / "raw_result.json", {"best_idx": best_idx})
        return
    _write_json(
        run_dir / "raw_result.json",
        {
            "best_idx": best_idx,
            "candidates": [{"system_prompt": prompt} for prompt in candidates],
            "val_aggregate_scores": scores,
        },
    )


def test_candidate_records_compute_gap_and_length_reduction() -> None:
    records = audit_script.build_candidate_records(
        candidates=[
            {"system_prompt": "short"},
            {"system_prompt": "best prompt with more words"},
        ],
        scores=[0.79, 0.8],
        best_idx=1,
    )

    assert records[0]["candidate_id"] == 0
    assert records[0]["is_shorter_than_best_candidate"] is True
    assert records[0]["score_gap_to_best_val"] == pytest.approx(0.01)
    assert records[1]["is_best_val_candidate"] is True
    assert records[1]["length_reduction_ratio"] == 0


def test_selection_rules_choose_shorter_near_best_candidate() -> None:
    candidate_records = audit_script.build_candidate_records(
        candidates=[
            {"system_prompt": "seed prompt"},
            {"system_prompt": "near best"},
            {"system_prompt": "best prompt with many many many words"},
        ],
        scores=[0.1, 0.78, 0.8],
        best_idx=2,
    )

    rules = {
        rule["rule"]: rule
        for rule in audit_script.apply_selection_rules(
            candidate_records=candidate_records,
            seed_prompt_chars=len("seed prompt"),
        )
    }

    assert rules["rule_a_best_val"]["selected_candidate_id"] == 2
    assert rules["rule_b_gap_0_02_shortest"]["selected_candidate_id"] == 1
    assert rules["rule_b_gap_0_02_shortest"]["chars_saved_vs_rule_a"] > 0
    assert rules["rule_d_seed_2x_cap_best_val"]["selection_available"] is True


def test_missing_candidate_artifacts_return_limitation(tmp_path: Path) -> None:
    run_dir_text = "outputs/run-missing/ts"
    _write_run(tmp_path, run_dir_text, candidates=None, scores=None)

    record = audit_script.audit_run(tmp_path, 0, run_dir_text)

    assert record["candidate_artifacts_available"] is False
    assert record["limitation"] == audit_script.LIMITATION_MESSAGE
    assert record["selection_rules"] == []


def test_audit_payload_and_report_include_required_flags(tmp_path: Path, monkeypatch) -> None:
    runs = ((0, "outputs/run0/ts"),)
    _write_run(
        tmp_path,
        "outputs/run0/ts",
        candidates=["seed prompt", "best candidate prompt"],
        scores=[0.1, 0.8],
        best_idx=1,
    )
    monkeypatch.setattr(audit_script, "create_timestamp", lambda: "20260525T210000+0800")

    payload = audit_script.build_audit_payload(tmp_path, runs)
    report = audit_script.render_report(payload)

    assert payload["metadata"]["not_new_experiment"] is True
    assert payload["metadata"]["posthoc_only"] is True
    assert payload["metadata"]["no_gepa_optimize_called"] is True
    assert payload["metadata"]["optimizer_not_modified"] is True
    assert payload["metadata"]["evaluator_not_modified"] is True
    assert payload["metadata"]["not_performance_claim"] is True
    assert payload["analysis"]["rules_with_near_best_shorter_selection_count"] == 0
    assert payload["analysis"]["supports_direct_length_controlled_gepa_experiment"] is False
    assert "`not_new_experiment = true`" in report
    assert "`posthoc_only = true`" in report
    assert "`no_gepa_optimize_called = true`" in report
    assert "不是 `Length-Controlled GEPA` 实验" in report


def test_main_writes_json_and_report_without_api_or_gepa_calls(tmp_path: Path, monkeypatch) -> None:
    runs = ((0, "outputs/run0/ts"),)
    _write_run(
        tmp_path,
        "outputs/run0/ts",
        candidates=["seed prompt", "best candidate prompt"],
        scores=[0.1, 0.8],
        best_idx=1,
    )
    monkeypatch.setattr(audit_script, "DEFAULT_RUNS", runs)
    monkeypatch.setattr(audit_script, "create_timestamp", lambda: "20260525T210500+0800")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_aime_official_budget_posthoc_length_control.py",
            "--project-root",
            str(tmp_path),
        ],
    )

    audit_script.main()

    audit_json = (
        tmp_path
        / "outputs"
        / "aime_official_budget_posthoc_length_control_audit"
        / "20260525T210500+0800"
        / "posthoc_length_control_audit.json"
    )
    report_path = tmp_path / "reports" / "aime_official_budget_posthoc_length_control_result.md"
    payload = json.loads(audit_json.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")

    assert payload["metadata"]["no_api_called"] is True
    assert payload["metadata"]["no_model_called"] is True
    assert payload["metadata"]["no_gepa_optimize_called"] is True
    assert "不调用模型、不调用 API、不调用 GEPA、不运行新实验" in report


def test_script_source_does_not_import_api_gepa_or_evaluator() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "import gepa" not in source
    assert "gepa.optimize" not in source
    assert "import openai" not in source
    assert "import litellm" not in source
    assert "evaluate_candidate" not in source
    assert "run_gepa_aime_experiment" not in source
