import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.length_controlled_runner_plan import (
    IMPLEMENTATION_PHASE_SEQUENCE,
    PLANNED_IMPLEMENTATION_FILES,
    REQUIRED_ENTRY_CONDITIONS,
    REQUIRED_STOP_CONDITIONS,
    ImplementationPhase,
    RunnerImplementationPlan,
    build_default_runner_implementation_plan,
    validate_runner_implementation_plan,
)


def test_default_plan_keeps_non_execution_boundaries():
    plan = build_default_runner_implementation_plan()
    payload = plan.to_dict()

    assert payload["status"] == "plan_only"
    assert payload["implementation_mode"] == "selection_variant_artifact_wiring"
    assert payload["required_flags"]["not_new_experiment"] is True
    assert payload["required_flags"]["no_model_called"] is True
    assert payload["required_flags"]["no_gepa_optimize_called"] is True
    assert payload["required_flags"]["outputs_not_modified"] is True


def test_default_plan_phase_sequence_is_stable():
    plan = build_default_runner_implementation_plan()

    assert tuple(phase.name for phase in plan.phases) == IMPLEMENTATION_PHASE_SEQUENCE
    assert plan.phases[0].name == "inspect_gepa_result_capabilities"
    assert plan.phases[-1].name == "define_dry_run_validation"


def test_default_plan_contains_required_conditions_and_future_files():
    plan = build_default_runner_implementation_plan()

    for condition in REQUIRED_ENTRY_CONDITIONS:
        assert condition in plan.entry_conditions
    for condition in REQUIRED_STOP_CONDITIONS:
        assert condition in plan.stop_conditions
    for planned_file in PLANNED_IMPLEMENTATION_FILES:
        assert planned_file in plan.planned_files


def test_validation_rejects_executed_status():
    plan = build_default_runner_implementation_plan()
    changed = RunnerImplementationPlan(
        plan_name=plan.plan_name,
        status="executed",
        implementation_mode=plan.implementation_mode,
        phases=plan.phases,
        entry_conditions=plan.entry_conditions,
        stop_conditions=plan.stop_conditions,
        planned_files=plan.planned_files,
        required_flags=plan.required_flags,
        decision_rule=plan.decision_rule,
    )

    with pytest.raises(ValueError, match="plan_only"):
        validate_runner_implementation_plan(changed)


def test_validation_rejects_phase_that_may_call_model():
    plan = build_default_runner_implementation_plan()
    changed_phases = (
        ImplementationPhase(
            name="inspect_gepa_result_capabilities",
            purpose="bad",
            deliverable="bad",
            validation="bad",
            may_call_model=True,
        ),
    ) + plan.phases[1:]
    changed = RunnerImplementationPlan(
        plan_name=plan.plan_name,
        status=plan.status,
        implementation_mode=plan.implementation_mode,
        phases=changed_phases,
        entry_conditions=plan.entry_conditions,
        stop_conditions=plan.stop_conditions,
        planned_files=plan.planned_files,
        required_flags=plan.required_flags,
        decision_rule=plan.decision_rule,
    )

    with pytest.raises(ValueError, match="不允许调用模型"):
        validate_runner_implementation_plan(changed)


def test_validation_rejects_missing_stop_condition():
    plan = build_default_runner_implementation_plan()
    changed = RunnerImplementationPlan(
        plan_name=plan.plan_name,
        status=plan.status,
        implementation_mode=plan.implementation_mode,
        phases=plan.phases,
        entry_conditions=plan.entry_conditions,
        stop_conditions=plan.stop_conditions[:-1],
        planned_files=plan.planned_files,
        required_flags=plan.required_flags,
        decision_rule=plan.decision_rule,
    )

    with pytest.raises(ValueError, match="stop_conditions"):
        validate_runner_implementation_plan(changed)


def test_module_does_not_import_or_call_execution_paths():
    source = Path("src/length_controlled_runner_plan.py").read_text(encoding="utf-8")

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
