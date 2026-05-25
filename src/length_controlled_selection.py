"""AIME 长度控制候选选择的纯函数规则。

本模块只处理已经存在的候选 prompt 元数据，不读取实验输出、不调用模型、
不调用 GEPA，也不修改任何 runner。它用于在后续设计 Length-Controlled
GEPA 前，先把候选选择规则固定为可测试、可审计的独立逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


Candidate = dict[str, Any]


@dataclass(frozen=True)
class SelectionResult:
    """记录选择结果和可审计理由。"""

    rule_name: str
    selected_candidate: Candidate
    best_candidate: Candidate
    reason: str
    parameters: dict[str, Any]
    fallback_used: bool
    eligible_count: int
    score_gap_to_best: float
    chars_saved_vs_best: int
    length_reduction_vs_best: float

    def to_dict(self) -> dict[str, Any]:
        """返回适合写入 JSON artifact 的普通字典。"""

        return {
            "rule_name": self.rule_name,
            "selected_candidate": dict(self.selected_candidate),
            "best_candidate": dict(self.best_candidate),
            "reason": self.reason,
            "parameters": dict(self.parameters),
            "fallback_used": self.fallback_used,
            "eligible_count": self.eligible_count,
            "score_gap_to_best": self.score_gap_to_best,
            "chars_saved_vs_best": self.chars_saved_vs_best,
            "length_reduction_vs_best": self.length_reduction_vs_best,
        }


def select_best_val(candidates: Sequence[Mapping[str, Any]]) -> SelectionResult:
    """Rule 0：选择 validation score 最高的候选。"""

    normalized = _normalize_candidates(candidates)
    best = _best_candidate(normalized)
    return _build_result(
        rule_name="best_val",
        selected=best,
        best=best,
        reason="选择 validation score 最高的候选；分数相同时选择更短 prompt。",
        parameters={},
        fallback_used=False,
        eligible_count=len(normalized),
    )


def select_shortest_within_score_gap(
    candidates: Sequence[Mapping[str, Any]], max_gap: float
) -> SelectionResult:
    """Rule 1：在最佳分数容忍区间内选择最短候选。"""

    if max_gap < 0:
        raise ValueError("max_gap 必须大于或等于 0。")

    normalized = _normalize_candidates(candidates)
    best = _best_candidate(normalized)
    best_score = float(best["val_score"])
    eligible = [
        candidate
        for candidate in normalized
        if best_score - float(candidate["val_score"]) <= max_gap
    ]
    selected = min(
        eligible,
        key=lambda candidate: (
            int(candidate["prompt_chars"]),
            -float(candidate["val_score"]),
            _candidate_sort_id(candidate),
        ),
    )
    return _build_result(
        rule_name="tolerance_shortest",
        selected=selected,
        best=best,
        reason="在 validation score 距离最佳值不超过阈值的候选中选择最短 prompt。",
        parameters={"max_gap": max_gap},
        fallback_used=False,
        eligible_count=len(eligible),
    )


def select_with_soft_length_penalty(
    candidates: Sequence[Mapping[str, Any]], lambda_chars: float
) -> SelectionResult:
    """Rule 2：对归一化长度施加软惩罚后选择调整分最高的候选。"""

    if lambda_chars < 0:
        raise ValueError("lambda_chars 必须大于或等于 0。")

    normalized = _normalize_candidates(candidates)
    best = _best_candidate(normalized)
    max_chars = max(int(candidate["prompt_chars"]) for candidate in normalized)
    scored_candidates: list[tuple[float, Candidate]] = []
    for candidate in normalized:
        normalized_length = int(candidate["prompt_chars"]) / max_chars
        adjusted_score = float(candidate["val_score"]) - lambda_chars * normalized_length
        enriched = dict(candidate)
        enriched["normalized_length"] = normalized_length
        enriched["adjusted_score"] = adjusted_score
        scored_candidates.append((adjusted_score, enriched))

    selected = max(
        scored_candidates,
        key=lambda item: (
            item[0],
            float(item[1]["val_score"]),
            -int(item[1]["prompt_chars"]),
            _candidate_sort_id(item[1]),
        ),
    )[1]
    return _build_result(
        rule_name="soft_length_penalty",
        selected=selected,
        best=best,
        reason="选择 validation score 减去归一化长度惩罚后的 adjusted_score 最高候选。",
        parameters={"lambda_chars": lambda_chars, "max_prompt_chars": max_chars},
        fallback_used=False,
        eligible_count=len(normalized),
    )


def select_with_hard_cap_then_best_val(
    candidates: Sequence[Mapping[str, Any]], max_chars: int, max_score_gap: float = 0.05
) -> SelectionResult:
    """Rule 4：长度上限内仅接受 near-best 候选，否则回退原最佳候选。"""

    if max_chars <= 0:
        raise ValueError("max_chars 必须大于 0。")
    if max_score_gap < 0:
        raise ValueError("max_score_gap 必须大于或等于 0。")

    normalized = _normalize_candidates(candidates)
    best = _best_candidate(normalized)
    best_score = float(best["val_score"])
    eligible = [
        candidate
        for candidate in normalized
        if int(candidate["prompt_chars"]) <= max_chars
        and best_score - float(candidate["val_score"]) <= max_score_gap
    ]

    fallback_used = not eligible
    selected = (
        best
        if fallback_used
        else max(
            eligible,
            key=lambda candidate: (
                float(candidate["val_score"]),
                -int(candidate["prompt_chars"]),
                _candidate_sort_id(candidate),
            ),
        )
    )
    reason = (
        "长度上限内没有分数接近最佳值的候选，回退到原始 best_val 候选。"
        if fallback_used
        else "在长度上限内选择 validation score 最高且接近最佳值的候选。"
    )
    return _build_result(
        rule_name="hard_cap_then_best_val",
        selected=selected,
        best=best,
        reason=reason,
        parameters={"max_chars": max_chars, "max_score_gap": max_score_gap},
        fallback_used=fallback_used,
        eligible_count=len(eligible),
    )


def select_lexicographic(
    candidates: Sequence[Mapping[str, Any]],
    min_score_fraction: float,
    prefer_shorter: bool = True,
) -> SelectionResult:
    """Rule 3：先设置分数比例 guard，再按长度或分数做词典序选择。"""

    if min_score_fraction <= 0 or min_score_fraction > 1:
        raise ValueError("min_score_fraction 必须位于 (0, 1]。")

    normalized = _normalize_candidates(candidates)
    best = _best_candidate(normalized)
    threshold = float(best["val_score"]) * min_score_fraction
    eligible = [
        candidate
        for candidate in normalized
        if float(candidate["val_score"]) >= threshold
    ]
    if prefer_shorter:
        selected = min(
            eligible,
            key=lambda candidate: (
                int(candidate["prompt_chars"]),
                -float(candidate["val_score"]),
                _candidate_sort_id(candidate),
            ),
        )
        reason = "在达到最佳分数比例 guard 的候选中优先选择最短 prompt。"
    else:
        selected = max(
            eligible,
            key=lambda candidate: (
                float(candidate["val_score"]),
                -int(candidate["prompt_chars"]),
                _candidate_sort_id(candidate),
            ),
        )
        reason = "在达到最佳分数比例 guard 的候选中优先选择最高 validation score。"

    return _build_result(
        rule_name="lexicographic_ratio_guard",
        selected=selected,
        best=best,
        reason=reason,
        parameters={
            "min_score_fraction": min_score_fraction,
            "prefer_shorter": prefer_shorter,
            "score_threshold": threshold,
        },
        fallback_used=False,
        eligible_count=len(eligible),
    )


def _normalize_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[Candidate]:
    if not candidates:
        raise ValueError("candidates 不能为空。")

    normalized: list[Candidate] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            raise ValueError(f"候选 {index} 必须是 mapping。")
        copied = dict(candidate)
        for field in ("candidate_id", "val_score", "prompt_text"):
            if field not in copied:
                raise ValueError(f"候选 {index} 缺少必需字段：{field}。")

        prompt_chars = copied.get("prompt_chars")
        if prompt_chars is None:
            prompt_chars = len(str(copied["prompt_text"]))
        if isinstance(prompt_chars, bool) or not isinstance(prompt_chars, int):
            raise ValueError(f"候选 {index} 的 prompt_chars 必须是整数。")
        if prompt_chars <= 0:
            raise ValueError(f"候选 {index} 的 prompt_chars 必须大于 0。")

        val_score = copied["val_score"]
        if isinstance(val_score, bool) or not isinstance(val_score, (int, float)):
            raise ValueError(f"候选 {index} 的 val_score 必须是数字。")

        copied["prompt_chars"] = prompt_chars
        copied["val_score"] = float(val_score)
        normalized.append(copied)

    return normalized


def _best_candidate(candidates: Sequence[Candidate]) -> Candidate:
    return max(
        candidates,
        key=lambda candidate: (
            float(candidate["val_score"]),
            -int(candidate["prompt_chars"]),
            _candidate_sort_id(candidate),
        ),
    )


def _build_result(
    *,
    rule_name: str,
    selected: Candidate,
    best: Candidate,
    reason: str,
    parameters: dict[str, Any],
    fallback_used: bool,
    eligible_count: int,
) -> SelectionResult:
    score_gap_to_best = float(best["val_score"]) - float(selected["val_score"])
    chars_saved_vs_best = int(best["prompt_chars"]) - int(selected["prompt_chars"])
    length_reduction_vs_best = chars_saved_vs_best / int(best["prompt_chars"])
    return SelectionResult(
        rule_name=rule_name,
        selected_candidate=dict(selected),
        best_candidate=dict(best),
        reason=reason,
        parameters=parameters,
        fallback_used=fallback_used,
        eligible_count=eligible_count,
        score_gap_to_best=score_gap_to_best,
        chars_saved_vs_best=chars_saved_vs_best,
        length_reduction_vs_best=length_reduction_vs_best,
    )


def _candidate_sort_id(candidate: Mapping[str, Any]) -> str:
    return str(candidate["candidate_id"])
