from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "audit_aime_official_budget_answer_extractability.py"

SPEC = importlib.util.spec_from_file_location("answer_extractability_audit_script", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
audit_script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit_script
SPEC.loader.exec_module(audit_script)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            json.dump(row, handle, ensure_ascii=False)
            handle.write("\n")


def _record(sample_id: str, prompt_version: str, prediction: str, gold: str, score: float) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "prompt_version": prompt_version,
        "question": f"question {sample_id}",
        "prediction": prediction,
        "gold": gold,
        "score": score,
        "error": None,
        "attempt_count": 1,
    }


def test_extract_prediction_answer_supports_protocol_and_boxed() -> None:
    assert audit_script.extract_prediction_answer("work\n### 70").value == "70"
    assert audit_script.extract_prediction_answer("work\n\\boxed{70}").value == "70"
    assert audit_script.extract_prediction_answer("Final answer: 588").value == "588"
    assert audit_script.extract_prediction_answer("").method == "empty"


def test_classify_record_detects_format_loss() -> None:
    record = _record("x", "seed", "solution \\boxed{70}", "### 70", 0.0)

    classified = audit_script.classify_record(record, Path("fake.jsonl"))

    assert classified["category"] == "format_loss"
    assert classified["extracted_answer"] == "70"
    assert classified["relaxed_extractable_correct"] is True


def test_classify_record_detects_reasoning_error_and_empty() -> None:
    wrong = _record("wrong", "seed", "### 71", "### 70", 0.0)
    empty = _record("empty", "optimized", "", "### 70", 0.0)

    assert audit_script.classify_record(wrong, Path("fake.jsonl"))["category"] == "reasoning_error"
    assert audit_script.classify_record(empty, Path("fake.jsonl"))["category"] == "empty_or_invalid"


def test_audit_run_summarizes_prompt_versions(tmp_path: Path) -> None:
    run_dir_text = "outputs/run0/ts"
    _write_jsonl(
        tmp_path / run_dir_text / "per_example_eval.jsonl",
        [
            _record("a", "seed", "### 1", "### 1", 1.0),
            _record("b", "seed", "\\boxed{2}", "### 2", 0.0),
            _record("c", "seed", "### 4", "### 3", 0.0),
            _record("d", "optimized", "### 1", "### 1", 1.0),
            _record("e", "optimized", "", "### 2", 0.0),
        ],
    )

    run = audit_script.audit_run(tmp_path, 0, run_dir_text)

    seed = run["by_prompt_version"]["seed"]
    optimized = run["by_prompt_version"]["optimized"]
    assert seed["official_correct_count"] == 1
    assert seed["format_loss_count"] == 1
    assert seed["reasoning_error_count"] == 1
    assert seed["relaxed_extractable_score"] == pytest.approx(2 / 3)
    assert optimized["empty_or_invalid_count"] == 1


def test_audit_run_normalizes_duplicate_prompt_sample_records(tmp_path: Path) -> None:
    run_dir_text = "outputs/run0/ts"
    _write_jsonl(
        tmp_path / run_dir_text / "per_example_eval.jsonl",
        [
            _record("a", "seed", "\\boxed{1}", "### 1", 0.0),
            _record("a", "seed", "### 1", "### 1", 1.0),
            _record("a", "optimized", "\\boxed{1}", "### 1", 0.0),
            _record("a", "optimized", "### 1", "### 1", 1.0),
        ],
    )

    run = audit_script.audit_run(tmp_path, 0, run_dir_text)

    assert run["by_prompt_version"]["seed"]["num_examples"] == 1
    assert run["by_prompt_version"]["seed"]["official_correct_count"] == 1
    assert run["by_prompt_version"]["optimized"]["num_examples"] == 1
    assert run["by_prompt_version"]["optimized"]["official_correct_count"] == 1


def test_build_payload_and_report_include_required_flags(tmp_path: Path, monkeypatch) -> None:
    run_dir_text = "outputs/run0/ts"
    _write_jsonl(
        tmp_path / run_dir_text / "per_example_eval.jsonl",
        [
            _record("a", "seed", "\\boxed{1}", "### 1", 0.0),
            _record("b", "optimized", "### 1", "### 1", 1.0),
        ],
    )
    monkeypatch.setattr(audit_script, "create_timestamp", lambda: "20260526T120000+0800")

    payload = audit_script.build_audit_payload(tmp_path, ((0, run_dir_text),))
    report = audit_script.render_report(payload)

    assert payload["metadata"]["not_new_experiment"] is True
    assert payload["metadata"]["diagnostic_only"] is True
    assert payload["metadata"]["relaxed_score_not_official"] is True
    assert payload["metadata"]["official_score_not_replaced"] is True
    assert payload["metadata"]["no_model_called"] is True
    assert payload["metadata"]["no_gepa_optimize_called"] is True
    assert "`relaxed_score_not_official = true`" in report
    assert "不能写：relaxed score 可以替代 official score" in report


def test_main_writes_json_and_report_without_api_or_gepa_calls(tmp_path: Path, monkeypatch) -> None:
    run_dir_text = "outputs/run0/ts"
    _write_jsonl(
        tmp_path / run_dir_text / "per_example_eval.jsonl",
        [
            _record("a", "seed", "\\boxed{1}", "### 1", 0.0),
            _record("b", "optimized", "### 1", "### 1", 1.0),
        ],
    )
    monkeypatch.setattr(audit_script, "DEFAULT_RUNS", ((0, run_dir_text),))
    monkeypatch.setattr(audit_script, "create_timestamp", lambda: "20260526T120500+0800")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_aime_official_budget_answer_extractability.py",
            "--project-root",
            str(tmp_path),
        ],
    )

    audit_script.main()

    audit_json = (
        tmp_path
        / "outputs"
        / "aime_official_budget_answer_extractability_audit"
        / "20260526T120500+0800"
        / "answer_extractability_audit.json"
    )
    report_path = tmp_path / "reports" / "aime_official_budget_answer_extractability_audit_result.md"
    payload = json.loads(audit_json.read_text(encoding="utf-8"))
    report = report_path.read_text(encoding="utf-8")

    assert payload["metadata"]["no_api_called"] is True
    assert payload["metadata"]["no_model_called"] is True
    assert payload["metadata"]["no_gepa_optimize_called"] is True
    assert "本报告不调用模型、不调用 API、不调用 GEPA、不运行新实验" in report


def test_missing_artifact_fails_explicitly(tmp_path: Path) -> None:
    (tmp_path / "outputs/missing/ts").mkdir(parents=True)
    with pytest.raises(audit_script.AuditError, match="缺少必需 artifact"):
        audit_script.audit_run(tmp_path, 0, "outputs/missing/ts")


def test_script_source_does_not_import_api_gepa_or_evaluator() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "import gepa" not in source
    assert "gepa.optimize" not in source
    assert "import openai" not in source
    assert "import litellm" not in source
    assert "evaluate_candidate" not in source
    assert "run_gepa_aime_experiment" not in source
