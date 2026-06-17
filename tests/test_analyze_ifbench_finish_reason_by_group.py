from __future__ import annotations

import importlib.util
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "analyze_ifbench_finish_reason_by_group.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "analyze_ifbench_finish_reason_by_group",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_analyze_aggregate_keeps_length_group_details(tmp_path: Path) -> None:
    module = load_module()
    aggregate_path = tmp_path / "IFBench_IFBenchCoT2StageProgram_GEPA_qwen3-8b-nocache-p2-t0-optimized-aggregate.json"
    aggregate_path.write_text(
        json.dumps(
            {
                "replay_tag": "nocache-p2-t0",
                "temperature": 0.0,
                "top_p": 0.95,
                "repetitions": 2,
                "replay_kind": "optimized",
                "provider_rejection_events": 1,
                "finish_reason_capture_status": "captured",
                "sample_level_score_matrix": [
                    {
                        "idx_in_split": 1,
                        "example_key": "a",
                        "instruction_group": "count",
                        "scores": {"rep1": 1, "rep2": 0},
                        "parse_failures": {"rep1": False, "rep2": True},
                        "finish_reasons": {"rep1": ["stop"], "rep2": ["length"]},
                    },
                    {
                        "idx_in_split": 2,
                        "example_key": "b",
                        "instruction_group": "format",
                        "scores": {"rep1": 1, "rep2": 1},
                        "parse_failures": {"rep1": False, "rep2": False},
                        "finish_reasons": {"rep1": ["stop"], "rep2": ["custom"]},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = module.analyze_aggregate(aggregate_path)

    assert result["status"] == "ok"
    assert result["variant"] == "p2"
    assert result["total_stop"] == 2
    assert result["total_length"] == 1
    assert result["total_other_finish_reason"] == 1
    assert result["provider_rejection_events"] == 1
    assert result["parse_failure_count"] == 1
    assert result["groups"]["count"]["length_sample_ids"] == ["a"]
    assert result["groups"]["count"]["length_sample_average_score"] == 0.5


def test_empty_file_is_reported_not_skipped(tmp_path: Path) -> None:
    module = load_module()
    aggregate_path = tmp_path / "empty-aggregate.json"
    aggregate_path.write_text("", encoding="utf-8")

    result = module.analyze_aggregate(aggregate_path)

    assert result["status"] == "empty_or_unreadable"
    assert result["aggregate"] == "empty-aggregate.json"


def test_build_report_and_markdown_include_p2_audit(tmp_path: Path) -> None:
    module = load_module()
    aggregate_path = tmp_path / "IFBench_IFBenchCoT2StageProgram_GEPA_qwen3-8b-nocache-p2-t0-optimized-aggregate.json"
    aggregate_path.write_text(
        json.dumps(
            {
                "replay_tag": "nocache-p2-t0",
                "temperature": 0.0,
                "top_p": 0.95,
                "repetitions": 1,
                "replay_kind": "optimized",
                "finish_reason_capture_status": "captured",
                "sample_level_score_matrix": [
                    {
                        "idx_in_split": 1,
                        "instruction_group": "count",
                        "scores": {"rep1": 0},
                        "parse_failures": {"rep1": False},
                        "finish_reasons": {"rep1": ["length"]},
                    },
                    {
                        "idx_in_split": 2,
                        "instruction_group": "format",
                        "scores": {"rep1": 1},
                        "parse_failures": {"rep1": False},
                        "finish_reasons": {"rep1": ["stop"]},
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.md"

    report = module.build_report(tmp_path)
    module.write_markdown(report, output)

    assert report["p2_length_event_audit"]["length_sample_average_score"] == 0.0
    assert report["p2_length_event_audit"]["non_length_sample_average_score"] == 1.0
    text = output.read_text(encoding="utf-8")
    assert "## P2 length event audit" in text
    assert "| aggregate | variant | temperature | repetitions | stop | length | provider rejects | parse failures | length groups |" in text
