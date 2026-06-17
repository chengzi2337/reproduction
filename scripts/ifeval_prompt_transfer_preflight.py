from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ifeval_official_adapter import (
    import_official_modules,
    read_ifeval_samples,
    resolve_dataset_path,
    resolve_ifeval_root,
    run_checker_smoke,
)
from src.logging_utils import create_timestamp, write_json, write_text


DEFAULT_VARIANT_CONFIG_PATH = PROJECT_ROOT / "configs" / "ifeval_prompt_transfer_variants.json"
DEFAULT_REPORT_JSON_PATH = PROJECT_ROOT / "reports" / "ifeval_prompt_transfer_preflight.json"
DEFAULT_REPORT_MD_PATH = PROJECT_ROOT / "reports" / "ifeval_prompt_transfer_preflight.md"
DEFAULT_DATASET_CANDIDATES = (
    Path("data") / "ifeval.jsonl",
    Path("data") / "ifeval.json",
    Path("data") / "IFEval" / "input_data.jsonl",
    Path("data") / "IFEval" / "ifeval.jsonl",
    Path("datasets") / "ifeval.jsonl",
    Path("datasets") / "ifeval.json",
)
REQUIRED_VARIANT_FIELDS = (
    "variant_id",
    "display_name",
    "source",
    "intended_hypothesis",
    "prompt_delta",
    "risk_notes",
)
class IFEvalPromptTransferPreflightError(RuntimeError):
    """IFEval prompt-transfer preflight 配置错误。"""


def sample_schema() -> dict[str, Any]:
    return {
        "prompt": {
            "required": True,
            "type": "string",
            "description": "IFEval 原始用户指令文本。",
        },
        "instruction_id_list": {
            "required": True,
            "type": "list[string]",
            "description": "rule checker 使用的 IFEval 指令约束标识列表。",
        },
        "kwargs": {
            "required": True,
            "type": "list[dict] | dict",
            "description": "每条 instruction 对应的规则参数。",
        },
        "metadata": {
            "required": False,
            "type": "dict",
            "description": "本地样本来源、索引和原始字段等审计信息。",
        },
    }


def prompt_variant_schema() -> dict[str, Any]:
    return {
        field: {"required": True}
        for field in REQUIRED_VARIANT_FIELDS
    }


def load_variants(config_path: Path = DEFAULT_VARIANT_CONFIG_PATH) -> list[dict[str, Any]]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    variants = payload.get("variants")
    if not isinstance(variants, list):
        raise IFEvalPromptTransferPreflightError("variant 配置必须包含 `variants` 列表。")
    seen: set[str] = set()
    for index, variant in enumerate(variants):
        if not isinstance(variant, dict):
            raise IFEvalPromptTransferPreflightError(f"variant[{index}] 必须是对象。")
        missing = [field for field in REQUIRED_VARIANT_FIELDS if field not in variant]
        if missing:
            raise IFEvalPromptTransferPreflightError(
                f"variant[{index}] 缺少字段：{', '.join(missing)}。"
            )
        variant_id = str(variant["variant_id"])
        if variant_id in seen:
            raise IFEvalPromptTransferPreflightError(f"variant_id 重复：{variant_id}。")
        seen.add(variant_id)
    return variants


def _normalize_sample(sample: dict[str, Any], *, source_path: Path, index: int) -> dict[str, Any]:
    metadata = sample.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        "prompt": sample.get("prompt", ""),
        "instruction_id_list": sample.get("instruction_id_list", []),
        "kwargs": sample.get("kwargs", []),
        "metadata": {
            **metadata,
            "source_path": source_path.as_posix(),
            "source_index": index,
            "raw_fields": sorted(str(key) for key in sample.keys()),
        },
    }


