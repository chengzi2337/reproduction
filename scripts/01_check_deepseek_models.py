from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_experiment_config
from src.deepseek_utils import probe_model_with_openai_client
from src.logging_utils import create_timestamp, write_text


def _write_blocked_report(*, project_root: Path, failed_model: str, reason: str, error_body: str = "") -> Path:
    blocked_dir = project_root / "outputs" / f"model_check_failed_{create_timestamp()}"
    blocked_dir.mkdir(parents=True, exist_ok=False)
    report_path = blocked_dir / "blocked_report.md"
    lines = [
        "# 模型检查阻塞报告",
        "",
        f"- 失败模型：`{failed_model}`",
        f"- 失败原因：{reason}",
        "- 当前阶段禁止模型替换。",
        "- 请检查 DEEPSEEK_API_KEY、DEEPSEEK_API_BASE、model id、余额、权限或限流状态。",
        "",
    ]
    if error_body:
        lines.extend(["## 错误体", "", "```text", error_body, "```", ""])
    write_text(report_path, "\n".join(lines))
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="检查 DeepSeek 模型可用性。")
    parser.add_argument("--config", default="configs/deepseek_smoke.yaml", help="配置文件路径")
    args = parser.parse_args()

    load_dotenv()
    try:
        config = load_experiment_config(PROJECT_ROOT / args.config)
    except Exception as exc:
        report_path = _write_blocked_report(
            project_root=PROJECT_ROOT,
            failed_model="配置或环境变量",
            reason=f"{type(exc).__name__}: {exc}",
        )
        print(f"[FAIL] 配置检查失败，详情见 {report_path}")
        raise SystemExit(1) from exc

    print("== DeepSeek 模型检查 ==")
    print(f"api_base: {config.api_base}")
    print(f"task_model: {config.task_model}")
    print(f"reflection_model: {config.reflection_model}")
    print("不会打印 API key。")
    print("")

    for label, model_name in [("task_model", config.task_model), ("reflection_model", config.reflection_model)]:
        result = probe_model_with_openai_client(
            api_key=config.api_key,
            api_base=config.api_base,
            model_name=model_name,
        )
        if result.ok:
            print(f"[OK] {label} 可用，响应为: {result.response_text!r}")
            continue

        report_path = _write_blocked_report(
            project_root=PROJECT_ROOT,
            failed_model=model_name,
            reason=f"{result.error_type}: {result.error_message}",
            error_body=result.error_body or "",
        )
        print(f"[FAIL] {label} 不可用")
        print(f"  model: {model_name}")
        print(f"  error_type: {result.error_type}")
        print(f"  error_message: {result.error_message}")
        print(f"  blocked_report: {report_path}")
        raise SystemExit(1)

    print("")
    print("[DONE] task_model 和 reflection_model 均通过最小请求检查。")


if __name__ == "__main__":
    main()
