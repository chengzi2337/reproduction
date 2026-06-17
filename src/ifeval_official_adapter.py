from __future__ import annotations

import importlib
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


OFFICIAL_PACKAGE = "instruction_following_eval"
REQUIRED_OFFICIAL_MODULES = (
    "instruction_following_eval.evaluation_lib",
    "instruction_following_eval.instructions",
    "instruction_following_eval.instructions_registry",
    "instruction_following_eval.instructions_util",
)
DEFAULT_IFEVAL_ROOT_CANDIDATES = (
    Path("external") / "google-research" / "instruction_following_eval",
    Path("..") / "google-research" / "instruction_following_eval",
)


class IFEvalOfficialAdapterError(RuntimeError):
    """官方 IFEval assets 或 checker 接入失败。"""


def normalize_ifeval_root(path: Path | None) -> Path | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    if resolved.name == OFFICIAL_PACKAGE:
        return resolved
    candidate = resolved / OFFICIAL_PACKAGE
    if candidate.exists():
        return candidate.resolve()
    return resolved


def resolve_ifeval_root(
    *,
    explicit_ifeval_root: Path | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    checked: list[Path] = []
    if explicit_ifeval_root is not None:
        checked.append(normalize_ifeval_root(explicit_ifeval_root) or explicit_ifeval_root)
    env_value = os.environ.get("IFEVAL_ROOT")
    if env_value:
        checked.append(normalize_ifeval_root(Path(env_value)) or Path(env_value))
    if project_root is not None:
        checked.extend((project_root / candidate).resolve() for candidate in DEFAULT_IFEVAL_ROOT_CANDIDATES)

    for candidate in checked:
        if candidate.exists() and candidate.is_dir():
            return {
                "ifeval_root_status": "ok",
                "ifeval_root": candidate.as_posix(),
                "checked_ifeval_roots": [path.as_posix() for path in checked],
                "repair_suggestion": None,
            }
    return {
        "ifeval_root_status": "missing",
        "ifeval_root": None,
        "checked_ifeval_roots": [path.as_posix() for path in checked],
        "repair_suggestion": (
            "请通过 --ifeval-root 指向本地 google-research/instruction_following_eval，"
            "或设置 IFEVAL_ROOT。不要把完整 google-research 仓库提交进当前 repo。"
        ),
    }


def resolve_dataset_path(
    *,
    explicit_dataset_path: Path | None = None,
    ifeval_root: Path | None = None,
    project_root: Path | None = None,
    fallback_candidates: tuple[Path, ...] = (),
) -> dict[str, Any]:
    checked: list[Path] = []
    if explicit_dataset_path is not None:
        checked.append(explicit_dataset_path.expanduser().resolve())
    if ifeval_root is not None:
        checked.append((ifeval_root / "data" / "input_data.jsonl").resolve())
    env_root = resolve_ifeval_root(project_root=project_root)
    env_root_path = Path(env_root["ifeval_root"]) if env_root["ifeval_root"] else None
    if env_root_path is not None:
        env_dataset = (env_root_path / "data" / "input_data.jsonl").resolve()
        if env_dataset not in checked:
            checked.append(env_dataset)
    if project_root is not None:
        checked.extend((project_root / candidate).resolve() for candidate in fallback_candidates)

    for candidate in checked:
        if candidate.exists() and candidate.is_file():
            return {
                "dataset_status": "ok",
                "dataset_path": candidate.as_posix(),
                "checked_paths": [path.as_posix() for path in checked],
                "repair_suggestion": None,
            }
    return {
        "dataset_status": "dataset_missing",
        "dataset_path": None,
        "checked_paths": [path.as_posix() for path in checked],
        "repair_suggestion": (
            "请准备本地官方 IFEval 数据文件，例如 "
            "`--ifeval-root external/google-research/instruction_following_eval`，"
            "或通过 --dataset-path 显式指定 input_data.jsonl。"
        ),
    }


def read_ifeval_samples(dataset_path: Path, *, limit: int = 3) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise IFEvalOfficialAdapterError("IFEval input_data.jsonl 每行必须是 JSON object。")
            for field in ("prompt", "instruction_id_list", "kwargs"):
                if field not in payload:
                    raise IFEvalOfficialAdapterError(f"IFEval 样本缺少字段：{field}。")
            samples.append(payload)
            if len(samples) >= limit:
                break
    return samples


@contextmanager
def official_import_path(ifeval_root: Path) -> Iterator[None]:
    package_parent = ifeval_root.resolve().parent
    package_parent_text = str(package_parent)
    inserted = package_parent_text not in sys.path
    if inserted:
        sys.path.insert(0, package_parent_text)
    try:
        yield
    finally:
        if inserted:
            try:
                sys.path.remove(package_parent_text)
            except ValueError:
                pass


def import_official_modules(ifeval_root: Path | None) -> dict[str, Any]:
    if ifeval_root is None:
        return {
            "checker_status": "checker_unavailable",
            "checker_module": None,
            "imported_modules": [],
            "import_error": "未提供可用的 --ifeval-root 或 IFEVAL_ROOT。",
            "repair_suggestion": "请通过 --ifeval-root 指向本地官方 instruction_following_eval 目录。",
        }
    imported: list[str] = []
    try:
        with official_import_path(ifeval_root):
            for module_name in REQUIRED_OFFICIAL_MODULES:
                importlib.import_module(module_name)
                imported.append(module_name)
    except Exception as exc:
        return {
            "checker_status": "checker_unavailable",
            "checker_module": None,
            "imported_modules": imported,
            "import_error": f"{type(exc).__name__}: {exc}",
            "repair_suggestion": (
                "请确认 --ifeval-root 指向 google-research/instruction_following_eval，"
                "且官方 evaluation_lib.py、instructions.py、instructions_registry.py、instructions_util.py 可导入。"
            ),
        }
    return {
        "checker_status": "ok",
        "checker_module": "instruction_following_eval.evaluation_lib",
        "imported_modules": imported,
        "import_error": None,
        "repair_suggestion": None,
    }


def run_checker_smoke(
    *,
    ifeval_root: Path | None,
    dataset_path: Path | None,
    sample_limit: int = 3,
    fake_response: str = "TEST RESPONSE",
) -> dict[str, Any]:
    if ifeval_root is None or dataset_path is None:
        return {
            "checker_smoke_status": "not_run",
            "checker_smoke_sample_count": 0,
            "checker_smoke_error": "缺少 IFEval root 或 dataset path。",
            "prompt_level_accuracy_available": False,
            "instruction_level_accuracy_available": False,
        }
    try:
        samples = read_ifeval_samples(dataset_path, limit=sample_limit)
        if not samples:
            raise IFEvalOfficialAdapterError("input_data.jsonl 没有可评估样本。")
        with official_import_path(ifeval_root):
            evaluation_lib = importlib.import_module("instruction_following_eval.evaluation_lib")
            inputs = evaluation_lib.read_prompt_list(str(dataset_path))[: len(samples)]
            prompt_to_response = {inp.prompt: fake_response for inp in inputs}
            strict_outputs = [
                evaluation_lib.test_instruction_following_strict(inp, prompt_to_response)
                for inp in inputs
            ]
            loose_outputs = [
                evaluation_lib.test_instruction_following_loose(inp, prompt_to_response)
                for inp in inputs
            ]
        prompt_available = all(hasattr(item, "follow_all_instructions") for item in strict_outputs)
        instruction_available = all(hasattr(item, "follow_instruction_list") for item in strict_outputs)
        return {
            "checker_smoke_status": "ok",
            "checker_smoke_sample_count": len(strict_outputs),
            "checker_smoke_error": None,
            "prompt_level_accuracy_available": prompt_available,
            "instruction_level_accuracy_available": instruction_available,
            "strict_follow_all": [bool(item.follow_all_instructions) for item in strict_outputs],
            "strict_instruction_counts": [
                len(list(item.follow_instruction_list)) for item in strict_outputs
            ],
            "loose_follow_all": [bool(item.follow_all_instructions) for item in loose_outputs],
        }
    except Exception as exc:
        return {
            "checker_smoke_status": "error",
            "checker_smoke_sample_count": 0,
            "checker_smoke_error": f"{type(exc).__name__}: {exc}",
            "prompt_level_accuracy_available": False,
            "instruction_level_accuracy_available": False,
        }
