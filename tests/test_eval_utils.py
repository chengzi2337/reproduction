from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import src.eval_utils as eval_utils


class _FakeEvaluationResult:
    def __init__(self, batch):
        self.outputs = [
            {"full_assistant_response": f"prediction-{item['input']}"} for item in batch
        ]
        self.scores = [1.0 for _ in batch]


class _FakeDefaultAdapter:
    batch_sizes: list[int] = []

    def __init__(self, model: str) -> None:
        self.model = model

    def evaluate(self, batch, candidate, capture_traces=False):
        _FakeDefaultAdapter.batch_sizes.append(len(batch))
        return _FakeEvaluationResult(batch)


def test_evaluate_candidate_uses_batched_default_adapter(monkeypatch) -> None:
    dataset = [
        {"input": f"question-{index}", "answer": f"answer-{index}", "id": f"id-{index}"}
        for index in range(5)
    ]

    monkeypatch.setattr(
        "gepa.adapters.default_adapter.default_adapter.DefaultAdapter",
        _FakeDefaultAdapter,
    )

    records, summary = eval_utils.evaluate_candidate(
        dataset=dataset,
        candidate={"system_prompt": "test prompt"},
        prompt_version="seed",
        split_name="test",
        task_model="deepseek-v4-flash",
        api_key="fake-key",
        api_base="https://api.deepseek.com",
        batch_size=2,
    )

    assert _FakeDefaultAdapter.batch_sizes == [2, 2, 1]
    assert len(records) == 5
    assert summary["evaluated_sample_count"] == 5
    assert summary["eval_model"] == "deepseek-v4-flash"
    assert summary["average_score"] == 1.0
    assert summary["num_errors"] == 0


def test_evaluate_candidate_records_batch_error(monkeypatch) -> None:
    class _ErrorAdapter:
        def __init__(self, model: str) -> None:
            self.model = model

        def evaluate(self, batch, candidate, capture_traces=False):
            raise RuntimeError("batch failed")

    dataset = [
        {"input": "q1", "answer": "a1", "id": "1"},
        {"input": "q2", "answer": "a2", "id": "2"},
    ]

    monkeypatch.setattr(
        "gepa.adapters.default_adapter.default_adapter.DefaultAdapter",
        _ErrorAdapter,
    )

    records, summary = eval_utils.evaluate_candidate(
        dataset=dataset,
        candidate={"system_prompt": "test prompt"},
        prompt_version="optimized",
        split_name="test",
        task_model="deepseek-v4-flash",
        api_key="fake-key",
        api_base="https://api.deepseek.com",
        batch_size=2,
    )

    assert len(records) == 2
    assert all(record["error"] == "RuntimeError: batch failed" for record in records)
    assert summary["num_errors"] == 2
    assert summary["average_score"] == 0.0
