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
    assert summary["requested_sample_count"] == 5
    assert summary["eval_model"] == "deepseek-v4-flash"
    assert summary["average_score"] == 1.0
    assert summary["num_errors"] == 0
    assert summary["is_complete"] is True
    assert all("attempt_count" in record for record in records)
    assert all(record["attempt_count"] == 1 for record in records)


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
    assert all(record["error"] == "RuntimeError after 1 attempts: batch failed" for record in records)
    assert summary["num_errors"] == 2
    assert summary["average_score"] == 0.0
    assert all(record["attempt_count"] == 1 for record in records)


def test_evaluate_candidate_retries_before_marking_error(monkeypatch) -> None:
    class _FlakyAdapter:
        attempts = 0

        def __init__(self, model: str) -> None:
            self.model = model

        def evaluate(self, batch, candidate, capture_traces=False):
            _FlakyAdapter.attempts += 1
            if _FlakyAdapter.attempts == 1:
                raise RuntimeError("transient failure")
            return _FakeEvaluationResult(batch)

    dataset = [{"input": "q1", "answer": "a1", "id": "1"}]

    monkeypatch.setattr(
        "gepa.adapters.default_adapter.default_adapter.DefaultAdapter",
        _FlakyAdapter,
    )

    records, summary = eval_utils.evaluate_candidate(
        dataset=dataset,
        candidate={"system_prompt": "test prompt"},
        prompt_version="seed",
        split_name="test",
        task_model="deepseek-v4-flash",
        api_key="fake-key",
        api_base="https://api.deepseek.com",
        batch_size=1,
        max_retries=1,
        retry_sleep_seconds=0.0,
    )

    assert _FlakyAdapter.attempts == 2
    assert summary["num_errors"] == 0
    assert records[0]["error"] is None
    assert records[0]["attempt_count"] == 2


def test_evaluate_candidate_resume_skips_completed_samples(monkeypatch, tmp_path: Path) -> None:
    class _ResumeAdapter:
        batch_sizes: list[int] = []

        def __init__(self, model: str) -> None:
            self.model = model

        def evaluate(self, batch, candidate, capture_traces=False):
            _ResumeAdapter.batch_sizes.append(len(batch))
            return _FakeEvaluationResult(batch)

    dataset = [
        {"input": "q1", "answer": "a1", "id": "1"},
        {"input": "q2", "answer": "a2", "id": "2"},
        {"input": "q3", "answer": "a3", "id": "3"},
    ]
    checkpoint = tmp_path / "per_example_eval.jsonl"
    existing_records = [
        {
            "sample_id": "1",
            "prompt_version": "seed",
            "question": "q1",
            "prediction": "p1",
            "gold": "a1",
            "score": 1.0,
            "error": None,
        }
    ]

    monkeypatch.setattr(
        "gepa.adapters.default_adapter.default_adapter.DefaultAdapter",
        _ResumeAdapter,
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
        existing_prompt_records=existing_records,
        checkpoint_path=checkpoint,
    )

    assert _ResumeAdapter.batch_sizes == [2]
    assert len(records) == 3
    assert summary["completed_from_resume"] == 1
    assert summary["num_new_records"] == 2
    checkpoint_records = eval_utils.read_jsonl(checkpoint)
    assert len(checkpoint_records) == 2


def test_normalize_records_keeps_latest_result_per_prompt_and_sample() -> None:
    records = [
        {
            "sample_id": "1",
            "prompt_version": "seed",
            "score": 0.0,
            "error": "RuntimeError: old failure",
        },
        {
            "sample_id": "1",
            "prompt_version": "seed",
            "score": 1.0,
            "error": None,
        },
        {
            "sample_id": "1",
            "prompt_version": "optimized",
            "score": 0.0,
            "error": "RuntimeError: optimized failure",
        },
    ]

    normalized = eval_utils.normalize_records(records)
    assert len(normalized) == 2
    seed_record = next(record for record in normalized if record["prompt_version"] == "seed")
    assert seed_record["score"] == 1.0
    assert seed_record["error"] is None


def test_split_effective_records_only_marks_success_for_resume() -> None:
    records = [
        {
            "sample_id": "1",
            "prompt_version": "seed",
            "score": 0.0,
            "error": "RuntimeError: failed",
        },
        {
            "sample_id": "2",
            "prompt_version": "seed",
            "score": 1.0,
            "error": None,
        },
        {
            "sample_id": "1",
            "prompt_version": "optimized",
            "score": 1.0,
            "error": None,
        },
    ]

    successful, failed = eval_utils.split_effective_records(records, prompt_version="seed")
    assert [record["sample_id"] for record in successful] == ["2"]
    assert [record["sample_id"] for record in failed] == ["1"]


def test_normalize_default_adapter_sample_adds_missing_additional_context() -> None:
    sample = {"input": "question", "answer": "### 1", "id": "x"}
    normalized = eval_utils.normalize_default_adapter_sample(sample)
    assert normalized["input"] == "question"
    assert normalized["answer"] == "### 1"
    assert normalized["additional_context"] == {}
