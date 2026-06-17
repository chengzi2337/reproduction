from __future__ import annotations

import json
from pathlib import Path

from src.ifeval_official_adapter import (
    import_official_modules,
    resolve_dataset_path,
    resolve_ifeval_root,
    run_checker_smoke,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _workspace(name: str) -> Path:
    path = PROJECT_ROOT / "outputs" / "tmp_ifeval_official_adapter_tests" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_fake_root(root: Path) -> Path:
    package = root / "instruction_following_eval"
    data_dir = package / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
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
                "    return OutputExample(inp.instruction_id_list, inp.prompt, prompt_to_response[inp.prompt], False, [False])",
                "def test_instruction_following_loose(inp, prompt_to_response):",
                "    return OutputExample(inp.instruction_id_list, inp.prompt, prompt_to_response[inp.prompt], False, [False])",
                "",
            ]
        ),
        encoding="utf-8",
    )
    sample = {
        "key": 1,
        "prompt": "Say beta.",
        "instruction_id_list": ["keywords:existence"],
        "kwargs": [{"keywords": ["beta"]}],
    }
    (data_dir / "input_data.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
    return package


def test_resolve_dataset_path_prefers_explicit_dataset(monkeypatch) -> None:
    monkeypatch.delenv("IFEVAL_ROOT", raising=False)
    workspace = _workspace("explicit_dataset")
    explicit = workspace / "input_data.jsonl"
    explicit.write_text(
        json.dumps({"prompt": "p", "instruction_id_list": [], "kwargs": []}) + "\n",
        encoding="utf-8",
    )

    result = resolve_dataset_path(explicit_dataset_path=explicit, project_root=PROJECT_ROOT)

    assert result["dataset_status"] == "ok"
    assert result["dataset_path"] == explicit.resolve().as_posix()


def test_fake_official_checker_import_and_smoke(monkeypatch) -> None:
    monkeypatch.delenv("IFEVAL_ROOT", raising=False)
    workspace = _workspace("fake_checker")
    ifeval_root = _write_fake_root(workspace)
    dataset = ifeval_root / "data" / "input_data.jsonl"

    root_result = resolve_ifeval_root(explicit_ifeval_root=ifeval_root, project_root=PROJECT_ROOT)
    import_result = import_official_modules(ifeval_root)
    smoke = run_checker_smoke(ifeval_root=ifeval_root, dataset_path=dataset)

    assert root_result["ifeval_root_status"] == "ok"
    assert import_result["checker_status"] == "ok"
    assert smoke["checker_smoke_status"] == "ok"
    assert smoke["checker_smoke_sample_count"] == 1
    assert smoke["prompt_level_accuracy_available"] is True
    assert smoke["instruction_level_accuracy_available"] is True
