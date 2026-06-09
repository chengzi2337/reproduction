from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "probe_ifbench_dashscope_compatibility.py"


def load_module():
    spec = importlib.util.spec_from_file_location("probe_ifbench_dashscope_compatibility", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_args_defaults() -> None:
    module = load_module()
    args = module.parse_args([])
    assert args.api_key_env == "QWEN_API_KEY"
    assert args.api_base == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert args.model == "qwen3-8b"
    assert args.execute is False


def test_findings_mark_top_k_and_enable_thinking_as_non_strict() -> None:
    module = load_module()
    findings = {item.item: item for item in module.build_doc_findings()}
    assert findings["top_k=20"].status == "兼容页未承诺"
    assert findings["enable_thinking"].status == "仅原生页明确"
    assert "兼容页参数表未列出" in findings["enable_thinking"].compatible_evidence


def test_env_resolution_prefers_requested_name_then_fallbacks(monkeypatch) -> None:
    module = load_module()
    monkeypatch.delenv("PRIMARY_QWEN_KEY", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fallback-secret")
    name, value = module.resolve_api_key("PRIMARY_QWEN_KEY")
    assert name == "DASHSCOPE_API_KEY"
    assert value == "fallback-secret"


def test_render_report_mentions_missing_live_probe_when_env_absent() -> None:
    module = load_module()
    args = module.parse_args([])
    report = module.render_report(
        args=args,
        findings=module.build_doc_findings(),
        env_presence={"QWEN_API_KEY": False, "DASHSCOPE_API_KEY": False, "OPENAI_API_KEY": False},
        selected_api_key_env=None,
        probe_results=[],
        live_probe_status="skipped_missing_env",
        gate_text="strict reproduction 仍不满足启动条件；仅可继续 backend-adapted 预备审计。",
    )
    assert "当前没有任何可安全复用的 API key 环境变量" in report
    assert "OpenAI-compatible 文档明确承诺了 `temperature`、`top_p`、`max_tokens`、`stop`" in report
    assert "compatibility-of-openai-with-dashscope" in report


def test_run_live_probes_explicitly_disables_thinking_for_non_stream_calls(monkeypatch) -> None:
    module = load_module()
    captured_requests: list[tuple[str, dict[str, object]]] = []

    def fake_build_client(*, api_key: str, api_base: str) -> object:
        assert api_key == "secret"
        assert api_base == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        return object()

    def fake_run_probe_case(
        client: object,
        *,
        api_key: str,
        model: str,
        timeout_seconds: int,
        name: str,
        description: str,
        request_kwargs: dict[str, object],
    ) -> object:
        captured_requests.append((name, request_kwargs))
        return module.ProbeOutcome(
            name=name,
            description=description,
            ok=True,
            finish_reason="stop",
            content="OK",
            reasoning_content="",
            status_code=None,
            error_type=None,
            error_message="",
            usage=None,
        )

    monkeypatch.setattr(module, "build_client", fake_build_client)
    monkeypatch.setattr(module, "run_probe_case", fake_run_probe_case)

    args = module.parse_args([])
    module.run_live_probes(args, "secret")

    request_map = {name: kwargs for name, kwargs in captured_requests}
    assert request_map["baseline_ok"]["extra_body"] == {"enable_thinking": False}
    assert request_map["top_k_extra_body"]["extra_body"] == {
        "enable_thinking": False,
        "top_k": 20,
    }
    assert request_map["stop_string"]["extra_body"] == {"enable_thinking": False}
    assert request_map["max_tokens_16384_acceptance"]["extra_body"] == {
        "enable_thinking": False
    }
    assert request_map["enable_thinking_extra_body"]["extra_body"] == {"enable_thinking": True}
