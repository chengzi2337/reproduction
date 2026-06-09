from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from openai import APIStatusError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3-8b"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "reports" / "ifbench_dashscope_feasibility_audit.md"
SHANGHAI_TZ = timezone(timedelta(hours=8))

OPENAI_PYTHON_SOURCE_URL = (
    "https://github.com/openai/openai-python/blob/main/src/openai/resources/chat/completions/completions.py"
)
OPENAI_COMPAT_URL = (
    "https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope"
)
DASHSCOPE_NATIVE_URL = (
    "https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-dashscope"
)
MODEL_LIST_URL = "https://www.alibabacloud.com/help/en/model-studio/models"


@dataclass(slots=True)
class DocFinding:
    item: str
    strict_target: str
    compatible_evidence: str
    native_evidence: str
    local_repo_usage: str
    status: str
    notes: str


@dataclass(slots=True)
class ProbeOutcome:
    name: str
    description: str
    ok: bool
    finish_reason: str | None
    content: str
    reasoning_content: str
    status_code: int | None
    error_type: str | None
    error_message: str
    usage: dict[str, Any] | None


@dataclass(slots=True)
class SummaryPayload:
    timestamp: str
    selected_api_key_env: str | None
    env_presence: dict[str, bool]
    execute_requested: bool
    live_probe_status: str
    stage_gate: str
    strict_reproduction_ready: bool
    report_path: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="审计 IFBench 当前 DashScope OpenAI-compatible 后端的参数可行性，并在安全条件满足时执行最小实调。"
    )
    parser.add_argument("--api-key-env", default="QWEN_API_KEY")
    parser.add_argument("--api-base", default=os.getenv("QWEN_API_BASE", DEFAULT_API_BASE))
    parser.add_argument("--model", default=os.getenv("QWEN_MODEL", DEFAULT_MODEL))
    parser.add_argument("--request-timeout-seconds", type=int, default=45)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="仅当环境变量中已存在 API key 时执行真实最小探针；否则拒绝运行。",
    )
    args = parser.parse_args(argv)
    if args.request_timeout_seconds <= 0:
        raise SystemExit("`--request-timeout-seconds` 必须为正整数。")
    return args


def now_text() -> str:
    return datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S %z")


