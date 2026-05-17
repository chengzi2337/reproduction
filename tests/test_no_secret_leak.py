from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
README_PATH = PROJECT_ROOT / "README.md"
TEXT_EXTENSIONS = {".json", ".jsonl", ".log", ".md", ".txt", ".yaml", ".yml"}


def _iter_text_files(base_dir: Path) -> list[Path]:
    if not base_dir.exists():
        return []
    return [path for path in base_dir.rglob("*") if path.is_file() and path.suffix in TEXT_EXTENSIONS]


def test_outputs_do_not_contain_actual_api_key() -> None:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    for path in _iter_text_files(OUTPUTS_DIR):
        content = path.read_text(encoding="utf-8", errors="ignore")
        if api_key:
            assert api_key not in content, f"检测到 API key 泄露：{path}"


def test_dotenv_is_not_tracked_by_git() -> None:
    result = subprocess.run(
        ["git", "ls-files", ".env"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == ""


def test_manifest_contains_no_api_key_field() -> None:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    forbidden_keys = {"api_key", "deepseek_api_key", "openai_api_key"}
    for manifest_path in OUTPUTS_DIR.rglob("manifest.json"):
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert forbidden_keys.isdisjoint({key.lower() for key in payload.keys()})
        if api_key:
            assert api_key not in json.dumps(payload, ensure_ascii=False), f"manifest 泄露了 API key：{manifest_path}"


def test_config_resolved_contains_no_api_key_field() -> None:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    forbidden_keys = {"api_key", "deepseek_api_key", "openai_api_key"}
    for config_path in OUTPUTS_DIR.rglob("config_resolved.yaml"):
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        assert forbidden_keys.isdisjoint({str(key).lower() for key in payload.keys()})
        if api_key:
            assert api_key not in json.dumps(payload, ensure_ascii=False), f"config_resolved 泄露了 API key：{config_path}"


def test_readme_contains_no_real_api_key() -> None:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    content = README_PATH.read_text(encoding="utf-8")
    if api_key:
        assert api_key not in content
