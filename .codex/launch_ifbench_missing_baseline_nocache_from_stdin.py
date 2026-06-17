from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUEUE_SCRIPT = PROJECT_ROOT / ".codex" / "run_ifbench_missing_baseline_nocache_replays.py"


def main() -> int:
    print("READY", flush=True)
    api_key = sys.stdin.readline().strip()
    if not api_key:
        print("缺少 API key，未启动 no-cache baseline replay 队列。", file=sys.stderr)
        return 2

    child_env = os.environ.copy()
    child_env["QWEN_API_KEY"] = api_key
    child_env["PYTHONUTF8"] = "1"
    process = subprocess.Popen(
        [sys.executable, str(QUEUE_SCRIPT)],
        cwd=PROJECT_ROOT,
        env=child_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    api_key = ""
    child_env["QWEN_API_KEY"] = ""
    print(f"STARTED_PID={process.pid}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