def build_doc_findings() -> list[DocFinding]:
    return [
        DocFinding(
            item="base_url",
            strict_target="需要通过 OpenAI SDK 指向 DashScope compatible-mode 端点。",
            compatible_evidence=f"OpenAI SDK 源码支持 `base_url`；阿里云兼容页列出北京端点 `{DEFAULT_API_BASE}`。",
            native_evidence="原生 DashScope 另有 `/api/v1` 端点，不等于 compatible-mode。",
            local_repo_usage="`scripts/run_ifbench_qwen3_smoke.py` 默认 `DEFAULT_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1`。",
            status="文档确认",
            notes="现有 IFBench wrapper 的连接方式与官方兼容页一致。",
        ),
        DocFinding(
            item="temperature=0.6",
            strict_target="论文 / artifact Qwen3 解码参数之一。",
            compatible_evidence="兼容页参数表明确支持 `temperature`，范围 `[0,2)`。",
            native_evidence="原生 DashScope 参数表也支持 `temperature`。",
            local_repo_usage="`run_ifbench_qwen3_smoke.py` 与现有 AIME Qwen3 配置均使用 `0.6`。",
            status="文档确认",
            notes="这一项可以作为 backend-adapted 运行的稳定映射项。",
        ),
        DocFinding(
            item="top_p=0.95",
            strict_target="论文 / artifact Qwen3 解码参数之一。",
            compatible_evidence="兼容页参数表明确支持 `top_p`。",
            native_evidence="原生 DashScope 参数表明确支持 `top_p`，并对 thinking / non-thinking 默认值分模型说明。",
            local_repo_usage="`run_ifbench_qwen3_smoke.py` 与 AIME Qwen3 配置均使用 `0.95`。",
            status="文档确认",
            notes="与论文协议一致，且兼容页有正式参数说明。",
        ),
        DocFinding(
            item="top_k=20",
            strict_target="论文 / artifact Qwen3 解码参数之一。",
            compatible_evidence="兼容页参数表未列出 `top_k`；DashScope Python SDK 的 OpenAI-compatible `Completions.create()` 签名显示有 `top_k`。",
            native_evidence="原生 DashScope 参数表明确支持 `top_k`，并给出“所有其他模型默认 20”。",
            local_repo_usage="`run_ifbench_qwen3_smoke.py` 通过 `extra_body.top_k=20` 传递；AIME Qwen3 配置也写死 `top_k: 20`。",
            status="兼容页未承诺",
            notes="当前仓库在用，但官方兼容页未正式写入参数表；需要实调确认当前后端是否接受。",
        ),
        DocFinding(
            item="max_tokens=16384",
            strict_target="论文 / artifact Qwen3 路径目标上限为 `16384`。",
            compatible_evidence="兼容页参数表支持 `max_tokens`，但强调“不同模型上限不同”。",
            native_evidence="原生 DashScope 页面也是按模型上限解释，不自动等于论文 Arbor 的 `16384`。",
            local_repo_usage="`run_ifbench_qwen3_smoke.py` 保守使用 `8192`；AIME Qwen3 现有配置也保守使用 `8192`。",
            status="模型上限未最终确认",
            notes="官方模型列表页面已确认 `qwen3-8b` 可用，但本轮工具未能稳定抽取其 max output 单元格；在真实 probe 前仍应保守维持 `8192`。",
        ),
        DocFinding(
            item="stop",
            strict_target="论文未显式依赖，但复现实验需要确认兼容页是否支持停止词。",
            compatible_evidence="兼容页参数表明确支持 `stop`，可传字符串或数组。",
            native_evidence="原生 DashScope 参数表也支持 `stop`。",
            local_repo_usage="当前 IFBench wrapper 未主动设置 `stop`。",
            status="文档确认",
            notes="若后续为收束输出协议增加停止词，这一项有官方兼容页保证。",
        ),
        DocFinding(
            item="enable_thinking",
            strict_target="论文没有给出 DashScope thinking 开关，但当前适配必须确认其是否改变 Qwen3 语义。",
            compatible_evidence="兼容页参数表未列出 `enable_thinking` 或 `thinking_budget`。",
            native_evidence="原生 DashScope 参数表明确支持 `enable_thinking`，并说明返回 `reasoning_content`。",
            local_repo_usage="当前 IFBench wrapper 默认 `enable_thinking=false`，AIME Qwen3 配置同样固定为 false。",
            status="仅原生页明确",
            notes="兼容页未正式承诺这一能力；如果 OpenAI-compatible 后端接受该字段，也应视作需要额外实调证明的扩展行为。",
        ),
        DocFinding(
            item="reasoning_content / reasoning_tokens",
            strict_target="如果 thinking 被打开，需要确认响应中是否有可观测字段。",
            compatible_evidence="兼容页响应参数表未列出 `reasoning_content`。",
            native_evidence="原生 DashScope 响应对象明确列出 `reasoning_content` 与 `reasoning_tokens`。",
            local_repo_usage="当前 IFBench wrapper 关闭 thinking，因此没有依赖这些字段。",
            status="仅原生页明确",
            notes="这进一步说明 compatible-mode 与原生 API 的可观测面不应直接视为等价。",
        ),
    ]


def env_order(primary_env: str) -> list[str]:
    ordered = [primary_env, "QWEN_API_KEY", "DASHSCOPE_API_KEY", "OPENAI_API_KEY"]
    unique: list[str] = []
    for name in ordered:
        if name not in unique:
            unique.append(name)
    return unique


def collect_env_presence(primary_env: str) -> dict[str, bool]:
    return {name: bool(os.getenv(name, "").strip()) for name in env_order(primary_env)}


def resolve_api_key(primary_env: str) -> tuple[str | None, str | None]:
    for name in env_order(primary_env):
        value = os.getenv(name, "").strip()
        if value:
            return name, value
    return None, None


