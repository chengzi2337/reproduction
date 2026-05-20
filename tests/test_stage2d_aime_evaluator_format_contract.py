from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


SPEC = importlib.util.spec_from_file_location(
    "stage2d_aime_evaluator_format_contract_script",
    PROJECT_ROOT / "scripts" / "stage2d_audit_aime_evaluator_format_contract.py",
)
assert SPEC is not None and SPEC.loader is not None
stage2d_contract_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage2d_contract_script)


def test_strict_vs_placeholder_distinction() -> None:
    assert stage2d_contract_script.strict_regex_match_hash_integer("### 72") is True
    assert stage2d_contract_script.strict_regex_match_hash_integer("### <answer>\n72\n</answer>") is False
    assert stage2d_contract_script.relaxed_extract_answer("### <answer>\n72\n</answer>") == "72"


def test_failure_mode_classification() -> None:
    assert (
        stage2d_contract_script.classify_failure_mode("### <answer>\n72\n</answer>", 0.0)
        == "xml_tag_placeholder_misuse"
    )
    assert (
        stage2d_contract_script.classify_failure_mode("### Step 1\nFinal answer: 72", 0.0)
        == "markdown_heading_misuse"
    )


def test_contract_audit_output_contains_expected_fields(tmp_path) -> None:
    run_dir, payload = stage2d_contract_script.run_contract_audit(tmp_path)
    output_text = (run_dir / "stage2d_aime_evaluator_contract_audit.json").read_text(encoding="utf-8")
    output = json.loads(output_text)

    assert output["path_type"] == "stage2d_aime_evaluator_format_contract_audit"
    assert output["not_performance_claim"] is True
    assert output["no_gepa_optimize_called"] is True
    assert "MIMO_API_KEY" not in output_text

    cases = {case["case_name"]: case for case in output["cases"]}
    assert cases["exact_contract"]["official_metric_score"] == 1.0
    assert cases["xml_placeholder_multiline"]["official_metric_score"] == 0.0
    assert cases["xml_placeholder_multiline"]["normalized_score"] == 1.0


def test_no_model_invocation_side_effects() -> None:
    run_dir, payload = stage2d_contract_script.run_contract_audit(
        Path(PROJECT_ROOT / "outputs" / "tmp_stage2d_contract_test")
    )
    assert run_dir.exists()
    assert payload["not_gepa_path"] is True
