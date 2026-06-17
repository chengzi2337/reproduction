from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER = PROJECT_ROOT / "scripts" / "run_ifbench_qwen3_smoke.py"
RUNS_ROOT = PROJECT_ROOT / ".codex" / "gepa-artifact" / "experiment_runs_data" / "experiment_runs"
LOG_ROOT = PROJECT_ROOT / ".codex" / "missing_baseline_nocache_logs"
AGGREGATE_ROOT = PROJECT_ROOT / "reports" / "replay_aggregates"
STATUS_PATH = PROJECT_ROOT / "reports" / "ifbench_qwen3_missing_baseline_nocache_status.json"
LM_NAME = "qwen3-8b-dashscope-paper-adapted"
SOURCE_RUN_NAME = f"IFBench_IFBenchCoT2StageProgram_Baseline_{LM_NAME}"
SEEDS = (1, 2)


def write_status(status: str, current_step: str, exit_code: int = 0) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "current_step": current_step,
        "seeds": list(SEEDS),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "exit_code": exit_code,
        "replay_tag_prefix": "nocache-missing-baseline",
        "disable_dspy_cache": True,
    }
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def source_run_dir(seed: int) -> Path:
    return RUNS_ROOT / f"seed_{seed}" / SOURCE_RUN_NAME


def aggregate_path(seed: int) -> Path:
    replay_tag = replay_tag_for_seed(seed)
    filename = f"{SOURCE_RUN_NAME}-{replay_tag}-baseline-aggregate.json"
    return AGGREGATE_ROOT / filename


def replay_tag_for_seed(seed: int) -> str:
    legacy_tag = f"nocache-missing-baseline-seed{seed}-t06"
    legacy_path = AGGREGATE_ROOT / f"{SOURCE_RUN_NAME}-{legacy_tag}-baseline-aggregate.json"
    if legacy_path.exists():
        return legacy_tag
    return f"nb-s{seed}-t06"


def aggregate_is_complete(seed: int) -> bool:
    path = aggregate_path(seed)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    runs = payload.get("runs")
    metric_summary = {}
    if isinstance(runs, list) and runs and isinstance(runs[0], dict):
        candidate = runs[0].get("metric_summary")
        if isinstance(candidate, dict):
            metric_summary = candidate
    return (
        payload.get("disable_dspy_cache") is True
        and payload.get("replay_kind") == "baseline"
        and payload.get("repetitions") == 1
        and metric_summary.get("metric_rows") == 294
        and not metric_summary.get("missing_indices")
        and not metric_summary.get("duplicate_indices")
    )


def run_seed(seed: int) -> int:
    source = source_run_dir(seed)
    if not source.exists():
        print(json.dumps({"seed": seed, "status": "missing_source_run", "source_run_dir": str(source)}, ensure_ascii=False), flush=True)
        return 2
    if aggregate_is_complete(seed):
        print(json.dumps({"seed": seed, "status": "skipped_complete", "aggregate": str(aggregate_path(seed))}, ensure_ascii=False), flush=True)
        return 0

    replay_tag = replay_tag_for_seed(seed)
    command = [
        sys.executable,
        str(RUNNER),
        "--yes",
        "--skip-probe",
        "--api-key-env",
        "QWEN_API_KEY",
        "--paper-adapted",
        "--cloud-low-concurrency",
        "--replay-kind",
        "baseline",
        "--replay-source-run-dir",
        str(source),
        "--replay-tag",
        replay_tag,
        "--replay-repetitions",
        "1",
        "--replay-aggregate-dir",
        str(AGGREGATE_ROOT),
        "--disable-dspy-cache",
        "--request-timeout-seconds",
        "1800",
        "--process-timeout-seconds",
        "604800",
        "--num-retries",
        "8",
    ]
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    stdout_path = LOG_ROOT / f"seed{seed}.stdout.log"
    stderr_path = LOG_ROOT / f"seed{seed}.stderr.log"
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=os.environ.copy(),
            stdout=stdout,
            stderr=stderr,
            text=True,
            check=False,
        )
    return completed.returncode


def main() -> int:
    if not os.environ.get("QWEN_API_KEY"):
        write_status("failed", "missing_api_key", 2)
        print("缺少 QWEN_API_KEY，未启动真实 no-cache replay。", file=sys.stderr)
        return 2

    write_status("running", "start")
    for seed in SEEDS:
        write_status("running", f"seed{seed}")
        exit_code = run_seed(seed)
        if exit_code != 0:
            write_status("failed", f"seed{seed}", exit_code)
            return exit_code
    write_status("complete", "done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
