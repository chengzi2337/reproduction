from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.logging_utils import create_timestamp, write_json, write_text


DEFAULT_VARIANT_CONFIG_PATH = PROJECT_ROOT / "configs" / "ifeval_prompt_transfer_variants.json"
DEFAULT_REPORT_JSON_PATH = PROJECT_ROOT / "reports" / "ifeval_prompt_transfer_preflight.json"
DEFAULT_REPORT_MD_PATH = PROJECT_ROOT / "reports" / "ifeval_prompt_transfer_preflight.md"
DEFAULT_DATASET_CANDIDATES = (
    PROJECT_ROOT / "data" / "ifeval.jsonl",
    PROJECT_ROOT / "data" / "ifeval.json",
    PROJECT_ROOT / "data" / "IFEval" / "input_data.jsonl",
    PROJECT_ROOT / "data" / "IFEval" / "ifeval.jsonl",
    PROJECT_ROOT / "datasets" / "ifeval.jsonl",
    PROJECT_ROOT / "datasets" / "ifeval.json",
)
REQUIRED_VARIANT_FIELDS = (
    "variant_id",
    "display_name",
    "source",
    "intended_hypothesis",
    "prompt_delta",
    "risk_notes",
)
CHECKER_MODULE_CANDIDATES = (
    "instruction_following_eval.evaluation_main",
    "ifeval.instruction_following_eval.evaluation_main",
    "eval.ifeval.evaluation_main",
    "lm_eval.tasks.ifeval.utils",
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


def _candidate_dataset_paths(dataset_path: Path | None) -> list[Path]:
    if dataset_path is not None:
        return [dataset_path]
    return list(DEFAULT_DATASET_CANDIDATES)


def _read_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if isinstance(payload, dict):
                samples.append(payload)
            if len(samples) >= limit:
                break
    return samples


def _read_json(path: Path, limit: int) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        values = payload.get("examples") or payload.get("data") or payload.get("samples") or []
    else:
        values = []
    return [item for item in values[:limit] if isinstance(item, dict)]


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
    preview_limit: int = 3,
) -> dict[str, Any]:
    checked_paths = _candidate_dataset_paths(dataset_path)
    existing_paths = [path for path in checked_paths if path.exists() and path.is_file()]
    if not existing_paths:
        return {
            "dataset_status": "dataset_missing",
            "dataset_path": None,
            "checked_paths": [path.as_posix() for path in checked_paths],
            "sample_count_detected": 0,
            "samples_preview": [],
            "repair_suggestion": "请把本地 IFEval JSONL/JSON 文件放入候选路径，或通过 --dataset-path 显式指定。",
        }

    selected_path = existing_paths[0]
    try:
        if selected_path.suffix.lower() == ".jsonl":
            raw_samples = _read_jsonl(selected_path, preview_limit + 1)
        elif selected_path.suffix.lower() == ".json":
            raw_samples = _read_json(selected_path, preview_limit + 1)
        else:
            return {
                "dataset_status": "dataset_unreadable",
                "dataset_path": selected_path.as_posix(),
                "checked_paths": [path.as_posix() for path in checked_paths],
                "sample_count_detected": 0,
                "samples_preview": [],
                "repair_suggestion": "当前 preflight 只支持 JSONL/JSON；请转换本地 IFEval 文件格式。",
            }
    except Exception as exc:
        return {
            "dataset_status": "dataset_unreadable",
            "dataset_path": selected_path.as_posix(),
            "checked_paths": [path.as_posix() for path in checked_paths],
            "sample_count_detected": 0,
            "samples_preview": [],
            "error_type": type(exc).__name__,
            "repair_suggestion": "请检查本地 IFEval 文件是否为 UTF-8 JSONL/JSON。",
        }

    preview = [
        _normalize_sample(sample, source_path=selected_path, index=index)
        for index, sample in enumerate(raw_samples[:preview_limit])
    ]
    return {
        "dataset_status": "dataset_available",
        "dataset_path": selected_path.as_posix(),
        "checked_paths": [path.as_posix() for path in checked_paths],
        "sample_count_detected": len(raw_samples),
        "samples_preview": preview,
        "repair_suggestion": None,
    }


def inspect_rule_checker() -> dict[str, Any]:
    for module_name in CHECKER_MODULE_CANDIDATES:
        try:
            spec = importlib.util.find_spec(module_name)
        except ModuleNotFoundError:
            spec = None
        if spec is None:
            continue
        return {
            "checker_status": "checker_importable",
            "checker_module": module_name,
            "llm_judge_enabled": False,
            "mock_prediction_probe": {
                "status": "not_executed",
                "reason": "preflight 只验证 rule-checker 模块可导入；真实函数适配在后续 runner 中实现。",
                "empty_prediction": "",
                "structured_result_contract": {
                    "prompt_level_passed": "bool",
                    "instruction_level_results": "list[dict]",
                    "failure_reasons": "list[string]",
                },
            },
            "repair_suggestion": None,
        }
    return {
        "checker_status": "checker_unavailable",
        "checker_module": None,
        "llm_judge_enabled": False,
        "mock_prediction_probe": {
            "status": "structured_stub",
            "empty_prediction": "",
            "structured_result": {
                "prompt_level_passed": False,
                "instruction_level_results": [],
                "failure_reasons": ["rule checker 依赖不可导入，未执行真实规则检查。"],
            },
        },
        "repair_suggestion": "请安装或接入本地 IFEval rule checker，并暴露可导入的规则评估模块；不要改成 LLM judge。",
    }


def build_preflight_result(
    *,
    variant_config_path: Path = DEFAULT_VARIANT_CONFIG_PATH,
    dataset_path: Path | None = None,
) -> dict[str, Any]:
    variants = load_variants(variant_config_path)
    dataset = load_ifeval_dataset(dataset_path)
    checker = inspect_rule_checker()
    blocked_reasons: list[str] = []
    if dataset["dataset_status"] != "dataset_available":
        blocked_reasons.append(dataset["dataset_status"])
    if checker["checker_status"] != "checker_importable":
        blocked_reasons.append(checker["checker_status"])
    return {
        "status": "ready" if not blocked_reasons else "blocked",
        "generated_at": create_timestamp(),
        "api_call_enabled": False,
        "full_budget_gepa_enabled": False,
        "dataset_status": dataset["dataset_status"],
        "checker_status": checker["checker_status"],
        "variant_count": len(variants),
        "variants": variants,
        "sample_count_detected": dataset["sample_count_detected"],
        "schema": {
            "ifeval_sample": sample_schema(),
            "prompt_variant": prompt_variant_schema(),
        },
        "dataset": dataset,
        "checker": checker,
        "next_real_run_entrypoint": (
            "python scripts/run_ifeval_prompt_transfer.py "
            "--enable-api-run --dataset-path <本地 IFEval 文件>"
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
            f"- dataset：{result['dataset'].get('repair_suggestion') or '当前无需修复。'}",
            f"- checker：{result['checker'].get('repair_suggestion') or '当前无需修复。'}",
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
    parser.add_argument("--dataset-path", default=None)
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON_PATH))
    parser.add_argument("--report-md", default=str(DEFAULT_REPORT_MD_PATH))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dataset_path = Path(args.dataset_path) if args.dataset_path else None
    result = build_preflight_result(
        variant_config_path=Path(args.variant_config),
        dataset_path=dataset_path,
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