def ensure_repo_imports() -> None:
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def redact_secret(text: str | None, secret: str) -> str:
    ensure_repo_imports()
    from src.deepseek_utils import redact_secret as _redact_secret

    return _redact_secret(text, secret)


def build_client(api_key: str, api_base: str) -> Any:
    ensure_repo_imports()
    from src.deepseek_utils import build_openai_client

    return build_openai_client(api_key=api_key, api_base=api_base)


def extract_error(exc: Exception, api_key: str) -> tuple[int | None, str, str | None]:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    body = ""
    if response is not None:
        response_text = getattr(response, "text", None)
        if isinstance(response_text, str):
            body = response_text
        elif callable(getattr(response, "json", None)):
            try:
                body = json.dumps(response.json(), ensure_ascii=False)
            except Exception:
                body = ""
    if isinstance(exc, APIStatusError) and getattr(exc, "body", None) is not None and not body:
        body = str(exc.body)
    return status_code, redact_secret(str(exc), api_key), redact_secret(body or None, api_key)


def usage_to_dict(usage: Any) -> dict[str, Any] | None:
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return usage
    return {
        key: getattr(usage, key)
        for key in dir(usage)
        if not key.startswith("_") and not callable(getattr(usage, key))
    }


def run_probe_case(
    client: Any,
    *,
    api_key: str,
    model: str,
    timeout_seconds: int,
    name: str,
    description: str,
    request_kwargs: dict[str, Any],
) -> ProbeOutcome:
    try:
        completion = client.chat.completions.create(
            model=model,
            timeout=timeout_seconds,
            **request_kwargs,
        )
        choice = completion.choices[0]
        message = choice.message
        content = str(getattr(message, "content", "") or "").strip()
        reasoning_content = str(getattr(message, "reasoning_content", "") or "").strip()
        return ProbeOutcome(
            name=name,
            description=description,
            ok=True,
            finish_reason=getattr(choice, "finish_reason", None),
            content=redact_secret(content, api_key),
            reasoning_content=redact_secret(reasoning_content, api_key),
            status_code=None,
            error_type=None,
            error_message="",
            usage=usage_to_dict(getattr(completion, "usage", None)),
        )
    except Exception as exc:
        status_code, message, _ = extract_error(exc, api_key)
        return ProbeOutcome(
            name=name,
            description=description,
            ok=False,
            finish_reason=None,
            content="",
            reasoning_content="",
            status_code=status_code,
            error_type=type(exc).__name__,
            error_message=message,
            usage=None,
        )


def run_live_probes(args: argparse.Namespace, api_key: str) -> list[ProbeOutcome]:
    client = build_client(api_key=api_key, api_base=args.api_base)
    cases = [
        (
            "baseline_ok",
            "最小成功请求，验证 compatible-mode 基础链路。",
            {
                "messages": [{"role": "user", "content": "Return exactly: OK"}],
                "temperature": 0,
                "max_tokens": 16,
                "extra_body": {"enable_thinking": False},
            },
        ),
        (
            "top_k_extra_body",
            "按当前 IFBench wrapper 的做法，经 `extra_body.top_k=20` 传入。",
            {
                "messages": [{"role": "user", "content": "Return exactly: OK"}],
                "temperature": 0,
                "max_tokens": 16,
                "extra_body": {"enable_thinking": False, "top_k": 20},
            },
        ),
        (
            "stop_string",
            "验证 compatible-mode 是否接受 `stop` 字符串。",
            {
                "messages": [{"role": "user", "content": "Return exactly: OK TOKEN AFTER"}],
                "temperature": 0,
                "max_tokens": 32,
                "stop": "TOKEN",
                "extra_body": {"enable_thinking": False},
            },
        ),
        (
            "enable_thinking_extra_body",
            "经 `extra_body.enable_thinking=true` 传入，观察是否报错或返回 reasoning 字段。",
            {
                "messages": [{"role": "user", "content": "请只返回 OK"}],
                "temperature": 0,
                "max_tokens": 32,
                "extra_body": {"enable_thinking": True},
            },
        ),
        (
            "max_tokens_16384_acceptance",
            "只检查服务端是否接受 `max_tokens=16384` 这个参数值，不把成功误写成真实上限已证实。",
            {
                "messages": [{"role": "user", "content": "Return exactly: OK"}],
                "temperature": 0,
                "max_tokens": 16384,
                "extra_body": {"enable_thinking": False},
            },
        ),
    ]
    return [
        run_probe_case(
            client,
            api_key=api_key,
            model=args.model,
            timeout_seconds=args.request_timeout_seconds,
            name=name,
            description=description,
            request_kwargs=request_kwargs,
        )
        for name, description, request_kwargs in cases
    ]


