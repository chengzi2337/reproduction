from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.openai_compatible_utils import build_litellm_model_name, temporary_openai_compatible_env


def test_build_litellm_model_name_supports_mimo() -> None:
    assert build_litellm_model_name("mimo-v2-flash") == "openai/mimo-v2-flash"


def test_temporary_openai_compatible_env_sets_and_restores_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "old-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)

    with temporary_openai_compatible_env(
        api_key="new-key",
        api_base="https://api.xiaomimimo.com/v1",
    ):
        assert os.environ["OPENAI_API_KEY"] == "new-key"
        assert os.environ["OPENAI_BASE_URL"] == "https://api.xiaomimimo.com/v1"
        assert os.environ["OPENAI_API_BASE"] == "https://api.xiaomimimo.com/v1"

    assert os.environ["OPENAI_API_KEY"] == "old-key"
    assert "OPENAI_BASE_URL" not in os.environ
    assert "OPENAI_API_BASE" not in os.environ
