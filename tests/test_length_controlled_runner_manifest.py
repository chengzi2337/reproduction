import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.length_controlled_runner_manifest import (
    REQUIRED_CANDIDATE_FIELDS,
    REQUIRED_SUMMARY_FIELDS,
    REQUIRED_TRAJECTORY_FIELDS,
    RunnerDesignManifest,
    RunnerRuleSpec,
    build_default_runner_design_manifest,
    validate_runner_design_manifest,
)


def test_default_manifest_keeps_runner_design_only_boundaries():
    manifest = build_default_runner_design_manifest()
    payload = manifest.to_dict()

    assert payload["stage"] == "runner_design_only"
    assert payload["execution_status"] == "not_executed"
    assert payload["integration_mode"] == "selection_variant_after_candidate_generation"
    assert payload["required_flags"]["not_new_experiment"] is True
    assert payload["required_flags"]["no_model_called"] is True
    assert payload["required_flags"]["no_gepa_optimize_called"] is True
    assert payload["required_flags"]["optimizer_core_unchanged"] is True
    assert payload["required_flags"]["evaluator_unchanged"] is True


def test_default_manifest_contains_required_artifact_fields():
    manifest = build_default_runner_design_manifest()

    for field_name in REQUIRED_CANDIDATE_FIELDS:
        assert field_name in manifest.candidate_fields
    for field_name in REQUIRED_TRAJECTORY_FIELDS:
        assert field_name in manifest.trajectory_fields
    for field_name in REQUIRED_SUMMARY_FIELDS:
        assert field_name in manifest.summary_fields


def test_default_manifest_rule_order_is_stable():
    manifest = build_default_runner_design_manifest()

    assert [rule.name for rule in manifest.rule_specs] == [
        "best_val",
        "tolerance_shortest_0_02",
        "tolerance_shortest_0_05",
        "tolerance_shortest_0_10",
        "soft_length_penalty",
        "lexicographic_ratio_guard_0_95",
        "hard_cap_then_best_val",
    ]
    assert manifest.rule_specs[-1].fallback == "best_val"


def test_validation_rejects_executed_manifest():
    manifest = build_default_runner_design_manifest()
    changed = RunnerDesignManifest(
        design_name=manifest.design_name,
        stage=manifest.stage,
        execution_status="executed",
        integration_mode=manifest.integration_mode,
        rule_specs=manifest.rule_specs,
        candidate_fields=manifest.candidate_fields,
        trajectory_fields=manifest.trajectory_fields,
        summary_fields=manifest.summary_fields,
        required_flags=manifest.required_flags,
        prohibited_actions=manifest.prohibited_actions,
        notes=manifest.notes,
    )

    with pytest.raises(ValueError, match="not_executed"):
        validate_runner_design_manifest(changed)


def test_validation_rejects_missing_required_flag():
    manifest = build_default_runner_design_manifest()
    flags = dict(manifest.required_flags)
    flags["no_model_called"] = False
    changed = RunnerDesignManifest(
        design_name=manifest.design_name,
        stage=manifest.stage,
        execution_status=manifest.execution_status,
        integration_mode=manifest.integration_mode,
        rule_specs=manifest.rule_specs,
        candidate_fields=manifest.candidate_fields,
        trajectory_fields=manifest.trajectory_fields,
        summary_fields=manifest.summary_fields,
        required_flags=flags,
        prohibited_actions=manifest.prohibited_actions,
        notes=manifest.notes,
    )

    with pytest.raises(ValueError, match="no_model_called"):
        validate_runner_design_manifest(changed)


def test_validation_rejects_hard_cap_without_best_val_fallback():
    manifest = build_default_runner_design_manifest()
    changed_rules = tuple(manifest.rule_specs[:-1]) + (
        RunnerRuleSpec(
            name="hard_cap_then_best_val",
            selector_function="select_with_hard_cap_then_best_val",
            parameters={"max_chars_multiplier": 3.0, "max_score_gap": 0.05},
            fallback=None,
        ),
    )
    changed = RunnerDesignManifest(
        design_name=manifest.design_name,
        stage=manifest.stage,
        execution_status=manifest.execution_status,
        integration_mode=manifest.integration_mode,
        rule_specs=changed_rules,
        candidate_fields=manifest.candidate_fields,
        trajectory_fields=manifest.trajectory_fields,
        summary_fields=manifest.summary_fields,
        required_flags=manifest.required_flags,
        prohibited_actions=manifest.prohibited_actions,
        notes=manifest.notes,
    )

    with pytest.raises(ValueError, match="fallback"):
        validate_runner_design_manifest(changed)


def test_module_does_not_import_or_call_execution_paths():
    source = Path("src/length_controlled_runner_manifest.py").read_text(encoding="utf-8")

    forbidden_snippets = [
        "import gepa",
        "gepa.optimize",
        "import openai",
        "import litellm",
        "requests.post",
        "httpx.",
        "urllib.request",
        "run_gepa_aime_experiment",
        "load_experiment_config",
        "outputs/",
    ]
    for snippet in forbidden_snippets:
        assert snippet not in source
