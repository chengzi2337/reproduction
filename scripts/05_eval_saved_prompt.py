from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_experiment_config
from src.eval_utils import evaluate_candidate, load_prompt_candidate, write_jsonl
from src.gepa_official_runner import load_official_aime_dataset
from src.logging_utils import append_text, create_timestamp, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="评估已保存的 seed / optimized prompt。")
    parser.add_argument("--run-dir", required=True, help="运行目录，例如 outputs/gepa_aime_pilot/<timestamp>")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        raise FileNotFoundError(f"运行目录不存在：{run_dir}")

    config = load_experiment_config(
        run_dir / "config_resolved.yaml",
        project_root=PROJECT_ROOT,
    )
    seed_candidate = load_prompt_candidate(run_dir / "seed_prompt.json")
    optimized_candidate = load_prompt_candidate(run_dir / "optimized_prompt.json")
    eval_timestamp = create_timestamp()

    _, valset, testset, _, _ = load_official_aime_dataset()
    if testset is not None:
        dataset = testset
        split_name = "test"
        split_label = "test split"
    else:
        dataset = valset
        split_name = "val"
        split_label = "validation sanity check only"
        append_text(
            run_dir / "notes.md",
            "\n## 评估附注\n\n"
            "- current GEPA official example did not expose a test split in this package version; using validation sanity check only.\n",
        )

    seed_records, seed_summary = evaluate_candidate(
        dataset=dataset,
        candidate=seed_candidate,
        prompt_version="seed",
        split_name=split_name,
        task_model=config.task_model,
        api_key=config.api_key,
        api_base=config.api_base,
    )
    optimized_records, optimized_summary = evaluate_candidate(
        dataset=dataset,
        candidate=optimized_candidate,
        prompt_version="optimized",
        split_name=split_name,
        task_model=config.task_model,
        api_key=config.api_key,
        api_base=config.api_base,
    )

    all_records = seed_records + optimized_records
    write_jsonl(run_dir / "per_example_eval.jsonl", all_records)

    score_delta = optimized_summary["average_score"] - seed_summary["average_score"]
    summary = {
        "split": split_name,
        "split_label": split_label,
        "eval_model": config.task_model,
        "eval_timestamp": eval_timestamp,
        "evaluated_sample_count": seed_summary["evaluated_sample_count"],
        "seed_prompt_score": seed_summary["average_score"],
        "optimized_prompt_score": optimized_summary["average_score"],
        "score_delta": score_delta,
        "seed": seed_summary,
        "optimized": optimized_summary,
    }
    write_json(run_dir / "saved_prompt_eval_summary.json", summary)
    append_text(
        run_dir / "notes.md",
        "\n## Saved Prompt Eval\n\n"
        f"- eval_timestamp: {eval_timestamp}\n"
        f"- split: {split_label}\n"
        f"- eval_model: {config.task_model}\n"
        f"- seed_prompt_score: {seed_summary['average_score']}\n"
        f"- optimized_prompt_score: {optimized_summary['average_score']}\n"
        f"- score_delta: {score_delta}\n",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