def stage_gate(findings: list[DocFinding], probe_results: list[ProbeOutcome]) -> tuple[str, bool]:
    has_compatible_gap = any(
        finding.status in {"兼容页未承诺", "仅原生页明确", "模型上限未最终确认"}
        for finding in findings
    )
    any_probe_failed = any(not result.ok for result in probe_results)
    if has_compatible_gap or any_probe_failed:
        return "strict reproduction 仍不满足启动条件；仅可继续 backend-adapted 预备审计。", False
    return "文档与最小实调均未发现新的兼容性阻断，可进入下一步受控 adapted 运行。", False


def render_findings_table(findings: list[DocFinding]) -> str:
    lines = [
        "| 项目 | strict 目标 | OpenAI-compatible 证据 | 原生 DashScope 证据 | 本地实现 | 判定 | 备注 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for finding in findings:
        lines.append(
            "| "
            + " | ".join(
                value.replace("\n", "<br>")
                for value in (
                    finding.item,
                    finding.strict_target,
                    finding.compatible_evidence,
                    finding.native_evidence,
                    finding.local_repo_usage,
                    finding.status,
                    finding.notes,
                )
            )
            + " |"
        )
    return "\n".join(lines)


def render_probe_section(probe_results: list[ProbeOutcome], execute_requested: bool) -> str:
    if not probe_results:
        if execute_requested:
            return "- 已请求执行真实 probe，但当前环境变量不可用，因此未运行。"
        return "- 本轮未执行真实 API probe；原因：当前会话环境变量中不存在可安全复用的 API key。"
    lines = [
        "| probe | 目的 | 结果 | finish_reason | reasoning_content | 错误 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in probe_results:
        outcome = "成功" if result.ok else "失败"
        reasoning = result.reasoning_content or "-"
        error = "-" if result.ok else f"{result.error_type or 'Error'}: {result.error_message}"
        lines.append(
            f"| {result.name} | {result.description} | {outcome} | {result.finish_reason or '-'} | {reasoning} | {error} |"
        )
    lines.append("")
    lines.append("补充说明：")
    for result in probe_results:
        if result.ok:
            content = result.content or "<空字符串>"
            lines.append(f"- `{result.name}` 返回内容：`{content}`")
            if result.usage:
                lines.append(
                    f"- `{result.name}` usage：`{json.dumps(result.usage, ensure_ascii=False, separators=(',', ':'))}`"
                )
    return "\n".join(lines)


def render_report(
    *,
    args: argparse.Namespace,
    findings: list[DocFinding],
    env_presence: dict[str, bool],
    selected_api_key_env: str | None,
    probe_results: list[ProbeOutcome],
    live_probe_status: str,
    gate_text: str,
) -> str:
    sources = [
        f"- OpenAI Python SDK：[{OPENAI_PYTHON_SOURCE_URL}]({OPENAI_PYTHON_SOURCE_URL})",
        f"- 阿里云 OpenAI-compatible 文档：[{OPENAI_COMPAT_URL}]({OPENAI_COMPAT_URL})",
        f"- 阿里云 DashScope 原生文档：[{DASHSCOPE_NATIVE_URL}]({DASHSCOPE_NATIVE_URL})",
        f"- 阿里云模型列表：[{MODEL_LIST_URL}]({MODEL_LIST_URL})",
    ]
    env_lines = [
        f"- `{name}`：{'present' if present else 'missing'}" for name, present in env_presence.items()
    ]
    if selected_api_key_env:
        env_lines.append(f"- 本轮若执行实调，将只使用已存在的环境变量：`{selected_api_key_env}`")
    else:
        env_lines.append("- 当前没有任何可安全复用的 API key 环境变量，因此真实 probe 被跳过。")
    return "\n".join(
        [
            "# IFBench DashScope 后端可行性审计",
            "",
            f"时间：{now_text()}",
            "",
            "## 快速结论",
            "",
            "- 当前仓库对 DashScope Qwen3 的既有适配路径是 `OpenAI-compatible + extra_body(top_k / enable_thinking)`。",
            "- 官方 OpenAI-compatible 文档明确承诺了 `temperature`、`top_p`、`max_tokens`、`stop`，但没有把 `top_k`、`enable_thinking` 写进参数表。",
            "- 官方原生 DashScope 文档明确支持 `top_k`、`enable_thinking`、`thinking_budget` 与 `reasoning_content`，说明原生接口能力更完整，但不能直接推出 compatible-mode 也同等承诺。",
            f"- 本轮 live probe 状态：`{live_probe_status}`。",
            f"- 阶段门禁：{gate_text}",
            "",
            "## 本地环境检查",
            "",
            *env_lines,
            "",
            "## 证据矩阵",
            "",
            render_findings_table(findings),
            "",
            "## 最小实调结果",
            "",
            render_probe_section(probe_results, args.execute),
            "",
            "## 当前判定",
            "",
            "- `temperature=0.6`、`top_p=0.95`、`stop`：可视为有官方 compatible-mode 文档支撑的映射项。",
            "- `top_k=20`：当前仓库在用，但更接近“SDK/原生页暗示可用，兼容页未正式承诺”。",
            "- `enable_thinking`：当前应继续默认关闭；若未来要打开，必须以实调结果而非推断为准。",
            "- `max_tokens=16384`：论文 strict 目标仍未闭环。当前仓库继续保守使用 `8192` 是合理防御性选择。",
            "",
            "## 下一步建议",
            "",
            f"1. 先在本机安全设置环境变量，例如 `setx {args.api_key_env} <value>` 或仅在当前 shell 临时导出，然后运行：",
            "",
            "```powershell",
            "python scripts/probe_ifbench_dashscope_compatibility.py --execute",
            "```",
            "",
            "2. 如果 `top_k_extra_body` 或 `enable_thinking_extra_body` 失败，应把 IFBench wrapper 明确降级为“只依赖兼容页正式参数”的实现。",
            "3. 如果 `max_tokens_16384_acceptance` 失败，则论文 strict reproduction 在当前 DashScope 路径上可直接判定为后端不等价。",
            "4. 在真实 probe 完成前，不启动正式 IFBench Baseline / GEPA 大预算 run。",
            "",
            "## 资料来源",
            "",
            *sources,
        ]
    )


def write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    findings = build_doc_findings()
    env_presence = collect_env_presence(args.api_key_env)
    selected_api_key_env, api_key = resolve_api_key(args.api_key_env)
    probe_results: list[ProbeOutcome] = []

    if args.execute and not api_key:
        raise SystemExit(
            "当前环境变量中没有可安全复用的 API key。为了避免把密钥写进命令日志，本脚本不会从命令行参数接收明文 key。"
        )

    live_probe_status = "skipped_missing_env"
    if args.execute and api_key:
        probe_results = run_live_probes(args, api_key)
        live_probe_status = "executed"

    gate_text, strict_ready = stage_gate(findings, probe_results)
    report = render_report(
        args=args,
        findings=findings,
        env_presence=env_presence,
        selected_api_key_env=selected_api_key_env,
        probe_results=probe_results,
        live_probe_status=live_probe_status,
        gate_text=gate_text,
    )
    write_report(args.report_path, report)
    payload = SummaryPayload(
        timestamp=now_text(),
        selected_api_key_env=selected_api_key_env,
        env_presence=env_presence,
        execute_requested=bool(args.execute),
        live_probe_status=live_probe_status,
        stage_gate=gate_text,
        strict_reproduction_ready=strict_ready,
        report_path=str(args.report_path),
    )
    print(json.dumps(asdict(payload), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
