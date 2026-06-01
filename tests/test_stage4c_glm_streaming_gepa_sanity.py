from __future__ import annotations

import importlib.util
import json
import sys
import time
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "stage4c_run_glm_streaming_gepa_sanity.py"

SPEC = importlib.util.spec_from_file_location("stage4c_glm_streaming_gepa_sanity_script", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
stage4c_script = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = stage4c_script
SPEC.loader.exec_module(stage4c_script)


def _provider(api_key: str = "secret-key"):
    return stage4c_script.BASE.ProviderConfig(
        provider="glm",
        api_base="https://open.bigmodel.cn/api/paas/v4/",
        api_key_env="GLM_API_KEY",
        api_key=api_key,
        model="glm-4.7",
        litellm_provider_string=None,
    )


def _dataset_payload():
    return {
        "trainset": [{"input": "q1", "answer": "### 1"}],
        "valset": [{"input": "q2", "answer": "### 2"}],
        "testset_available": False,
        "dataset_source": "fake-dataset",
        "adaptation_notes": ["fake-note"],
        "trainset_size": 1,
        "valset_size_full": 1,
        "diagnostic_val_limit": 1,
        "valset_size_used": 1,
    }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_build_arm_specs_default_and_disabled() -> None:
    specs = stage4c_script.build_arm_specs(["disabled"])
    assert [item.thinking_type for item in specs] == ["disabled"]
    assert specs[0].first_token_timeout_seconds == 300


def test_effective_min_metric_calls_is_seed_eval_plus_one() -> None:
    payload = {
        "valset_size_used": 3,
    }
    semantics = stage4c_script.build_metric_call_semantics(payload, max_metric_calls=6)
    assert semantics["seed_full_eval_metric_calls"] == 3
    assert semantics["effective_min_metric_calls"] == 4
    assert semantics["requested_budget_reaches_loop_entry"] is True


def test_patch_litellm_for_streaming_restores_functions() -> None:
    fake_module = SimpleNamespace(
        completion=lambda **kwargs: "orig-completion",
        batch_completion=lambda **kwargs: "orig-batch",
    )
    original_completion = fake_module.completion
    original_batch = fake_module.batch_completion

    bridge = stage4c_script.StreamingLitellmBridge(
        provider_config=_provider(),
        arm_spec=stage4c_script.build_arm_specs(["default"])[0],
        arm_dir=PROJECT_ROOT / "outputs" / "tmp-stage4c-test",
        sleep_between_requests=0.0,
        max_retries=0,
    )

    import importlib

    real_import_module = importlib.import_module

    def fake_import_module(name: str):
        if name == "litellm":
            return fake_module
        return real_import_module(name)

    stage4c_script.importlib.import_module = fake_import_module
    try:
        with stage4c_script.patch_litellm_for_streaming(bridge):
            assert fake_module.completion == bridge.completion
            assert fake_module.batch_completion == bridge.batch_completion
        assert fake_module.completion is original_completion
        assert fake_module.batch_completion is original_batch
    finally:
        stage4c_script.importlib.import_module = real_import_module


def test_execute_thinking_arm_pre_health_failure_blocks_optimize(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_health_check(**kwargs):
        calls.append(kwargs["phase"])
        return {
            "status": "timeout",
            "content_exact_ok": False,
            "error_type": "FirstTokenTimeout",
            "error_message_sanitized": "too slow",
        }

    monkeypatch.setattr(stage4c_script, "execute_health_check", fake_health_check)

    result = stage4c_script.execute_thinking_arm(
        provider_config=_provider(),
        arm_spec=stage4c_script.build_arm_specs(["default"])[0],
        dataset_payload=_dataset_payload(),
        seed_prompt_name="strong_format",
        max_metric_calls=1,
        sleep_between_requests=0.0,
        max_retries=0,
        arm_dir=tmp_path / "arm-default",
        paired_thinking=False,
    )

    assert calls == ["before"]
    assert result["status"] == "blocked_by_health_check"
    assert result["optimize_called"] is False
    assert result["optimization_loop_entered"] is False
    assert result["effective_min_metric_calls"] == 2
    assert (tmp_path / "arm-default" / "arm_result.json").exists()


def test_execute_streaming_request_classifies_first_token_timeout(monkeypatch, tmp_path: Path) -> None:
    class _SlowStream:
        def __init__(self) -> None:
            self.response = SimpleNamespace(status_code=200)

        def __iter__(self):
            time.sleep(0.05)
            if False:
                yield None

        def close(self) -> None:
            return None

    class _ChatCompletions:
        def create(self, **kwargs):
            return _SlowStream()

    class _Chat:
        def __init__(self) -> None:
            self.completions = _ChatCompletions()

    class _FakeClient:
        def __init__(self, **kwargs) -> None:
            self.chat = _Chat()

    monkeypatch.setattr(stage4c_script, "OpenAI", _FakeClient)

    response, record = stage4c_script.execute_streaming_request(
        provider_config=_provider(),
        arm_spec=stage4c_script.ThinkingArmSpec(
            thinking_type="default",
            sdk_timeout_seconds=600,
            first_token_timeout_seconds=0,
            post_first_token_timeout_seconds=900,
            application_wall_clock_timeout_seconds=600,
            emergency_guard_timeout_seconds=600,
        ),
        messages=[{"role": "user", "content": "Return exactly: OK"}],
        request_role="health_before",
        request_index=1,
        arm_dir=tmp_path,
    )

    assert record["status"] == "timeout"
    assert record["error_type"] == "FirstTokenTimeout"
    assert record["timeout_source"] == "first_token_guard"
    assert record["content_nonempty"] is False


def test_main_dry_run_does_not_call_execute_and_does_not_leak_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(stage4c_script, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("GLM_API_KEY", "top-secret-glm-key")
    monkeypatch.setattr(stage4c_script, "build_dataset_payload", lambda limit: _dataset_payload())

    def fail_if_execute_called(**kwargs):
        raise AssertionError("dry-run 不应触发真实 execute")

    monkeypatch.setattr(stage4c_script, "run_execute", fail_if_execute_called)
    report_path = tmp_path / "reports" / "stage4c_glm_streaming_gepa_sanity_result.md"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stage4c_run_glm_streaming_gepa_sanity.py",
            "--streaming",
            "--report-path",
            str(report_path.relative_to(tmp_path)).replace("\\", "/"),
        ],
    )

    stage4c_script.main()

    output_root = tmp_path / "outputs" / "stage4c_glm_streaming_gepa_sanity"
    run_dirs = sorted(output_root.iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    report_text = _read_text(report_path)
    paired_results = json.loads(_read_text(run_dir / "paired_results.json"))
    run_summary = json.loads(_read_text(run_dir / "run_summary.json"))

    assert paired_results["diagnostic_only"] is True
    assert paired_results["single_thinking_diagnostic"] is True
    assert run_summary["not_model_ranking"] is True
    assert "top-secret-glm-key" not in report_text
    for artifact in (
        run_dir / "input_snapshot.json",
        run_dir / "paired_results.json",
        run_dir / "run_summary.json",
        run_dir / "failure_cases.json",
    ):
        assert "top-secret-glm-key" not in _read_text(artifact)


def test_main_execute_calls_run_execute_in_disabled_only_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(stage4c_script, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("GLM_API_KEY", "secret-key")
    monkeypatch.setattr(stage4c_script, "build_dataset_payload", lambda limit: _dataset_payload())
    observed: dict[str, object] = {}

    def fake_run_execute(**kwargs):
        observed["thinking_types"] = [item.thinking_type for item in kwargs["arm_specs"]]
        observed["paired_thinking"] = kwargs["paired_thinking"]
        return [
            {
                "thinking_type": "disabled",
                "status": "ok",
                "optimize_called": True,
                "optimize_completed": True,
                "optimization_loop_entered": True,
                "optimization_iterations_started": 1,
                "effective_min_metric_calls": 2,
                "health_before": {"status": "ok"},
                "health_after": {"status": "ok"},
                "gepa_result_summary": {"total_metric_calls": 2},
                "request_summary": {"request_count": 2, "timeout_count": 0},
                **stage4c_script.build_diagnostic_flags(paired_thinking=False),
            },
        ]

    monkeypatch.setattr(stage4c_script, "run_execute", fake_run_execute)
    report_path = tmp_path / "reports" / "stage4c_glm_streaming_gepa_sanity_result.md"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stage4c_run_glm_streaming_gepa_sanity.py",
            "--streaming",
            "--execute",
            "--report-path",
            str(report_path.relative_to(tmp_path)).replace("\\", "/"),
        ],
    )

    stage4c_script.main()

    assert observed["thinking_types"] == ["disabled"]
    assert observed["paired_thinking"] is False
    assert "disabled" in _read_text(report_path)
    assert "seed-evaluation sanity" in _read_text(report_path)


def test_main_execute_calls_run_execute_in_paired_order_when_requested(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(stage4c_script, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("GLM_API_KEY", "secret-key")
    monkeypatch.setattr(stage4c_script, "build_dataset_payload", lambda limit: _dataset_payload())
    observed: dict[str, object] = {}

    def fake_run_execute(**kwargs):
        observed["thinking_types"] = [item.thinking_type for item in kwargs["arm_specs"]]
        observed["paired_thinking"] = kwargs["paired_thinking"]
        return []

    monkeypatch.setattr(stage4c_script, "run_execute", fake_run_execute)
    report_path = tmp_path / "reports" / "stage4c_glm_streaming_gepa_sanity_result.md"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stage4c_run_glm_streaming_gepa_sanity.py",
            "--paired-thinking-diagnostic",
            "--thinking-types",
            "default",
            "disabled",
            "--streaming",
            "--execute",
            "--report-path",
            str(report_path.relative_to(tmp_path)).replace("\\", "/"),
        ],
    )

    stage4c_script.main()

    assert observed["thinking_types"] == ["default", "disabled"]
    assert observed["paired_thinking"] is True


def test_arm_worker_reconstructs_provider_config_with_properties(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_execute_thinking_arm(**kwargs):
        provider_config = kwargs["provider_config"]
        captured["provider_type"] = type(provider_config).__name__
        captured["api_base_present"] = provider_config.api_base_present
        return {"thinking_type": "default", "status": "ok"}

    monkeypatch.setattr(stage4c_script, "execute_thinking_arm", fake_execute_thinking_arm)

    class _Queue:
        def __init__(self) -> None:
            self.payload = None

        def put(self, value):
            self.payload = value

    queue = _Queue()
    stage4c_script._arm_worker(
        queue,
        {
            "provider_config": {
                "provider": "glm",
                "api_base": "https://open.bigmodel.cn/api/paas/v4/",
                "api_key_env": "GLM_API_KEY",
                "api_key": "secret-key",
                "model": "glm-4.7",
                "litellm_provider_string": None,
            },
            "arm_spec": {
                "thinking_type": "default",
                "sdk_timeout_seconds": 1800,
                "first_token_timeout_seconds": 1800,
                "post_first_token_timeout_seconds": 900,
                "application_wall_clock_timeout_seconds": 2700,
                "emergency_guard_timeout_seconds": 3600,
            },
            "dataset_payload": _dataset_payload(),
            "seed_prompt_name": "strong_format",
            "max_metric_calls": 1,
            "sleep_between_requests": 0.0,
            "max_retries": 0,
            "arm_dir": str(tmp_path / "arm-default"),
            "paired_thinking": False,
        },
    )

    assert captured["provider_type"] == "ProviderConfig"
    assert captured["api_base_present"] is True
    assert queue.payload == {"status": "ok", "result": {"thinking_type": "default", "status": "ok"}}


def test_script_source_targets_glm_streaming_gepa_sanity() -> None:
    source = _read_text(SCRIPT_PATH)
    assert "gepa.optimize" in source
    assert "optimization_loop_entered" in source
    assert '"mimo"' not in source


def test_mock_execute_thinking_arm_marks_loop_entry_for_metric_calls_6_and_9(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        stage4c_script,
        "execute_health_check",
        lambda **kwargs: {"status": "ok", "content_exact_ok": True},
    )
    monkeypatch.setattr(stage4c_script, "patch_litellm_for_streaming", lambda bridge: nullcontext())
    monkeypatch.setattr(stage4c_script, "temporary_openai_compatible_env", lambda **kwargs: nullcontext())

    class _FakeResult:
        best_idx = 0
        val_aggregate_scores = [0.0]
        total_metric_calls = 6
        num_candidates = 1
        num_val_instances = 3
        num_full_val_evals = 1

    def fake_optimize(**kwargs):
        callbacks = kwargs.get("callbacks") or []
        for callback in callbacks:
            if hasattr(callback, "on_optimization_start"):
                callback.on_optimization_start({"trainset_size": 1, "valset_size": len(kwargs["valset"]), "config": {}})
            if kwargs["max_metric_calls"] > len(kwargs["valset"]) and hasattr(callback, "on_iteration_start"):
                callback.on_iteration_start({"iteration": 1, "state": None})
            if hasattr(callback, "on_optimization_end"):
                callback.on_optimization_end({"best_candidate_idx": 0, "total_iterations": 1, "total_metric_calls": kwargs["max_metric_calls"], "final_state": None})
        return _FakeResult()

    monkeypatch.setitem(sys.modules, "gepa", SimpleNamespace(optimize=fake_optimize))

    dataset_payload = {
        "trainset": [{"input": "q1", "answer": "### 1"}],
        "valset": [
            {"input": "q2", "answer": "### 2"},
            {"input": "q3", "answer": "### 3"},
            {"input": "q4", "answer": "### 4"},
        ],
        "testset_available": False,
        "dataset_source": "fake-dataset",
        "adaptation_notes": ["fake-note"],
        "trainset_size": 1,
        "valset_size_full": 3,
        "diagnostic_val_limit": 3,
        "valset_size_used": 3,
    }

    for max_metric_calls in (6, 9):
        result = stage4c_script.execute_thinking_arm(
            provider_config=_provider(),
            arm_spec=stage4c_script.build_arm_specs(["disabled"])[0],
            dataset_payload=dataset_payload,
            seed_prompt_name="strong_format",
            max_metric_calls=max_metric_calls,
            sleep_between_requests=0.0,
            max_retries=0,
            arm_dir=tmp_path / f"arm-disabled-{max_metric_calls}",
            paired_thinking=False,
        )
        assert result["optimization_loop_entered"] is True
        assert result["optimization_iterations_started"] == 1
        assert result["effective_min_metric_calls"] == 4
        assert result["gepa_budget_semantics"]["requested_budget_reaches_loop_entry"] is True