def load_ifeval_dataset(
    dataset_path: Path | None = None,
    *,
    ifeval_root: Path | None = None,
    preview_limit: int = 3,
) -> dict[str, Any]:
    resolved = resolve_dataset_path(
        explicit_dataset_path=dataset_path,
        ifeval_root=ifeval_root,
        project_root=PROJECT_ROOT,
        fallback_candidates=DEFAULT_DATASET_CANDIDATES,
    )
    selected_path = Path(resolved["dataset_path"]) if resolved["dataset_path"] else None
    if selected_path is None:
        return {
            **resolved,
            "sample_count_detected": 0,
            "samples_preview": [],
        }
    try:
        raw_samples = read_ifeval_samples(selected_path, limit=preview_limit + 1)
    except Exception as exc:
        return {
            "dataset_status": "dataset_unreadable",
            "dataset_path": selected_path.as_posix(),
            "checked_paths": resolved["checked_paths"],
            "sample_count_detected": 0,
            "samples_preview": [],
            "error_type": type(exc).__name__,
            "repair_suggestion": "请检查本地 IFEval input_data.jsonl 是否为 UTF-8 JSONL 且包含官方字段。",
        }

    preview = [
        _normalize_sample(sample, source_path=selected_path, index=index)
        for index, sample in enumerate(raw_samples[:preview_limit])
    ]
    return {
        "dataset_status": "ok",
        "dataset_path": selected_path.as_posix(),
        "checked_paths": resolved["checked_paths"],
        "sample_count_detected": len(raw_samples),
        "samples_preview": preview,
        "repair_suggestion": None,
    }


def inspect_rule_checker(ifeval_root: Path | None = None) -> dict[str, Any]:
    checker = import_official_modules(ifeval_root)
    return {
        **checker,
        "llm_judge_enabled": False,
        "rule_checker_required": True,
    }


def build_preflight_result(
    *,
    variant_config_path: Path = DEFAULT_VARIANT_CONFIG_PATH,
    dataset_path: Path | None = None,
    ifeval_root: Path | None = None,
) -> dict[str, Any]:
    variants = load_variants(variant_config_path)
    root = resolve_ifeval_root(explicit_ifeval_root=ifeval_root, project_root=PROJECT_ROOT)
    root_path = Path(root["ifeval_root"]) if root["ifeval_root"] else None
    dataset = load_ifeval_dataset(dataset_path, ifeval_root=root_path)
    dataset_path_for_smoke = Path(dataset["dataset_path"]) if dataset.get("dataset_path") else None
    checker = inspect_rule_checker(root_path)
    smoke = run_checker_smoke(ifeval_root=root_path, dataset_path=dataset_path_for_smoke)
    blocked_reasons: list[str] = []
    if dataset["dataset_status"] != "ok":
        blocked_reasons.append(dataset["dataset_status"])
    if checker["checker_status"] != "ok":
        blocked_reasons.append(checker["checker_status"])
    if checker["checker_status"] == "ok" and smoke["checker_smoke_status"] != "ok":
        blocked_reasons.append("checker_smoke_failed")
    return {
        "status": "ready" if not blocked_reasons else "blocked",
        "generated_at": create_timestamp(),
        "api_call_enabled": False,
        "full_budget_gepa_enabled": False,
        "dataset_status": dataset["dataset_status"],
        "checker_status": checker["checker_status"],
        "checker_smoke_status": smoke["checker_smoke_status"],
        "checker_smoke_sample_count": smoke["checker_smoke_sample_count"],
        "checker_smoke_error": smoke["checker_smoke_error"],
        "prompt_level_accuracy_available": smoke["prompt_level_accuracy_available"],
        "instruction_level_accuracy_available": smoke["instruction_level_accuracy_available"],
        "variant_count": len(variants),
        "variants": variants,
        "sample_count_detected": dataset["sample_count_detected"],
        "schema": {
            "ifeval_sample": sample_schema(),
            "prompt_variant": prompt_variant_schema(),
        },
        "ifeval_root": root,
        "dataset": dataset,
        "checker": checker,
        "checker_smoke": smoke,
        "next_real_run_entrypoint": (
            "python scripts/run_ifeval_prompt_transfer.py "
            "--enable-api-run --ifeval-root <本地 instruction_following_eval>"
        ),
        "blocked_reasons": blocked_reasons,
    }


