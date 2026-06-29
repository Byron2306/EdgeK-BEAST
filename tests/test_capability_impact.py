from pathlib import Path

from app.kernel.capability.capability_impact import CapabilityImpactFingerprint


def _build(engine, root, confidence=0.9, policy="v1", schema="sha256:s1"):
    return engine.build(
        root,
        target_paths=["app/target.py"],
        dependency_paths=["app/dependency.py"],
        test_paths=["tests/test_target.py"],
        symbols={"app/target.py": ["transform"]},
        tool_schema_hashes=[schema],
        policy_version=policy,
        confidence=confidence,
    )


def _workspace(tmp_path: Path):
    (tmp_path / "app").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "app/target.py").write_text("def transform(value):\n    return value + 1\n")
    (tmp_path / "app/dependency.py").write_text("LIMIT = 3\n")
    (tmp_path / "tests/test_target.py").write_text("def test_target():\n    assert True\n")


def test_unchanged_impact_fingerprint_remains_active(tmp_path):
    _workspace(tmp_path)
    engine = CapabilityImpactFingerprint()
    previous = _build(engine, tmp_path)
    current = _build(engine, tmp_path)
    decision = engine.compare(previous, current)
    assert decision["state"] == "active"
    assert decision["reusable"] is True
    assert decision["confidence"] == 0.9


def test_comment_only_change_causes_small_decay_not_invalidation(tmp_path):
    _workspace(tmp_path)
    engine = CapabilityImpactFingerprint()
    previous = _build(engine, tmp_path)
    (tmp_path / "app/target.py").write_text("# comment\ndef transform(value):\n    return value + 1\n")
    decision = engine.compare(previous, _build(engine, tmp_path))
    assert decision["state"] == "active"
    assert decision["reusable"] is True
    assert decision["confidence"] == 0.882
    assert decision["nonsemantic_changes"]


def test_target_ast_change_requires_shadow_revalidation(tmp_path):
    _workspace(tmp_path)
    engine = CapabilityImpactFingerprint()
    previous = _build(engine, tmp_path)
    (tmp_path / "app/target.py").write_text("def transform(value):\n    return value + 2\n")
    decision = engine.compare(previous, _build(engine, tmp_path))
    assert decision["state"] == "shadow_revalidation"
    assert decision["reusable"] is False
    assert any("semantic_change" in item for item in decision["critical_changes"])


def test_dependency_test_schema_and_policy_changes_invalidate(tmp_path):
    _workspace(tmp_path)
    engine = CapabilityImpactFingerprint()
    previous = _build(engine, tmp_path)
    (tmp_path / "app/dependency.py").write_text("LIMIT = 4\n")
    (tmp_path / "tests/test_target.py").write_text("def test_target():\n    assert 1 == 1\n")
    current = _build(engine, tmp_path, policy="v2", schema="sha256:s2")
    decision = engine.compare(previous, current)
    assert decision["reusable"] is False
    assert "tool_schema_change" in decision["critical_changes"]
    assert "policy_version_change" in decision["critical_changes"]
    assert any("dependencies" in item for item in decision["critical_changes"])
    assert any("tests" in item for item in decision["critical_changes"])


def test_missing_target_and_path_escape_fail_closed(tmp_path):
    _workspace(tmp_path)
    engine = CapabilityImpactFingerprint()
    previous = _build(engine, tmp_path)
    (tmp_path / "app/target.py").unlink()
    decision = engine.compare(previous, _build(engine, tmp_path))
    assert decision["state"] == "shadow_revalidation"
    assert decision["reusable"] is False
    try:
        engine.build(tmp_path, target_paths=["../outside.py"])
    except ValueError:
        pass
    else:
        raise AssertionError("path escape should fail closed")
