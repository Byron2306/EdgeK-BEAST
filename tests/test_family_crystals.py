"""Multi-family coding crystals: reviewed resolvers, replay, composites, registry and memfd capsule (offline)."""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

import pytest

from app.kernel.compute import family_crystals as fc
from app.kernel.compute.coding_crystals import coding_catalog_digest

ROOT = Path(__file__).resolve().parents[1]
V1_CATALOG = "sha256:41dec18fd131eb4dfd4c5d351dcb0f5427a4cb08cafb648b712e549300e65b92"


def _tasks():
    spec = importlib.util.spec_from_file_location("gauntlet_large_tasks", ROOT / "scripts" / "gauntlet_large_tasks.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


T = _tasks()
TASKS = T.all_tasks()


def make(tmp: Path, name: str) -> Path:
    root = tmp / name / "repo"
    for rel, text in TASKS[name]["files"].items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return root


def crystal(family: str) -> fc.FamilyCrystal:
    return fc.FamilyCrystal(crystal_id="", task_family=family, steps=fc.recipe([family]), catalog_digest=fc.catalog_digest(),
                            source_run_id="t", source_envelope_digest="sha256:" + "1" * 64).sealed()


def params(name):
    return {"implementation_target": TASKS[name]["target"], "verify_command": TASKS[name]["verify"]}


def hidden_passes(worktree: Path, name: str) -> bool:
    for rel, text in TASKS[name]["hidden"].items():
        (worktree / rel).write_text(text)
    return fc.run_verify(TASKS[name]["hidden_verify"], worktree)["returncode"] == 0


def test_v1_catalog_untouched_and_families_catalog_separate():
    assert coding_catalog_digest() == V1_CATALOG
    assert fc.catalog_digest() != V1_CATALOG
    assert not fc.family_crystals_enabled({})


@pytest.mark.parametrize("family", T.FAMILY_ORDER)
def test_family_resolver_replays_cold_heldout_and_warm_and_hidden_intent_holds(tmp_path, family):
    c = crystal(family)
    names = [n for n, t in TASKS.items() if t["family"] == family and t["role"] in {"cold", "heldout", "warm"}]
    assert len(names) == 6
    for name in names:
        root = make(tmp_path, name)
        assert fc.run_verify(TASKS[name]["verify"], root)["returncode"] != 0
        out = fc.replay_family(c, params(name), root, root.parent / "wt")
        assert out["ok"], (name, out["trace"][-1])
        assert out["model_calls"] == 0
        assert hidden_passes(root.parent / "wt", name), name


@pytest.mark.parametrize("family", T.FAMILY_ORDER)
def test_near_miss_is_not_resolvable(tmp_path, family):
    name = f"{T.PREFIX[family]}-near"
    root = make(tmp_path, name)
    out = fc.replay_family(crystal(family), params(name), root, root.parent / "wt")
    assert out["ok"] is False


def test_decoy_resolves_but_verifier_refuses(tmp_path):
    root = make(tmp_path, "const-decoy")
    out = fc.replay_family(crystal("fix-config-constant"), params("const-decoy"), root, root.parent / "wt")
    assert out["ok"] is False and out["reason"] == "expectation_failed"
    assert out["trace"][-1]["expect"] == "pass"


def test_applicability_bands(tmp_path):
    c = crystal("fix-off-by-one")
    for name, band in (("obo-w1", 1.0), ("obo-near", 0.85), ("exc-w1", 0.45)):
        root = make(tmp_path, name)
        observed = fc.run_verify(TASKS[name]["verify"], root)
        assert fc.applicability(c, root, TASKS[name], observed)["similarity"] == band, name


def test_guard_never_wraps_not_implemented(tmp_path):
    root = make(tmp_path, "far-1")
    out = fc.replay_family(crystal("fix-unhandled-exception"), params("far-1"), root, root.parent / "wt")
    assert out["ok"] is False and out["reason"] == "not_applicable"


def test_composite_chains_children_with_improve_step(tmp_path):
    obo, const = crystal("fix-off-by-one"), crystal("fix-config-constant")
    comp = fc.compose([obo, const], source_run_id="lattice")
    comp.validate()
    assert [s["expect"] for s in comp.steps if s["opcode"] == "worktree.verify"] == ["fail", "improve", "pass"]
    for name in ("dual-h1", "dual-w1"):
        root = make(tmp_path, name)
        assert fc.replay_family(const, params(name), root, root.parent / "single")["ok"] is False
        out = fc.replay_family(comp, params(name), root, root.parent / "wt")
        assert out["ok"], out["trace"][-1]
        assert hidden_passes(root.parent / "wt", name)


def test_tampered_crystal_and_unreviewed_steps_refused():
    c = crystal("fix-off-by-one")
    data = c.to_dict()
    data["steps"][3]["opcode"] = "repair.operator_swap"
    with pytest.raises(ValueError):
        fc.FamilyCrystal.from_dict(data)
    data = c.to_dict()
    data["task_family"] = "fix-logic-operator"
    with pytest.raises(ValueError):
        fc.FamilyCrystal.from_dict(data)


def test_registry_promotion_needs_operator_and_children_promoted(tmp_path):
    from app.kernel.compute.heldout_replay import HeldOutReplayGate

    reg = fc.FamilyRegistry(tmp_path / "f.sqlite3")
    a, b = crystal("fix-off-by-one"), crystal("fix-config-constant")
    reg.add_candidate(a)
    receipt = HeldOutReplayGate().evaluate(a.crystal_id, ["x", "y", "z"], lambda _v: True)
    with pytest.raises(PermissionError):
        reg.promote(a.crystal_id, receipt, approved_by="")
    reg.promote(a.crystal_id, receipt, approved_by="Byron")
    comp = fc.compose([a, b], source_run_id="l")
    with pytest.raises(LookupError):
        reg.add_candidate(comp)
    assert [x.crystal_id for x in reg.promoted()] == [a.crystal_id]


def test_rename_and_toolchain_capsule_replay_in_child(tmp_path, monkeypatch):
    from app.kernel.compute import crystal_memfd_capsule as cap

    monkeypatch.setenv("BEAST_CRYSTAL_CAPSULE", "1")
    for family, name in (("refactor-rename-symbol", "ren-w1"), ("toolchain-regenerate", "tool-w1")):
        c = crystal(family)
        root = make(tmp_path, name)
        ref = root.parent / "ref"
        assert fc.replay_family(c, params(name), root, ref)["ok"]
        pristine, after = fc.tree_digest(root), fc.tree_digest(ref)
        files = {k: v for k, v in after.items() if pristine.get(k) != v}
        post = {"verify_command": TASKS[name]["verify"], "implementation_target": TASKS[name]["target"],
                "tests_run": 2, "files_sha256_after": files}
        payload = cap.build_payload(c, registry_record_digest="sha256:x", promotion={}, parameters=params(name),
                                    postcondition=post, binding={"root": str(root), "worktree": str(root.parent / "cap")})
        manifest = cap.build_manifest(payload, crystal_id=c.crystal_id, crystal_digest=c.digest)
        fd, stats = cap.seal_capsule(manifest, payload)
        try:
            child = cap.handoff_to_replay_child(fd, manifest, admit_token="t")
        finally:
            os.close(fd)
        assert child["ok"], child.get("refused") or child["postcondition"]
        assert child["postcondition"]["checks"]["files_sha256_after"] is True
        assert child["network"]["inet_sockets"] == 0
        shutil.rmtree(root.parent)


def test_composite_authority_is_intersection_and_toolchain_child_cannot_widen():
    obo, const, tool = crystal("fix-off-by-one"), crystal("fix-config-constant"), crystal("toolchain-regenerate")
    comp = fc.compose([obo, const], source_run_id="l")
    assert set(comp.authority) == fc.recipe_authority(["fix-off-by-one"]) & fc.recipe_authority(["fix-config-constant"])
    with pytest.raises(ValueError):
        fc.compose([obo, tool], source_run_id="l").validate()  # run_declared not in the obo child's authority
    data = comp.to_dict()
    data["authority"] = sorted(data["authority"] + ["worktree.run_declared_tool"])
    with pytest.raises(ValueError):
        fc.FamilyCrystal.from_dict(data)


def _promote(reg, c):
    from app.kernel.compute.heldout_replay import HeldOutReplayGate

    reg.add_candidate(c)
    reg.promote(c.crystal_id, HeldOutReplayGate().evaluate(c.crystal_id, ["a", "b", "c"], lambda _v: True), approved_by="Byron")


def _fresh(tmp_path):
    fresh = T.fresh_lattice_tasks(7)
    TASKS.update(fresh)
    return {t["role"] + ":" + t["family"]: n for n, t in fresh.items()}


def test_discovery_selects_lattice_only_for_chained_workload(tmp_path):
    reg = fc.FamilyRegistry(tmp_path / "f.sqlite3")
    obo, const, op = crystal("fix-off-by-one"), crystal("fix-config-constant"), crystal("fix-logic-operator")
    for c in (obo, const, op):
        _promote(reg, c)
    comp = fc.compose([obo, const], source_run_id="l")
    _promote(reg, comp)
    names = _fresh(tmp_path)
    dual, single, diff = names["fresh:fresh-lattice"], names["fresh:fresh-single"], names["fresh:fresh-lattice-diff"]
    for name, expect_id, expect_sim in ((dual, comp.crystal_id, 1.0), (single, const.crystal_id, 1.0)):
        root = make(tmp_path, name)
        ranked = fc.discover(reg, root, TASKS[name], fc.run_verify(TASKS[name]["verify"], root))
        assert (ranked[0]["crystal_id"], ranked[0]["similarity"]) == (expect_id, expect_sim), name
    root = make(tmp_path, diff)
    ranked = fc.discover(reg, root, TASKS[diff], fc.run_verify(TASKS[diff]["verify"], root))
    assert ranked[0]["similarity"] < 0.95  # second capability differs: no exact-band lattice proposal


def test_lattice_stages_replay_from_separate_sealed_capsules(tmp_path, monkeypatch):
    from app.kernel.compute import crystal_memfd_capsule as cap

    monkeypatch.setenv("BEAST_CRYSTAL_CAPSULE", "1")
    obo, const = crystal("fix-off-by-one"), crystal("fix-config-constant")
    comp = fc.compose([obo, const], source_run_id="l")
    name = _fresh(tmp_path)["fresh:fresh-lattice"]
    root = make(tmp_path, name)
    src = root
    for index, child in enumerate((obo, const)):
        wt = root.parent / f"stage{index}"
        last = index == 1
        post = {"verify_command": TASKS[name]["verify"], "implementation_target": TASKS[name]["target"], "tests_run": 2,
                "expect_returncode": 0 if last else 1}
        payload = cap.build_payload(child, registry_record_digest="sha256:x", promotion={},
                                    parameters={**params(name), "lattice_stage": {"composite": comp.to_dict(), "index": index}},
                                    postcondition=post, binding={"root": str(src), "worktree": str(wt)})
        manifest = cap.build_manifest(payload, crystal_id=child.crystal_id, crystal_digest=child.digest)
        fd, _ = cap.seal_capsule(manifest, payload)
        try:
            out = cap.handoff_to_replay_child(fd, manifest, admit_token="t")
        finally:
            os.close(fd)
        assert out["ok"], out.get("refused") or out["replay"]["trace"][-1]
        assert out["lattice_stage"] == {"composite_id": comp.crystal_id, "index": index}
        src = wt
    assert hidden_passes(src, name)
    with pytest.raises(PermissionError):
        fc.replay_stage(comp, const, 0, params(name), root, root.parent / "bad")  # wrong child for stage 0


def test_guard_applicability_uses_scratch_tracebacks(tmp_path):
    c = crystal("fix-unhandled-exception")
    root = make(tmp_path, "exc-w1")
    observed = fc.run_verify(TASKS["exc-w1"]["verify"], root)
    assert fc.applicability(c, root, TASKS["exc-w1"], observed)["similarity"] == 1.0


def test_hard_lattice_rename_plus_guard_on_multifile_repo(tmp_path):
    ren, guard = crystal("refactor-rename-symbol"), crystal("fix-unhandled-exception")
    comp = fc.compose([ren, guard], source_run_id="lattice2")
    comp.validate()
    names = [n for n, t in TASKS.items() if t["family"] == "composite-refguard"]
    assert len(names) >= 4
    for name in names:
        root = make(tmp_path, name)
        assert len([p for p in TASKS[name]["files"] if p.endswith(".py") and "test_" not in p]) >= 4  # multi-file
        assert fc.run_verify(TASKS[name]["verify"], root)["failures"] == 2
        for single in (ren, guard):
            assert fc.replay_family(single, params(name), root, root.parent / f"s-{single.task_family}")["ok"] is False
        out = fc.replay_family(comp, params(name), root, root.parent / "wt")
        assert out["ok"], (name, out["trace"][-1])
        assert hidden_passes(root.parent / "wt", name), name


def test_hard_lattice_discovery_and_negatives_on_fresh_tasks(tmp_path):
    reg = fc.FamilyRegistry(tmp_path / "f.sqlite3")
    ren, guard, op = crystal("refactor-rename-symbol"), crystal("fix-unhandled-exception"), crystal("fix-logic-operator")
    for c in (ren, guard, op):
        _promote(reg, c)
    comp = fc.compose([ren, guard], source_run_id="l2")
    _promote(reg, comp)
    fresh = T.fresh_lattice2_tasks(11)
    TASKS.update(fresh)
    by = {t["family"]: n for n, t in fresh.items()}
    dual, single, diff = by["fresh-lattice2"], by["fresh-single2"], by["fresh-lattice2-diff"]
    for name, expect_id in ((dual, comp.crystal_id), (single, ren.crystal_id)):
        root = make(tmp_path, name)
        ranked = fc.discover(reg, root, TASKS[name], fc.run_verify(TASKS[name]["verify"], root))
        assert (ranked[0]["crystal_id"], ranked[0]["similarity"]) == (expect_id, 1.0), name
    root = make(tmp_path, diff)
    ranked = fc.discover(reg, root, TASKS[diff], fc.run_verify(TASKS[diff]["verify"], root))
    top = ranked[0]
    if top["crystal_id"] == comp.crystal_id and top["similarity"] >= 0.95:
        assert fc.replay_family(comp, params(diff), root, root.parent / "wt")["ok"] is False  # must fall back, never accept


def test_nested_family_composite_preserves_graph_and_flattens_execution():
    from app.kernel.compute.family_crystals import (
        FamilyCrystal,
        catalog_digest,
        compose,
        recipe,
        recipe_authority,
    )

    def leaf(family, suffix):
        from app.kernel.compute.family_crystals import _digest
        return FamilyCrystal(
            crystal_id="",
            task_family=family,
            steps=recipe((family,)),
            catalog_digest=catalog_digest(),
            source_run_id=f"run-{suffix}",
            source_envelope_digest=_digest(["env", suffix]),
            expected_failures=1,
        ).sealed()

    a = leaf("fix-off-by-one", "a")
    b = leaf("fix-config-constant", "b")
    c = leaf("fix-logic-operator", "c")

    ab = compose([a, b], source_run_id="run-ab")
    abc = compose([ab, c], source_run_id="run-abc")

    assert ab.component_ids == (a.crystal_id, b.crystal_id)
    assert ab.component_families == (
        "fix-off-by-one",
        "fix-config-constant",
    )

    # Graph structure remains nested.
    assert abc.component_ids == (ab.crystal_id, c.crystal_id)

    # Execution semantics flatten into atomic capabilities.
    assert abc.component_families == (
        "fix-off-by-one",
        "fix-config-constant",
        "fix-logic-operator",
    )
    assert abc.expected_failures == 3
    assert abc.steps == recipe(abc.component_families)

    expected_authority = (
        set(ab.authority)
        & recipe_authority(("fix-logic-operator",))
    )
    assert set(abc.authority) == expected_authority

    abc.validate()


def test_nested_composite_can_execute_as_parent_lattice_stage():
    from app.kernel.compute.family_crystals import (
        FamilyCrystal,
        _digest,
        catalog_digest,
        compose,
        recipe,
        stage_steps,
    )

    def leaf(family, suffix):
        return FamilyCrystal(
            crystal_id="",
            task_family=family,
            steps=recipe((family,)),
            catalog_digest=catalog_digest(),
            source_run_id=f"run-{suffix}",
            source_envelope_digest=_digest(["env", suffix]),
            expected_failures=1,
        ).sealed()

    a = leaf("fix-off-by-one", "a")
    b = leaf("fix-config-constant", "b")
    c = leaf("fix-logic-operator", "c")

    ab = compose([a, b], source_run_id="run-ab")
    abc = compose([ab, c], source_run_id="run-abc")

    first = stage_steps(abc, ab, 0)
    second = stage_steps(abc, c, 1)

    first_verifiers = [
        step["expect"]
        for step in first
        if step["opcode"] == "worktree.verify"
    ]
    second_verifiers = [
        step["expect"]
        for step in second
        if step["opcode"] == "worktree.verify"
    ]

    # AB internally performs A then B, but because another parent capability
    # remains its terminal PASS becomes IMPROVE.
    assert first_verifiers == ["fail", "improve", "improve"]

    # C is the terminal parent stage.
    assert second_verifiers == ["fail", "pass"]


def test_lattice_topology_preserves_nested_graph(tmp_path):
    from app.kernel.compute.family_crystals import (
        FamilyCrystal,
        FamilyRegistry,
        _digest,
        catalog_digest,
        compose,
        lattice_topology,
        recipe,
    )
    from app.kernel.compute.heldout_replay import ReplayReceipt

    def leaf(family, suffix):
        return FamilyCrystal(
            crystal_id="",
            task_family=family,
            steps=recipe((family,)),
            catalog_digest=catalog_digest(),
            source_run_id=f"run-{suffix}",
            source_envelope_digest=_digest(["env", suffix]),
            expected_failures=1,
        ).sealed()

    def promote(registry, crystal):
        registry.add_candidate(crystal)
        registry.promote(
            crystal.crystal_id,
            ReplayReceipt(
                crystal.crystal_id,
                3,
                3,
                True,
                "heldout passed",
            ),
            approved_by="byron",
        )

    registry = FamilyRegistry(tmp_path / "families.sqlite3")

    a = leaf("fix-off-by-one", "a")
    b = leaf("fix-config-constant", "b")
    c = leaf("fix-logic-operator", "c")

    for crystal in (a, b, c):
        promote(registry, crystal)

    ab = compose([a, b], source_run_id="run-ab")
    promote(registry, ab)

    abc = compose([ab, c], source_run_id="run-abc")
    promote(registry, abc)

    graph = lattice_topology(registry, abc)

    assert graph["root"]["crystal_id"] == abc.crystal_id
    assert graph["root"]["children"][0]["crystal_id"] == ab.crystal_id
    assert graph["root"]["children"][0]["children"][0]["crystal_id"] == a.crystal_id
    assert graph["root"]["children"][0]["children"][1]["crystal_id"] == b.crystal_id
    assert graph["root"]["children"][1]["crystal_id"] == c.crystal_id

    assert [x["task_family"] for x in graph["leaves"]] == [
        "fix-off-by-one",
        "fix-config-constant",
        "fix-logic-operator",
    ]
    assert graph["leaf_count"] == 3
