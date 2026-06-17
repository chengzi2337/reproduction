from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.ifeval_prompt_transfer_preflight import (
    DEFAULT_VARIANT_CONFIG_PATH,
    build_preflight_result,
)
from src.logging_utils import create_timestamp, write_json


DEFAULT_OUTPUT_JSON_PATH = PROJECT_ROOT / "reports" / "ifeval_prompt_transfer_runner_status.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="IFEval prompt-transfer runner stub；默认 dry-run，不调用模型。"
    )
    parser.add_argument("--variant-config", default=str(DEFAULT_VARIANT_CONFIG_PATH))
    parser.add_argument("--dataset-path", default=None)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON_PATH))
    parser.add_argument("--dry-run", action="store_true", help="显式保持 dry-run；默认也是 dry-run。")
    parser.add_argument(
        "--enable-api-run",
        action="store_true",
        help="显式请求真实运行；当前 stub 未实现真实调用，会返回 blocked。",
    )
    return parser.parse_args(argv)


def build_runner_status(args: argparse.Namespace) -> dict[str, Any]:
    dataset_path = Path(args.dataset_path) if args.dataset_path else None
    preflight = build_preflight_result(
        variant_config_path=Path(args.variant_config),
        dataset_path=dataset_path,
    )
    if args.enable_api_run:
        return {
            "status": "blocked",
            "mode": "api_run_requested_but_not_implemented",
            "generated_at": create_timestamp(),
            "api_call_enabled": False,
            "real_run_implemented": False,
            "blocked_reasons": [
                "真实 IFEval API runner 尚未实现。",
                "本任务只交付 preflight 和 dry-run 框架。",
                "禁止静默 fallback 到任何云调用。",
            ],
            "preflight_status": preflight["status"],
            "dataset_status": preflight["dataset_status"],
            "checker_status": preflight["checker_status"],
            "variant_count": preflight["variant_count"],
        }
    return {
        "status": "dry_run",
        "mode": "dry_run",
        "generated_at": create_timestamp(),
        "api_call_enabled": False,
        "real_run_implemented": False,
        "preflight_status": preflight["status"],
        "dataset_status": preflight["dataset_status"],
        "checker_status": preflight["checker_status"],
        "variant_count": preflight["variant_count"],
        "blocked_reasons": preflight["blocked_reasons"],
        "next_real_run_requires": [
            "接入本地 IFEval rule checker。",
            "显式指定本地 IFEval 数据文件。",
            "单独实现真实调用路径并再次审计。",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    status = build_runner_status(args)
    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, status)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 2 if args.enable_api_run else 0


if __name__ == "__main__":
    raise SystemExit(main())
