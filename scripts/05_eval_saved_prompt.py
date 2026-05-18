from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_experiment_config
from src.eval_utils import (
    DEFAULT_EVAL_BATCH_SIZE,
    evaluate_candidate,
    load_prompt_candidate,
    normalize_records,
    read_jsonl,
    split_effective_records,
    write_jsonl,
)
from src.gepa_official_runner import load_official_aime_dataset
from src.logging_utils import append_text, create_timestamp, write_json


def classify_error_type(error_text: str | None) -> str:
    if not error_text:
        return "ok"
    text = str(error_text).lower()
    if "rate limit" in text or "ratelimit" in text or "429" in text:
        return "rate limit"
    if "timeout" in text or "timed out" in text or "readtimeout" in text:
        return "timeout"
    if "authentication" in text or "auth" in text or "401" in text:
        return "auth"
    if "billing" in text or "insufficient_quota" in text or "quota" in text or "balance" in text:
        return "billing"
    if "bad request" in text or "badrequesterror" in text or "400" in text or "invalid_request_error" in text:
        return "bad request"
    if "provider" in text or "no attribute 'choices'" in text:
        return "provider returned error"
    return "other"


def build_error_diagnostic(records: list[dict[str, object]]) -> dict[str, object]:
    errors = [record for record in records if record.get("error")]
    by_prompt_version: dict[str, int] = {}
    by_error_type: dict[str, int] = {}
    by_error_text: dict[str, int] = {}

    for record in errors:
        prompt_version = str(record["prompt_version"])
        error_text = str(record["error"])
        error_type = classify_error_type(error_text)
        by_prompt_version[prompt_version] = by_prompt_version.get(prompt_version, 0) + 1
        by_error_type[error_type] = by_error_type.get(error_type, 0) + 1
        by_error_text[error_text] = by_error_text.get(error_text, 0) + 1

    primary_error_type = max(by_error_type.items(), key=lambda item: item[1])[0] if by_error_type else "none"
    return {
        "error_total": len(errors),
        "by_prompt_version": by_prompt_version,
        "by_error_type": by_error_type,
        "by_error_text": by_error_text,
        "primary_error_type": primary_error_type,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="评估已保存的 seed / optimized prompt。")
    parser.add_argument("--run-dir", required=True, help="运行目录，例如 outputs/gepa_aime_pilot/<timestamp>")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_EVAL_BATCH_SIZE, help="评估批大小。")
    parser.add_argument("--limit", type=int, default=None, help="仅评估前 N 个样本，用于小规模测试。")
    parser.add_argument("--resume", action="store_true", help="基于已有 per_example_eval.jsonl 断点续跑。")
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="显式重试已有失败记录。当前 resume 默认只跳过成功记录。",
    )
    parser.add_argument("--max-retries", type=int, default=0, help="单个批次失败后的最大重试次数。")
    parser.add_argument(
        "--retry-sleep-seconds",
        type=float,
        default=2.0,
        help="批次重试前的等待秒数。",
    )
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        raise FileNotFoundError(f"运行目录不存在：{run_dir}")
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit 必须是大于 0 的整数。")
    if args.max_retries < 0:
        raise ValueError("--max-retries 不能小于 0。")
    if args.retry_sleep_seconds < 0:
        raise ValueError("--retry-sleep-seconds 不能小于 0。")

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

    if args.limit is not None:
        dataset = dataset[: args.limit]

    per_example_path = run_dir / "per_example_eval.jsonl"
    existing_records = read_jsonl(per_example_path) if args.resume else []
    if not args.resume and per_example_path.exists():
        per_example_path.unlink()

    seed_success_records, seed_failed_records = split_effective_records(existing_records, prompt_version="seed")
    optimized_success_records, optimized_failed_records = split_effective_records(
        existing_records,
        prompt_version="optimized",
    )

    seed_records, seed_summary = evaluate_candidate(
        dataset=dataset,
        candidate=seed_candidate,
        prompt_version="seed",
        split_name=split_name,
        task_model=config.task_model,
        api_key=config.api_key,
        api_base=config.api_base,
        batch_size=args.batch_size,
        existing_prompt_records=seed_success_records,
        checkpoint_path=per_example_path,
        max_retries=args.max_retries,
        retry_sleep_seconds=args.retry_sleep_seconds,
    )
    optimized_records, optimized_summary = evaluate_candidate(
        dataset=dataset,
        candidate=optimized_candidate,
        prompt_version="optimized",
        split_name=split_name,
        task_model=config.task_model,
        api_key=config.api_key,
        api_base=config.api_base,
        batch_size=args.batch_size,
        existing_prompt_records=optimized_success_records,
        checkpoint_path=per_example_path,
        max_retries=args.max_retries,
        retry_sleep_seconds=args.retry_sleep_seconds,
    )

    all_records = normalize_records(seed_records + optimized_records)
    write_jsonl(per_example_path, all_records)

    diagnostic = build_error_diagnostic(all_records)
    write_json(run_dir / "saved_prompt_eval_diagnostic.json", diagnostic)

    score_delta = optimized_summary["average_score"] - seed_summary["average_score"]
    valid_for_performance_claim = (
        seed_summary["num_errors"] == 0
        and optimized_summary["num_errors"] == 0
        and seed_summary["evaluated_sample_count"] == len(dataset)
        and optimized_summary["evaluated_sample_count"] == len(dataset)
        and args.limit is None
    )
    summary = {
        "split": split_name,
        "split_label": split_label,
        "eval_model": config.task_model,
        "eval_timestamp": eval_timestamp,
        "evaluated_sample_count": seed_summary["evaluated_sample_count"],
        "requested_sample_count": len(dataset),
        "batch_size": args.batch_size,
        "limit": args.limit,
        "resume": args.resume,
        "retry_failed": args.retry_failed,
        "max_retries": args.max_retries,
        "retry_sleep_seconds": args.retry_sleep_seconds,
        "seed_prompt_score": seed_summary["average_score"],
        "optimized_prompt_score": optimized_summary["average_score"],
        "score_delta": score_delta,
        "valid_for_performance_claim": valid_for_performance_claim,
        "error_diagnostic": diagnostic,
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
        f"- batch_size: {args.batch_size}\n"
        f"- limit: {args.limit}\n"
        f"- resume: {args.resume}\n"
        f"- retry_failed: {args.retry_failed}\n"
        f"- max_retries: {args.max_retries}\n"
        f"- retry_sleep_seconds: {args.retry_sleep_seconds}\n"
        f"- resume_skips_success_only: {args.resume}\n"
        f"- previous_seed_failed_records: {len(seed_failed_records)}\n"
        f"- previous_optimized_failed_records: {len(optimized_failed_records)}\n"
        f"- seed_prompt_score: {seed_summary['average_score']}\n"
        f"- optimized_prompt_score: {optimized_summary['average_score']}\n"
        f"- score_delta: {score_delta}\n"
        f"- valid_for_performance_claim: {valid_for_performance_claim}\n",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
