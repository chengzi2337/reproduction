from __future__ import annotations

import json
import uuid
from pathlib import Path

from src.ifeval_evaluation_utils import (
    CANONICAL_SUMMARY_SOURCE,
    checker_metadata,
    compare_aggregates,
    evaluate_raw_outputs,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def workspace(name: str) -> Path:
    path = PROJECT_ROOT / "outputs" / "tmp_ifeval_evaluation_utils_tests" / f"{name}_{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    return path


def write_fake_ifeval_root(root: Path) -> tuple[Path, Path]:
    package = root / "instruction_following_eval"
    data_dir = package / "data"
    data_dir.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "instructions.py").write_text("", encoding="utf-8")
    (package / "instructions_registry.py").write_text("INSTRUCTION_DICT = {}\n", encoding="utf-8")
    (package / "instructions_util.py").write_text("", encoding="utf-8")
    (package / "evaluation_lib.py").write_text(
        "\n".join(
            [
                "from dataclasses import dataclass",
                "import json",
                "@dataclass",
                "class InputExample:",
                "    key: int",
                "    instruction_id_list: list",
                "    prompt: str",
                "    kwargs: list",
                "@dataclass",
                "class OutputExample:",
                "    instruction_id_list: list",
                "    prompt: str",
                "    response: str",
                "    follow_all_instructions: bool",
                "    follow_instruction_list: list",
                "def read_prompt_list(input_jsonl_filename):",
                "    with open(input_jsonl_filename, encoding='utf-8') as handle:",
                "        return [InputExample(**json.loads(line)) for line in handle if line.strip()]",
                "def test_instruction_following_strict(inp, prompt_to_response):",
                "    response = prompt_to_response.get(inp.prompt, '')",
                "    followed = response == 'PASS'",
                "    return OutputExample(inp.instruction_id_list, inp.prompt, response, followed, [followed])",
                "def test_instruction_following_loose(inp, prompt_to_response):",
                "    return test_instruction_following_strict(inp, prompt_to_response)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    rows = [
        {
            "key": 0,
            "prompt": "Prompt 0",
            "instruction_id_list": ["keywords:existence"],
            "kwargs": [{"keywords": ["PASS"]}],
        },
        {
            "key": 1,
            "prompt": "Prompt 1",
            "instruction_id_list": ["keywords:existence"],
            "kwargs": [{"keywords": ["PASS"]}],
        },
    ]
    dataset_path = data_dir / "input_data.jsonl"
    dataset_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return package, dataset_path


def test_checker_metadata_declares_deterministic_official_checker() -> None:
    metadata = checker_metadata()

    assert metadata["checker_source"] == "official_ifeval"
    assert metadata["aggregation_source"] == "deterministic_offline_checker"
    assert metadata["canonical_summary_source"] == CANONICAL_SUMMARY_SOURCE
    assert metadata["langdetect_seed"] == 0
    assert metadata["llm_judge_enabled"] is False


def test_evaluate_raw_outputs_returns_canonical_aggregate() -> None:
    root = workspace("aggregate")
    ifeval_root, dataset_path = write_fake_ifeval_root(root)
    raw_rows = [
        {"sample_index": 0, "prompt": "Prompt 0", "variant": "baseline", "response": "PASS", "provider_status": "ok"},
        {"sample_index": 1, "prompt": "Prompt 1", "variant": "baseline", "response": "FAIL", "provider_status": "ok"},
        {"sample_index": 0, "prompt": "Prompt 0", "variant": "baseline_mhc", "response": "PASS", "provider_status": "ok"},
        {"sample_index": 1, "prompt": "Prompt 1", "variant": "baseline_mhc", "response": "PASS", "provider_status": "ok"},
    ]

    result = evaluate_raw_outputs(
        ifeval_root=ifeval_root,
        dataset_path=dataset_path,
        raw_rows=raw_rows,
        variants=["baseline", "baseline_mhc"],
        limit=2,
    )

    assert result["evaluation"]["per_variant"]["baseline"]["prompt_level_accuracy"] == 0.5
    assert result["evaluation"]["per_variant"]["baseline_mhc"]["prompt_level_accuracy"] == 1.0
    assert result["evaluation"]["aggregation_source"] == "deterministic_offline_checker"
    assert result["pairwise"]["baseline_mhc - baseline"]["improved_sample_ids"] == [1]


def test_compare_aggregates_marks_mismatch_without_exception() -> None:
    comparison = compare_aggregates(
        {"per_variant": {"baseline": {"prompt_level_accuracy": 0.0, "instruction_level_accuracy": 0.0}}},
        {"per_variant": {"baseline": {"prompt_level_accuracy": 1.0, "instruction_level_accuracy": 1.0}}},
    )

    assert comparison["status"] == "mismatch"
    assert comparison["canonical_summary_source"] == CANONICAL_SUMMARY_SOURCE
