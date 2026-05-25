import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.length_controlled_selection import (
    select_best_val,
    select_lexicographic,
    select_shortest_within_score_gap,
    select_with_hard_cap_then_best_val,
    select_with_soft_length_penalty,
)


def _candidate(candidate_id, val_score, prompt_chars):
    return {
        "candidate_id": candidate_id,
        "val_score": val_score,
        "prompt_chars": prompt_chars,
        "prompt_text": "x" * prompt_chars,
    }


def test_select_best_val_prefers_score_then_shorter_tie():
    result = select_best_val(
        [
            _candidate("long_tie", 0.8, 900),
            _candidate("short_tie", 0.8, 300),
            _candidate("lower", 0.7, 100),
        ]
    )

    assert result.rule_name == "best_val"
    assert result.selected_candidate["candidate_id"] == "short_tie"
    assert result.fallback_used is False


def test_select_shortest_within_score_gap_uses_near_best_shorter():
    result = select_shortest_within_score_gap(
        [
            _candidate("best_long", 0.82, 1000),
            _candidate("near_short", 0.80, 250),
            _candidate("too_low", 0.75, 120),
        ],
        max_gap=0.02,
    )

    assert result.selected_candidate["candidate_id"] == "near_short"
    assert result.eligible_count == 2
    assert result.score_gap_to_best == pytest.approx(0.02)
    assert result.chars_saved_vs_best == 750


def test_soft_length_penalty_can_select_shorter_candidate():
    result = select_with_soft_length_penalty(
        [
            _candidate("best_long", 0.82, 1000),
            _candidate("shorter", 0.80, 250),
        ],
        lambda_chars=0.05,
    )

    assert result.rule_name == "soft_length_penalty"
    assert result.selected_candidate["candidate_id"] == "shorter"
    assert result.selected_candidate["adjusted_score"] == pytest.approx(0.7875)


def test_ratio_guard_selects_shortest_above_fraction():
    result = select_lexicographic(
        [
            _candidate("best_long", 0.90, 1200),
            _candidate("above_guard_short", 0.86, 300),
            _candidate("below_guard", 0.84, 100),
        ],
        min_score_fraction=0.95,
        prefer_shorter=True,
    )

    assert result.selected_candidate["candidate_id"] == "above_guard_short"
    assert result.parameters["score_threshold"] == pytest.approx(0.855)
    assert result.eligible_count == 2


def test_hard_cap_falls_back_when_cap_candidate_quality_is_too_low():
    result = select_with_hard_cap_then_best_val(
        [
            _candidate("best_long", 0.90, 1200),
            _candidate("under_cap_low", 0.70, 300),
        ],
        max_chars=500,
        max_score_gap=0.05,
    )

    assert result.selected_candidate["candidate_id"] == "best_long"
    assert result.fallback_used is True
    assert result.eligible_count == 0


def test_hard_cap_selects_cap_candidate_when_near_best():
    result = select_with_hard_cap_then_best_val(
        [
            _candidate("best_long", 0.90, 1200),
            _candidate("under_cap_near", 0.87, 300),
            _candidate("under_cap_lower", 0.84, 250),
        ],
        max_chars=500,
        max_score_gap=0.05,
    )

    assert result.selected_candidate["candidate_id"] == "under_cap_near"
    assert result.fallback_used is False
    assert result.eligible_count == 1


@pytest.mark.parametrize(
    ("candidates", "message"),
    [
        ([], "不能为空"),
        ([{"candidate_id": "missing", "val_score": 0.1}], "缺少必需字段"),
        ([_candidate("bad_chars", 0.1, 0)], "必须大于 0"),
        ([_candidate("bad_score", True, 10)], "val_score 必须是数字"),
    ],
)
def test_invalid_candidates_raise_clear_error(candidates, message):
    with pytest.raises(ValueError, match=message):
        select_best_val(candidates)


def test_module_does_not_import_api_gepa_or_evaluator():
    source = Path("src/length_controlled_selection.py").read_text(encoding="utf-8")

    forbidden_snippets = [
        "import gepa",
        "gepa.optimize",
        "import openai",
        "import litellm",
        "requests.post",
        "httpx.",
        "urllib.request",
        "evaluate_candidate",
        "run_gepa_aime_experiment",
    ]
    for snippet in forbidden_snippets:
        assert snippet not in source