def render_markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# IFEval prompt-transfer preflight",
        "",
        "## 当前定位",
        "",
        "- 当前没有调用真实 API。",
        "- 当前只是 IFEval prompt-transfer 实验框架和 dry-run/preflight。",
        "- IFEval 评估口径必须使用 rule checker，不使用 LLM judge。",
        "- 后续真实运行必须通过单独入口 `scripts/run_ifeval_prompt_transfer.py` 显式启动。",
        "- 当前实验要回答的问题是：P2/MHC 是否可迁移为 hard instruction-following constraint-priority principle。",
        "- 本报告不是实验证据，不包含 IFEval 真实 API 运行结果。",
        "",
        "## 结构化状态",
        "",
        f"- status：`{result['status']}`",
        f"- api_call_enabled：`{str(result['api_call_enabled']).lower()}`",
        f"- full_budget_gepa_enabled：`{str(result['full_budget_gepa_enabled']).lower()}`",
        f"- dataset_status：`{result['dataset_status']}`",
        f"- checker_status：`{result['checker_status']}`",
        f"- checker_smoke_status：`{result['checker_smoke_status']}`",
        f"- checker_smoke_sample_count：`{result['checker_smoke_sample_count']}`",
        f"- prompt_level_accuracy_available：`{str(result['prompt_level_accuracy_available']).lower()}`",
        f"- instruction_level_accuracy_available：`{str(result['instruction_level_accuracy_available']).lower()}`",
        f"- variant_count：`{result['variant_count']}`",
        f"- sample_count_detected：`{result['sample_count_detected']}`",
        "",
        "## Prompt variants",
        "",
    ]
    for variant in result["variants"]:
        lines.append(
            f"- `{variant['variant_id']}` / {variant['display_name']}：{variant['intended_hypothesis']}"
        )
    lines.extend(
        [
            "",
            "## IFEval sample schema",
            "",
        ]
    )
    for field, meta in result["schema"]["ifeval_sample"].items():
        lines.append(
            f"- `{field}`：`{meta['type']}`；required=`{str(meta['required']).lower()}`；{meta['description']}"
        )
    lines.extend(
        [
            "",
            "## 阻断原因",
            "",
        ]
    )
    if result["blocked_reasons"]:
        lines.extend(f"- `{reason}`" for reason in result["blocked_reasons"])
    else:
        lines.append("- 无")
    lines.extend(
        [
            "",
            "## 修复建议",
            "",
            f"- ifeval_root：{result['ifeval_root'].get('repair_suggestion') or '当前无需修复。'}",
            f"- dataset：{result['dataset'].get('repair_suggestion') or '当前无需修复。'}",
            f"- checker：{result['checker'].get('repair_suggestion') or '当前无需修复。'}",
            "- 推荐命令：`python scripts/ifeval_prompt_transfer_preflight.py --ifeval-root external/google-research/instruction_following_eval`",
            "",
            "## 结论边界",
            "",
            "- 本阶段仍然不是 IFEval 实验结果。",
            "- 当前只证明官方数据和 checker 是否已接入。",
            "- 下一阶段才会运行 prompt-transfer API 评测。",
            "- IFEval 使用 rule checker，不使用 LLM judge。",
            "",
            "## 后续入口",
            "",
            f"- `{result['next_real_run_entrypoint']}`",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IFEval prompt-transfer preflight；默认不调用模型。")
    parser.add_argument("--variant-config", default=str(DEFAULT_VARIANT_CONFIG_PATH))
    parser.add_argument("--ifeval-root", default=None)
    parser.add_argument("--dataset-path", default=None)
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON_PATH))
    parser.add_argument("--report-md", default=str(DEFAULT_REPORT_MD_PATH))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dataset_path = Path(args.dataset_path) if args.dataset_path else None
    ifeval_root = Path(args.ifeval_root) if args.ifeval_root else None
    result = build_preflight_result(
        variant_config_path=Path(args.variant_config),
        dataset_path=dataset_path,
        ifeval_root=ifeval_root,
    )
    report_json_path = Path(args.report_json)
    report_md_path = Path(args.report_md)
    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report_md_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(report_json_path, result)
    write_text(report_md_path, render_markdown_report(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
