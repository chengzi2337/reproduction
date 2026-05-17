from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import yaml


PACKAGE_NAMES = [
    "gepa",
    "dspy",
    "litellm",
    "openai",
    "pyyaml",
    "pandas",
    "numpy",
    "tqdm",
    "pytest",
    "python-dotenv",
    "datasets",
]


class TeeStream:
    def __init__(self, *targets: Any) -> None:
        self.targets = targets

    def write(self, data: str) -> int:
        for target in self.targets:
            target.write(data)
            target.flush()
        return len(data)

    def flush(self) -> None:
        for target in self.targets:
            target.flush()

    def isatty(self) -> bool:
        return any(hasattr(target, "isatty") and target.isatty() for target in self.targets)


@contextmanager
def capture_stdout_stderr(stdout_path: Path, stderr_path: Path) -> Iterator[None]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_handle:
        sys.stdout = TeeStream(original_stdout, stdout_handle)
        sys.stderr = TeeStream(original_stderr, stderr_handle)
        try:
            yield
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr


def create_timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")


def create_run_dir(base_output_dir: Path) -> Path:
    timestamp = create_timestamp()
    normalized = f"{timestamp[:-5]}{timestamp[-5:-2]}{timestamp[-2:]}"
    run_dir = base_output_dir / normalized
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_yaml(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)


def write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write(content)


def append_text(path: Path, content: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)


def get_git_commit(project_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return None
    commit = result.stdout.strip()
    return commit or None


def get_package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package_name in PACKAGE_NAMES:
        try:
            versions[package_name] = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            versions[package_name] = "NOT_INSTALLED"
    return versions


def write_package_versions(path: Path) -> dict[str, str]:
    versions = get_package_versions()
    lines = [f"python=={platform.python_version()}"]
    lines.extend(f"{name}=={version}" for name, version in versions.items())
    write_text(path, "\n".join(lines) + "\n")
    return versions


def build_manifest(
    *,
    run_id: str,
    timestamp: str,
    project_root: Path,
    provider: str,
    api_base: str,
    task_model: str,
    reflection_model: str,
    max_metric_calls: int,
    seed: int,
    benchmark: str,
    reproduction_type: str,
    allow_model_substitution: bool,
    model_check_passed: bool,
    output_dir: Path,
    code_modified_from_gepa_official: bool,
    notes: list[str],
) -> dict[str, Any]:
    versions = get_package_versions()
    return {
        "run_id": run_id,
        "timestamp": timestamp,
        "git_commit": get_git_commit(project_root),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "gepa_version": versions["gepa"],
        "dspy_version": versions["dspy"],
        "litellm_version": versions["litellm"],
        "openai_version": versions["openai"],
        "provider": provider,
        "api_base": api_base,
        "task_model": task_model,
        "reflection_model": reflection_model,
        "max_metric_calls": max_metric_calls,
        "seed": seed,
        "benchmark": benchmark,
        "reproduction_type": reproduction_type,
        "allow_model_substitution": allow_model_substitution,
        "model_check_passed": model_check_passed,
        "output_dir": str(output_dir),
        "code_modified_from_gepa_official": code_modified_from_gepa_official,
        "notes": notes,
    }
