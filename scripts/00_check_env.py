from __future__ import annotations

import importlib.metadata
import os
import platform
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DEFAULT_DEEPSEEK_API_BASE


PACKAGE_NAMES = [
    "gepa",
    "dspy",
    "litellm",
    "openai",
    "pyyaml",
    "pandas",
    "numpy",
]


def _version_of(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return "NOT_INSTALLED"


def main() -> None:
    load_dotenv()
    print("== 环境检查 ==")
    print(f"Python version: {platform.python_version()}")
    print(f"OS/platform: {platform.platform()}")
    print(f"当前工作目录: {Path.cwd()}")
    print("")
    print("== 包版本 ==")
    for package_name in PACKAGE_NAMES:
        print(f"{package_name}: {_version_of(package_name)}")

    api_key_exists = bool(os.getenv("DEEPSEEK_API_KEY"))
    api_base = str(os.getenv("DEEPSEEK_API_BASE") or "").strip()
    task_model = str(os.getenv("TASK_MODEL") or "").strip()
    reflection_model = str(os.getenv("REFLECTION_MODEL") or "").strip()

    print("")
    print("== 环境变量 ==")
    print(f"DEEPSEEK_API_KEY: {'已设置' if api_key_exists else '未设置'}")
    print(f"DEEPSEEK_API_BASE: {api_base or f'未设置（默认将使用 {DEFAULT_DEEPSEEK_API_BASE}）'}")
    print(f"TASK_MODEL: {task_model or '未设置'}")
    print(f"REFLECTION_MODEL: {reflection_model or '未设置'}")

    errors: list[str] = []
    if not task_model:
        errors.append("缺少 TASK_MODEL。请通过环境变量配置任务模型。")
    if not reflection_model:
        errors.append("缺少 REFLECTION_MODEL。请通过环境变量配置反思模型。")

    if errors:
        print("")
        print("== 错误 ==")
        for message in errors:
            print(f"- {message}")
        raise SystemExit(1)

    if not api_key_exists:
        print("")
        print("== 警告 ==")
        print("- 当前未设置 DEEPSEEK_API_KEY，后续模型检查和实际运行会失败。")

    print("")
    print("环境变量检查完成。")


if __name__ == "__main__":
    main()
