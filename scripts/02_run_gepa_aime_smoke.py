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
    parser = argparse.ArgumentParser(description="运行 GEPA AIME DeepSeek smoke 复现。")
    parser.add_argument("--config", default="configs/deepseek_smoke.yaml", help="配置文件路径")
    args = parser.parse_args()

    config = load_experiment_config(PROJECT_ROOT / args.config)
    run_dir = run_gepa_aime_experiment(config)
    print(f"[DONE] smoke 运行完成：{run_dir}")


if __name__ == "__main__":
    main()
