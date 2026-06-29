import threading
import time
from datetime import datetime, timezone

from app.kernel.compute.ablation_harness import AblationHarness, AblationRun
from app.kernel.data_processing.incremental_fingerprint import IncrementalFingerprintEngine
from app.kernel.local.ollama import OllamaContextBlock, OllamaContextCache


def test_incremental_fingerprint_rebuilds_for_dependency_test_and_deletion(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "tests").mkdir()
    target = tmp_path / "app/target.py"
    dependency = tmp_path / "app/dependency.py"
    test_file = tmp_path / "tests/test_target.py"
    target.write_text("def value():\n    return 1\n")
    dependency.write_text("LIMIT = 1\n")
    test_file.write_text("def test_value():\n    assert True\n")
    engine = IncrementalFingerprintEngine(tmp_path, tmp_path / "state.json")
    kwargs = {
        "target_paths": ["app/target.py"],
        "dependency_paths": ["app/dependency.py"],
        "test_paths": ["tests/test_target.py"],
    }

    first = engine.build_incremental(**kwargs)
    unchanged = engine.build_incremental(**kwargs)
    dependency.write_text("LIMIT = 2\n")
    dependency_changed = engine.build_incremental(**kwargs)
    test_file.unlink()
    test_deleted = engine.build_incremental(**kwargs)

    assert first["beast_object_type"] == "capability_impact_fingerprint"
    assert unchanged["beast_object_type"] == "incremental_fingerprint_unchanged"
    assert dependency_changed["fingerprint_hash"] != first["fingerprint_hash"]
    assert test_deleted["fingerprint_hash"] != dependency_changed["fingerprint_hash"]
    assert test_deleted["tests"]["tests/test_target.py"]["exists"] is False


def test_ollama_context_cache_uses_identical_hashed_keys_and_lru():
    cache = OllamaContextCache(max_size=1)
    first = OllamaContextBlock(
        context_id="one",
        model="model",
        prompt_prefix="prefix",
        system_prompt="system",
        ollama_context=[1, 2],
    )
    second = OllamaContextBlock(
        context_id="two",
        model="model",
        prompt_prefix="other",
        system_prompt="system",
        ollama_context=[3],
    )

    cache.put(first)
    assert cache.get("model", "prefix", "system") is first
    cache.put(second)
    assert cache.get("model", "prefix", "system") is None
    assert cache.get("model", "other", "system") is second
    assert cache.evict("model", "other", "system") is True


class _ConcurrentHarness(AblationHarness):
    def __init__(self, tmp_path):
        super().__init__(repo_root=tmp_path)
        self.active = 0
        self.max_active = 0
        self.probe_lock = threading.Lock()

    def run_ablation(self, candidate_name, task_class, transform_type, **kwargs):
        with self.probe_lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.05)
        run = AblationRun(
            run_id=f"run-{len(self.runs)}",
            candidate_name=candidate_name,
            task_class=task_class,
            transform_type=transform_type,
            visible_tests_passed=1,
            visible_tests_total=1,
            hidden_tests_passed=1,
            hidden_tests_total=1,
            rollback_success=True,
            scope_checks_passed=True,
            security_checks_passed=True,
            behavior_preserved=True,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        with self._record_lock:
            self.runs.append(run)
        with self.probe_lock:
            self.active -= 1
        return run


def test_ablation_batch_really_runs_with_bounded_concurrency(tmp_path):
    harness = _ConcurrentHarness(tmp_path)
    reports = harness.run_batch(
        [{"candidate_name": "schema_validation", "task_class": "contract"}],
        runs_per_candidate=4,
        parallel=2,
    )
    assert harness.max_active == 2
    assert reports["schema_validation"].total_runs == 4
    assert reports["schema_validation"].meets_promotion_threshold is True


def test_ablation_missing_scope_security_tests_fails_closed(tmp_path, monkeypatch):
    harness = AblationHarness(repo_root=tmp_path)
    outcomes = iter([(1, 1, ""), (1, 1, ""), (1, 1, ""), (0, 0, "no tests")])
    monkeypatch.setattr(harness, "_run_pytest", lambda *args, **kwargs: next(outcomes))
    run = harness.run_ablation("candidate", "task", "deterministic")
    assert run.scope_checks_passed is False
    assert run.security_checks_passed is False
    assert run.behavior_preserved is False
