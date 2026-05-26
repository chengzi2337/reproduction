"""Length-Controlled GEPA runner design 的非执行 manifest 构造器。

本模块只描述未来 runner 应如何组织选择规则和 artifact capture。
它不导入 GEPA、不导入现有执行 runner、不读取 outputs，也不调用任何模型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


DEFAULT_RULE_SEQUENCE = (
    "best_val",
    "tolerance_shortest_0_02",
    "tolerance_shortest_0_05",
    "tolerance_shortest_0_10",
    "soft_length_penalty",
    "lexicographic_ratio_guard_0_95",
    "hard_cap_then_best_val",
)

REQUIRED_CANDIDATE_FIELDS = (
    "candidate_id",
    "parent_candidate_id",
    "mutation_step",
    "candidate_prompt",
    "candidate_prompt_chars",
    "candidate_prompt_words",
    "candidate_prompt_lines",
    "val_score",
    "train_score",
    "reflection_source",
    "selected_by_original_gepa",
    "selected_by_length_control_rule",
    "length_control_rule_name",
    "score_gap_to_best",
    "length_reduction_vs_best",
)

REQUIRED_TRAJECTORY_FIELDS = (
    "run_id",
    "seed",
    "candidate_id",
    "parent_candidate_id",
    "mutation_step",
    "generation_round",
    "selection_round",
    "was_evaluated_on_validation",
    "was_eligible_for_final_selection",
    "rejection_reason",
)

REQUIRED_SUMMARY_FIELDS = (
    "candidate_pool_size",
    "num_candidates_within_0_02",
    "num_candidates_within_0_05",
    "num_shorter_near_best_candidates",
    "best_val_prompt_length",
    "shortest_near_best_prompt_length",
    "original_gepa_selected_candidate_id",
    "length_control_selected_candidate_id",
    "length_control_rule_name",
    "length_control_fallback_used",
    "not_new_experiment",
    "no_model_called_by_audit",
    "no_gepa_optimize_called_by_audit",
)


@dataclass(frozen=True)
class RunnerRuleSpec:
    """描述一个最终选择规则，不包含执行逻辑。"""

    name: str
    selector_function: str
    parameters: dict[str, Any] = field(default_factory=dict)
    fallback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "selector_function": self.selector_function,
            "parameters": dict(self.parameters),
            "fallback": self.fallback,
        }


@dataclass(frozen=True)
class RunnerDesignManifest:
    """未来 length-controlled runner 的设计契约。"""

    design_name: str
    stage: str
    execution_status: str
    integration_mode: str
    rule_specs: tuple[RunnerRuleSpec, ...]
    candidate_fields: tuple[str, ...]
    trajectory_fields: tuple[str, ...]
    summary_fields: tuple[str, ...]
    required_flags: dict[str, bool]
    prohibited_actions: tuple[str, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "design_name": self.design_name,
            "stage": self.stage,
            "execution_status": self.execution_status,
            "integration_mode": self.integration_mode,
            "rule_specs": [rule.to_dict() for rule in self.rule_specs],
            "candidate_fields": list(self.candidate_fields),
            "trajectory_fields": list(self.trajectory_fields),
            "summary_fields": list(self.summary_fields),
            "required_flags": dict(self.required_flags),
            "prohibited_actions": list(self.prohibited_actions),
            "notes": list(self.notes),
        }


def build_default_runner_design_manifest() -> RunnerDesignManifest:
    """构造默认 runner design manifest，供文档和测试复用。"""

    rule_specs = (
        RunnerRuleSpec(
            name="best_val",
            selector_function="select_best_val",
            parameters={},
            fallback=None,
        ),
        RunnerRuleSpec(
            name="tolerance_shortest_0_02",
            selector_function="select_shortest_within_score_gap",
            parameters={"max_gap": 0.02},
            fallback=None,
        ),
        RunnerRuleSpec(
            name="tolerance_shortest_0_05",
            selector_function="select_shortest_within_score_gap",
            parameters={"max_gap": 0.05},
            fallback=None,
        ),
        RunnerRuleSpec(
            name="tolerance_shortest_0_10",
            selector_function="select_shortest_within_score_gap",
            parameters={"max_gap": 0.10},
            fallback=None,
        ),
        RunnerRuleSpec(
            name="soft_length_penalty",
            selector_function="select_with_soft_length_penalty",
            parameters={"lambda_chars": 0.02},
            fallback=None,
        ),
        RunnerRuleSpec(
            name="lexicographic_ratio_guard_0_95",
            selector_function="select_lexicographic",
            parameters={"min_score_fraction": 0.95, "prefer_shorter": True},
            fallback=None,
        ),
        RunnerRuleSpec(
            name="hard_cap_then_best_val",
            selector_function="select_with_hard_cap_then_best_val",
            parameters={"max_chars_multiplier": 3.0, "max_score_gap": 0.05},
            fallback="best_val",
        ),
    )
    manifest = RunnerDesignManifest(
        design_name="aime_length_controlled_gepa_runner_design",
        stage="runner_design_only",
        execution_status="not_executed",
        integration_mode="selection_variant_after_candidate_generation",
        rule_specs=rule_specs,
        candidate_fields=REQUIRED_CANDIDATE_FIELDS,
        trajectory_fields=REQUIRED_TRAJECTORY_FIELDS,
        summary_fields=REQUIRED_SUMMARY_FIELDS,
        required_flags={
            "not_new_experiment": True,
            "runner_design_only": True,
            "no_model_called": True,
            "no_gepa_optimize_called": True,
            "optimizer_core_unchanged": True,
            "evaluator_unchanged": True,
        },
        prohibited_actions=(
            "run_gepa_optimize",
            "call_model_backend",
            "modify_optimizer_core",
            "modify_evaluator",
            "write_existing_official_results",
            "persist_secret_values",
            "persist_local_absolute_paths",
        ),
        notes=(
            "第一版只设计 selection variant，不设计 optimizer variant。",
            "runner 应先保存完整 candidate pool，再离线应用 length-control selection。",
            "hard cap 规则必须有质量阈值和 best_val fallback。",
        ),
    )
    validate_runner_design_manifest(manifest)
    return manifest


def validate_runner_design_manifest(manifest: RunnerDesignManifest) -> None:
    """校验 manifest 是否满足当前阶段的边界条件。"""

    if manifest.execution_status != "not_executed":
        raise ValueError("runner design manifest 必须保持 not_executed。")
    if manifest.stage != "runner_design_only":
        raise ValueError("当前阶段只能是 runner_design_only。")
    if manifest.integration_mode != "selection_variant_after_candidate_generation":
        raise ValueError("第一版必须是候选生成后的 selection variant。")

    _require_flags(manifest.required_flags)
    _require_fields("candidate_fields", manifest.candidate_fields, REQUIRED_CANDIDATE_FIELDS)
    _require_fields("trajectory_fields", manifest.trajectory_fields, REQUIRED_TRAJECTORY_FIELDS)
    _require_fields("summary_fields", manifest.summary_fields, REQUIRED_SUMMARY_FIELDS)
    _require_rule_sequence(manifest.rule_specs)


def _require_flags(flags: Mapping[str, bool]) -> None:
    required_true_flags = (
        "not_new_experiment",
        "runner_design_only",
        "no_model_called",
        "no_gepa_optimize_called",
        "optimizer_core_unchanged",
        "evaluator_unchanged",
    )
    for flag in required_true_flags:
        if flags.get(flag) is not True:
            raise ValueError(f"缺少必需的 true flag：{flag}。")


def _require_fields(name: str, actual: Sequence[str], required: Sequence[str]) -> None:
    missing = [field_name for field_name in required if field_name not in actual]
    if missing:
        raise ValueError(f"{name} 缺少字段：{', '.join(missing)}。")


def _require_rule_sequence(rule_specs: Sequence[RunnerRuleSpec]) -> None:
    names = tuple(rule.name for rule in rule_specs)
    if names != DEFAULT_RULE_SEQUENCE:
        raise ValueError("rule_specs 必须保持预定义顺序，便于跨 seed 对比。")
    for rule in rule_specs:
        if not rule.selector_function:
            raise ValueError(f"规则 {rule.name} 缺少 selector_function。")
    hard_cap = rule_specs[-1]
    if hard_cap.name != "hard_cap_then_best_val" or hard_cap.fallback != "best_val":
        raise ValueError("hard_cap_then_best_val 必须显式 fallback 到 best_val。")
