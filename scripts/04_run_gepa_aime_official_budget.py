from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_experiment_config
from src.gepa_official_runner import run_gepa_aime_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 GEPA AIME DeepSeek official budget 复现。")
    parser.add_argument("--config", default="configs/deepseek_official_budget.yaml", help="配置文件路径")
    parser.add_argument("--yes", action="store_true", help="确认执行 official budget")
    args = parser.parse_args()

    if not args.yes:
        print("该脚本会调用 DeepSeek API；")
        print("会产生 API 费用；")
        print("建议先跑 smoke 和 pilot；")
        print("如确认运行，请加 --yes。")
        raise SystemExit(0)

    config = load_experiment_config(PROJECT_ROOT / args.config)
    print("== GEPA AIME official budget ==")
    print("已收到 --yes，开始执行。")
    print(f"task_model: {config.task_model}")
    print(f"reflection_model: {config.reflection_model}")
    print(f"max_metric_calls: {config.max_metric_calls}")
    print(f"output_dir: {config.output_dir}")
    run_dir = run_gepa_aime_experiment(config)
    print(f"[DONE] official budget 运行完成：{run_dir}")


if __name__ == "__main__":
    main()
