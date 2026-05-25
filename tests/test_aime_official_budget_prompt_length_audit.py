from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "audit_aime_official_budget_prompt_lengths.py"

SPEC = importlib.util.spec_from_file_location("prompt_length_audit_script", SCRIPT_PATH)
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
    seed_score: float,
    optimized_score: float,
    best_score: float,
    seed_prompt: str = "seed prompt",
    optimized_prompt: str = "optimized prompt\nwith more words",
) -> Path:
    run_dir = project_root / run_dir_text
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "seed_prompt.json", {"candidate": {"system_prompt": seed_prompt}})
    _write_json(run_dir / "optimized_prompt.json", {"candidate": {"system_prompt": optimized_prompt}})
    _write_json(
        run_dir / "gepa_result_summary.json",
        {
            "best_score": best_score,
            "num_candidates": 3,
            "num_full_val_evals": 3,
        },
    )
    _write_json(
        run_dir / "saved_prompt_eval_summary.json",
        {
            "seed_prompt_score": seed_score,
            "optimized_prompt_score": optimized_score,
            "score_delta": optimized_score - seed_score,
        },
    )
    return run_dir


def test_compute_prompt_stats_counts_chars_lines_words_and_token_estimate() -> None:
    stats = audit_script.compute_prompt_stats("one two\nthree")

    assert stats.chars == 13
    assert stats.lines == 2
    assert stats.words == 3
    assert stats.tokens_est == 3.25


def test_audit_run_extracts_scores_and_prompt_lengths(tmp_path: Path) -> None:
    run_dir_text = "outputs/fake-run/20260525T200000+0800"
    _write_run(
        tmp_path,
        run_dir_text,
        seed_score=0.2,
        optimized_score=0.7,
        best_score=0.8,
        seed_prompt="short seed",
        optimized_prompt="long optimized prompt\nsecond line",
    )

    record = audit_script.audit_run(tmp_path, 7, run_dir_text)

    assert record["seed"] == 7
    assert record["run_dir"] == run_dir_text
    assert record["seed_prompt_score"] == 0.2
    assert record["optimized_prompt_score"] == 0.7
    assert record["score_delta"] == pytest.approx(0.5)
    assert record["best_val_score"] == 0.8
    assert record["seed_prompt_chars"] == len("short seed")
    assert record["optimized_prompt_chars"] == len("long optimized prompt\nsecond line")
    assert record["prompt_char_growth"] > 0
    assert record["optimized_prompt_lines"] == 2
    assert record["optimized_prompt_words"] == 5
    assert record["num_candidates"] == 3
    assert record["num_full_val_evals"] == 3


def test_missing_artifact_fails_explicitly(tmp_path: Path) -> None:
    run_dir_text = "outputs/missing-artifact/20260525T200000+0800"
    run_dir = tmp_path / run_dir_text
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "seed_prompt.json", {"candidate": {"system_prompt": "seed"}})

    with pytest.raises(audit_script.AuditError, match="缺失必需 artifact"):
        audit_script.audit_run(tmp_path, 0, run_dir_text)


def test_build_audit_payload_and_report_include_boundary_flags(tmp_path: Path, monkeypatch) -> None:
    runs = (
        (0, "outputs/run0/ts"),
        (1, "outputs/run1/ts"),
    )
    _write_run(
        tmp_path,
        "outputs/run0/ts",
        seed_score=0.1,
        optimized_score=0.9,
        best_score=0.6,
        seed_prompt="seed",
        optimized_prompt="short optimized",
    )
    _write_run(
        tmp_path,
        "outputs/run1/ts",
        seed_score=0.2,
        optimized_score=0.5,
        best_score=0.7,
        seed_prompt="seed",
        optimized_prompt="this optimized prompt is much longer than run zero",
    )
    monkeypatch.setattr(audit_script, "create_timestamp", lambda: "20260525T200000+0800")

    payload = audit_script.build_audit_payload(tmp_path, runs)
    report = audit_script.render_report(payload)

    assert payload["metadata"]["not_new_experiment"] is True
    assert payload["metadata"]["no_gepa_optimize_called"] is True
    assert payload["metadata"]["not_performance_claim"] is True
    assert payload["metadata"]["token_estimate_for_audit_only"] is True
    assert payload["metadata"]["not_exact_tokenizer_count"] is True
    assert "`not_new_experiment = true`" in report
    assert "`no_gepa_optimize_called = true`" in report
    assert "`not_performance_claim = true`" in report
    assert "不是 `Length-Controlled GEPA` 实验" in report


def test_main_writes_json_and_report_without_api_or_gepa_calls(tmp_path: Path, monkeypatch) -> None:
    runs = ((0, "outputs/run0/ts"),)
    _write_run(
        tmp_path,
        "outputs/run0/ts",
        seed_score=0.1,
        optimized_score=0.4,
        best_score=0.5,
        seed_prompt="seed",
        optimized_prompt="optimized prompt with more text",
    )
    monkeypatch.setattr(audit_script, "DEFAULT_RUNS", runs)
    monkeypatch.setattr(audit_script, "create_timestamp", lambda: "20260525T200500+0800")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_aime_official_budget_prompt_lengths.py",
            "--project-root",
            str(tmp_path),
        ],
    )

    audit_script.main()

    audit_json = (
        tmp_path
        / "outputs"
        / "aime_official_budget_prompt_length_audit"
        / "20260525T200500+0800"
        / "prompt_length_audit.json"
    )
    report_path = tmp_path / "reports" / "aime_official_budget_prompt_length_audit_result.md"
    payload = json.loads(audit_json.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")

    assert payload["metadata"]["no_api_called"] is True
    assert payload["metadata"]["no_model_called"] is True
    assert payload["metadata"]["no_gepa_optimize_called"] is True
    assert "不调用模型、不调用 GEPA、不运行新实验" in report


def test_script_source_does_not_import_api_gepa_or_evaluator() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "import gepa" not in source
    assert "gepa.optimize" not in source
    assert "import openai" not in source
    assert "import litellm" not in source
    assert "evaluate_candidate" not in source
    assert "run_gepa_aime_experiment" not in source
