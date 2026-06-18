from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "analyze_ifeval_prompt_transfer_smoke.py"
VARIANTS = [
    "baseline",
    "baseline_mhc",
    "verbose_helpfulness",
    "mhc_concise",
    "ifbench_gepa_prompt_transfer",
    "gepa_p2_transfer",
]


def workspace(name: str) -> Path:
    path = PROJECT_ROOT / "outputs" / "tmp_analyze_ifeval_smoke_tests" / f"{name}_{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    return path


def load_module():
    spec = importlib.util.spec_from_file_location("analyze_ifeval_prompt_transfer_smoke", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_fake_ifeval_root(root: Path, sample_count: int = 2) -> tuple[Path, Path]:
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
                "    followed = 'PASS' in response",
                "    return OutputExample(inp.instruction_id_list, inp.prompt, response, followed, [followed for _ in inp.instruction_id_list])",
                "def test_instruction_following_loose(inp, prompt_to_response):",
                "    return test_instruction_following_strict(inp, prompt_to_response)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    rows = [
        {
            "key": index,
            "prompt": f"Prompt {index}",
            "instruction_id_list": ["keywords:existence"],
            "kwargs": [{"keywords": ["PASS"]}],
        }
        for index in range(sample_count)
    ]
    dataset_path = data_dir / "input_data.jsonl"
    dataset_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return package, dataset_path


def raw_response_for(variant_id: str, sample_index: int) -> str:
    table = {
        "baseline": ["FAIL", "PASS"],
        "baseline_mhc": ["PASS", "FAIL"],
        "verbose_helpfulness": ["FAIL", "PASS"],
        "mhc_concise": ["PASS", "FAIL"],
        "ifbench_gepa_prompt_transfer": ["FAIL", "PASS"],
        "gepa_p2_transfer": ["PASS", "PASS"],
    }
    return table[variant_id][sample_index]


def write_fake_smoke_dir(tmp_path: Path, *, omit_variant: str | None = None, extra_sample: bool = False) -> Path:
    smoke_dir = tmp_path / "smoke"
    smoke_dir.mkdir()
    ifeval_root, dataset_path = write_fake_ifeval_root(tmp_path / "official")
    raw_rows = []
    for sample_index in range(2):
        prompt = f"Prompt {sample_index}"
        for variant_id in VARIANTS:
            if variant_id == omit_variant:
                continue
            raw_rows.append(
                {
                    "sample_index": sample_index,
                    "prompt": prompt,
                    "variant": variant_id,
                    "response": raw_response_for(variant_id, sample_index),
                    "provider_status": "ok",
                    "provider_error": None,
                    "finish_reason": "stop",
                    "usage": {},
                }
            )
    if extra_sample:
        raw_rows.append(
            {
                "sample_index": 99,
                "prompt": "Prompt 99",
                "variant": "baseline",
                "response": "PASS",
                "provider_status": "ok",
                "provider_error": None,
                "finish_reason": "stop",
                "usage": {},
            }
        )
    (smoke_dir / "raw_outputs.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in raw_rows),
        encoding="utf-8",
    )
    write_json(
        smoke_dir / "run_config.json",
        {
            "dataset_path": str(dataset_path),
            "ifeval_root": str(ifeval_root),
            "limit": 2,
            "variants": VARIANTS,
            "api_run_enabled": True,
            "gepa_optimization_enabled": False,
        },
    )
    write_json(smoke_dir / "eval_results.json", {"per_variant": {}})
    write_json(smoke_dir / "summary.json", {"status": "completed", "limit": 2})
    write_json(
        smoke_dir / "provider_events.json",
        {
            "provider_error_count": 0,
            "provider_rejection_count": 0,
            "timeout_count": 0,
            "provider_status_counts": {"ok": len(raw_rows)},
            "events": [],
        },
    )
    return smoke_dir


def test_analyzer_reads_minimal_fake_smoke_and_writes_outputs() -> None:
    module = load_module()
    tmp_path = workspace("minimal")
    smoke_dir = write_fake_smoke_dir(tmp_path)

    audit = module.analyze_smoke(smoke_dir)
    matrix_payload = json.loads((smoke_dir / "pairwise_sample_matrix.json").read_text(encoding="utf-8"))
    markdown = (smoke_dir / "audit.md").read_text(encoding="utf-8")
    csv_text = (smoke_dir / "pairwise_sample_matrix.csv").read_text(encoding="utf-8")

    assert audit["status"] == "completed"
    assert audit["actual_raw_output_rows"] == 12
    assert matrix_payload["sample_count"] == 2
    assert markdown.strip()
    assert csv_text.startswith("sample_index,")


def test_analyzer_detects_missing_variant_rows() -> None:
    module = load_module()
    tmp_path = workspace("missing_variant")
    smoke_dir = write_fake_smoke_dir(tmp_path, omit_variant="gepa_p2_transfer")

    audit = module.analyze_smoke(smoke_dir)

    assert audit["status"] == "blocked"
    assert audit["sample_consistency"]["per_variant"]["gepa_p2_transfer"]["missing_sample_indexes"] == [0, 1]


def test_analyzer_detects_inconsistent_sample_set() -> None:
    module = load_module()
    tmp_path = workspace("inconsistent_samples")
    smoke_dir = write_fake_smoke_dir(tmp_path, extra_sample=True)

    audit = module.analyze_smoke(smoke_dir)

    assert audit["status"] == "blocked"
    assert audit["sample_consistency"]["per_variant"]["baseline"]["extra_sample_indexes"] == [99]


def test_pairwise_improved_degraded_tied_counts() -> None:
    module = load_module()
    tmp_path = workspace("pairwise")
    smoke_dir = write_fake_smoke_dir(tmp_path)

    module.analyze_smoke(smoke_dir)
    matrix_payload = json.loads((smoke_dir / "pairwise_sample_matrix.json").read_text(encoding="utf-8"))
    baseline_mhc = matrix_payload["pairwise_comparisons"]["baseline_mhc - baseline"]
    gepa_p2 = matrix_payload["pairwise_comparisons"][
        "gepa_p2_transfer - ifbench_gepa_prompt_transfer"
    ]

    assert baseline_mhc["improved_sample_count"] == 1
    assert baseline_mhc["degraded_sample_count"] == 1
    assert baseline_mhc["tied_sample_count"] == 0
    assert baseline_mhc["improved_sample_ids"] == [0]
    assert baseline_mhc["degraded_sample_ids"] == [1]
    assert gepa_p2["improved_sample_count"] == 1
    assert gepa_p2["degraded_sample_count"] == 0
    assert gepa_p2["tied_sample_count"] == 1


def test_missing_input_writes_structured_blocked_outputs() -> None:
    module = load_module()
    tmp_path = workspace("missing_input")
    smoke_dir = tmp_path / "missing"
    smoke_dir.mkdir()

    audit = module.analyze_smoke(smoke_dir)
    audit_json = json.loads((smoke_dir / "audit.json").read_text(encoding="utf-8"))

    assert audit["status"] == "blocked"
    assert audit_json["status"] == "blocked"
    assert (smoke_dir / "audit.md").read_text(encoding="utf-8").strip()
    assert json.loads((smoke_dir / "pairwise_sample_matrix.json").read_text(encoding="utf-8"))["status"] == "blocked"


def test_analyzer_module_does_not_import_provider_client() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "from openai import" not in source.lower()
    assert "OpenAI(" not in source
