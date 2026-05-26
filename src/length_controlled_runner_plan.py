"""Length-Controlled GEPA runner implementation plan 的非执行计划模型。

本模块只表达未来实现步骤、准入条件和停机条件，不读取 artifacts、
不调用模型、不调用 GEPA，也不导入现有执行 runner。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


IMPLEMENTATION_PHASE_SEQUENCE = (
    "inspect_gepa_result_capabilities",
    "define_candidate_extraction_adapter",
    "define_artifact_writer",
    "define_offline_selection_comparison",
    "define_report_summary_writer",
    "define_dry_run_validation",
)

REQUIRED_ENTRY_CONDITIONS = (
    "runner_design_manifest_exists",
    "selection_rules_are_pure_functions",
    "artifact_capture_contract_exists",
    "no_optimizer_core_change_required",
    "no_evaluator_change_required",
    "user_has_not_approved_new_experiment",
)

REQUIRED_STOP_CONDITIONS = (
    "candidate_pool_unavailable",
    "candidate_score_alignment_unverifiable",
    "selected_candidate_not_in_pool",
    "optimizer_core_change_required",
    "model_call_required_for_plan",
    "secret_or_absolute_path_would_be_persisted",
)

PLANNED_IMPLEMENTATION_FILES = (
    "src/length_controlled_runner_artifacts.py",
    "src/length_controlled_runner_comparison.py",
    "scripts/plan_aime_length_controlled_runner.py",
    "tests/test_length_controlled_runner_artifacts.py",
    "tests/test_length_controlled_runner_comparison.py",
)


@dataclass(frozen=True)
class ImplementationPhase:
    """描述一个未来实现阶段，不表示该阶段已经执行。"""

    name: str
    purpose: str
    deliverable: str
    validation: str
    may_execute_gepa: bool = False
    may_call_model: bool = False
    may_modify_optimizer: bool = False
    may_modify_evaluator: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "purpose": self.purpose,
            "deliverable": self.deliverable,
            "validation": self.validation,
            "may_execute_gepa": self.may_execute_gepa,
            "may_call_model": self.may_call_model,
            "may_modify_optimizer": self.may_modify_optimizer,
            "may_modify_evaluator": self.may_modify_evaluator,
        }


@dataclass(frozen=True)
class RunnerImplementationPlan:
    """未来 runner implementation 的计划契约。"""

    plan_name: str
    status: str
    implementation_mode: str
    phases: tuple[ImplementationPhase, ...]
    entry_conditions: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    planned_files: tuple[str, ...]
    required_flags: dict[str, bool]
    decision_rule: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_name": self.plan_name,
            "status": self.status,
            "implementation_mode": self.implementation_mode,
            "phases": [phase.to_dict() for phase in self.phases],
            "entry_conditions": list(self.entry_conditions),
            "stop_conditions": list(self.stop_conditions),
            "planned_files": list(self.planned_files),
            "required_flags": dict(self.required_flags),
            "decision_rule": self.decision_rule,
        }


def build_default_runner_implementation_plan() -> RunnerImplementationPlan:
    """构造默认 implementation plan，供文档和测试复用。"""

    phases = (
        ImplementationPhase(
            name="inspect_gepa_result_capabilities",
            purpose="确认 GEPA result 是否暴露完整候选、分数和轨迹字段。",
            deliverable="只读 capability matrix；若字段不足则输出 artifact limitation。",
            validation="使用 fake result 覆盖字段存在、字段缺失和字段不一致场景。",
        ),
        ImplementationPhase(
            name="define_candidate_extraction_adapter",
            purpose="把 GEPA result 转换为统一 candidate pool 结构。",
            deliverable="纯函数 adapter 设计，不调用 GEPA，不读取 outputs。",
            validation="使用 fake result 校验 candidate_id、prompt、score 和 parent 字段映射。",
        ),
        ImplementationPhase(
            name="define_artifact_writer",
            purpose="定义 candidate_pool、trajectory_summary 和 manifest 的写入边界。",
            deliverable="artifact writer 契约和 JSON schema 风格校验。",
            validation="使用临时目录写入 fake artifacts，并检查不包含 secret 或绝对路径。",
        ),
        ImplementationPhase(
            name="define_offline_selection_comparison",
            purpose="在同一 candidate pool 上离线应用 best_val 与 length-control rules。",
            deliverable="selection comparison 纯函数，复用 length_controlled_selection。",
            validation="使用 fake candidates 覆盖 fallback、near-best 和 hard cap 场景。",
        ),
        ImplementationPhase(
            name="define_report_summary_writer",
            purpose="生成只描述 validation tradeoff 的 summary，不写 performance claim。",
            deliverable="summary writer 契约和报告字段清单。",
            validation="检查 not_new_experiment、not_performance_claim 和 no_gepa flags。",
        ),
        ImplementationPhase(
            name="define_dry_run_validation",
            purpose="定义不调用模型的 dry-run 验证命令和停止条件。",
            deliverable="dry-run checklist；通过后才允许请求真实实验批准。",
            validation="compileall、pytest 和静态禁用调用扫描。",
        ),
    )
    plan = RunnerImplementationPlan(
        plan_name="aime_length_controlled_runner_implementation_plan",
        status="plan_only",
        implementation_mode="selection_variant_artifact_wiring",
        phases=phases,
        entry_conditions=REQUIRED_ENTRY_CONDITIONS,
        stop_conditions=REQUIRED_STOP_CONDITIONS,
        planned_files=PLANNED_IMPLEMENTATION_FILES,
        required_flags={
            "not_new_experiment": True,
            "plan_only": True,
            "no_model_called": True,
            "no_gepa_optimize_called": True,
            "optimizer_core_unchanged": True,
            "evaluator_unchanged": True,
            "outputs_not_modified": True,
        },
        decision_rule=(
            "若 GEPA result 无法提供可校验 candidate pool 和 score alignment，"
            "下一步必须写 artifact limitation，而不是运行 Length-Controlled GEPA。"
        ),
    )
    validate_runner_implementation_plan(plan)
    return plan


def validate_runner_implementation_plan(plan: RunnerImplementationPlan) -> None:
    """校验计划是否仍处于非执行 implementation planning 阶段。"""

    if plan.status != "plan_only":
        raise ValueError("runner implementation plan 必须保持 plan_only。")
    if plan.implementation_mode != "selection_variant_artifact_wiring":
        raise ValueError("第一版实现计划必须限定为 selection_variant_artifact_wiring。")
    _require_phase_sequence(plan.phases)
    _require_values("entry_conditions", plan.entry_conditions, REQUIRED_ENTRY_CONDITIONS)
    _require_values("stop_conditions", plan.stop_conditions, REQUIRED_STOP_CONDITIONS)
    _require_values("planned_files", plan.planned_files, PLANNED_IMPLEMENTATION_FILES)
    _require_flags(plan.required_flags)
    _reject_executable_phase(plan.phases)


def _require_phase_sequence(phases: Sequence[ImplementationPhase]) -> None:
    names = tuple(phase.name for phase in phases)
    if names != IMPLEMENTATION_PHASE_SEQUENCE:
        raise ValueError("implementation phases 必须保持预定义顺序。")


def _require_values(name: str, actual: Sequence[str], required: Sequence[str]) -> None:
    missing = [value for value in required if value not in actual]
    if missing:
        raise ValueError(f"{name} 缺少必需项：{', '.join(missing)}。")


def _require_flags(flags: Mapping[str, bool]) -> None:
    required_true_flags = (
        "not_new_experiment",
        "plan_only",
        "no_model_called",
        "no_gepa_optimize_called",
        "optimizer_core_unchanged",
        "evaluator_unchanged",
        "outputs_not_modified",
    )
    for flag in required_true_flags:
        if flags.get(flag) is not True:
            raise ValueError(f"缺少必需的 true flag：{flag}。")


def _reject_executable_phase(phases: Sequence[ImplementationPhase]) -> None:
    for phase in phases:
        if phase.may_execute_gepa:
            raise ValueError(f"阶段 {phase.name} 不允许执行 GEPA。")
        if phase.may_call_model:
            raise ValueError(f"阶段 {phase.name} 不允许调用模型。")
        if phase.may_modify_optimizer:
            raise ValueError(f"阶段 {phase.name} 不允许修改 optimizer。")
        if phase.may_modify_evaluator:
            raise ValueError(f"阶段 {phase.name} 不允许修改 evaluator。")
