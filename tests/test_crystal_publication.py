"""D7: HF Xet publication of promoted coding crystals (fake hub, offline) and quarantined import."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent))

from crystal_fabric_support import HELD_OUT_VARIANTS, crystal_stack, run_learn, run_with_planner  # noqa: E402

from app.kernel.compute.coding_crystals import (  # noqa: E402
    CodingCrystalExtractor,
    CodingCrystalPlanner,
    CodingCrystalRegistry,
)
from app.kernel.compute.crystal_publication import (  # noqa: E402
    CrystalImporter,
    CrystalPublisher,
    assert_publishable,
    build_publication_bundle,
    reproduce_quarantined,
)
from app.kernel.compute.heldout_replay import ReplayReceipt  # noqa: E402

DATASET = "byron-test/beast-coding-crystals"
FAMILY = "fix-failing-assertion"


class FakeHub:
    """In-memory stand-in for OfficialHFDatasetRemote (+ read_file); records every call."""

    def __init__(self):
        self.datasets: dict[str, dict] = {}
        self.calls: list[tuple] = []

    def _ds(self, dataset_id):
        return self.datasets.setdefault(dataset_id, {"private": None, "main": {}, "branches": {}, "prs": [], "chunks": {}})

    def ensure_dataset(self, dataset_id, *, private=True):
        self.calls.append(("ensure_dataset", dataset_id, private))
        self._ds(dataset_id)["private"] = private

    def has_chunk(self, dataset_id, digest):
        return digest in self._ds(dataset_id)["chunks"]

    def upload_chunk(self, dataset_id, digest, payload):
        self.calls.append(("upload_chunk", digest))
        self._ds(dataset_id)["chunks"][digest] = bytes(payload)

    def commit_files(self, dataset_id, files, *, message, parent_commit=""):
        self.calls.append(("commit_files", sorted(files)))
        self._ds(dataset_id)["main"].update({k: bytes(v) for k, v in files.items()})
        return "commit-main"

    def create_branch_and_pr(self, dataset_id, files, *, branch, title, description=""):
        self.calls.append(("create_branch_and_pr", branch, sorted(files)))
        ds = self._ds(dataset_id)
        ds["branches"].setdefault(branch, {}).update({k: bytes(v) for k, v in files.items()})
        ds["prs"].append({"branch": branch, "title": title})
        return {"commit": "commit-pr", "pull_request": f"pr-{len(ds['prs'])}"}

    def read_file(self, dataset_id, path, *, revision="main"):
        ds = self._ds(dataset_id)
        if path.startswith("xet/objects/"):
            digest = "sha256:" + path.split("/", 2)[2].replace("/", "")
            return ds["chunks"][digest]
        files = ds["main"] if revision == "main" else ds["branches"][revision]
        return files[path]

    def all_bytes(self, dataset_id) -> bytes:
        ds = self._ds(dataset_id)
        blobs = list(ds["main"].values()) + list(ds["chunks"].values())
        for files in ds["branches"].values():
            blobs.extend(files.values())
        return b"\n".join(blobs)


@pytest.fixture(scope="module")
def promoted(tmp_path_factory):
    base = tmp_path_factory.mktemp("pub")
    stack = crystal_stack(base / "stack")
    learned = run_learn(base / "learn", base / "envelopes.sqlite3")
    candidate = CodingCrystalExtractor().extract(learned["envelope"], learned["observations"])
    stack["registry"].add_candidate(candidate)
    stack["registry"].promote(candidate.crystal_id, ReplayReceipt(
        candidate.crystal_id, 3, 3, True, "held-out replay passed", ("pricing", "limits", "greeting"), (True, True, True)))
    key = Ed25519PrivateKey.generate()
    record = stack["registry"].get(candidate.crystal_id)
    bundle = build_publication_bundle(record, key, key_id="test-key")
    return {"base": base, "stack": stack, "learned": learned, "candidate": candidate, "key": key, "bundle": bundle}


# --- Task 1 ---------------------------------------------------------------------------------------

def test_bundle_contains_only_manifest_chunks_compat_and_proofs(promoted):
    bundle = promoted["bundle"]
    assert set(bundle["files"]) == {"manifest.json", "compatibility.json", "proofs.json", "chunks.json", "signature.json"}
    manifest = json.loads(bundle["files"]["manifest.json"])
    assert manifest["crystal_id"] == promoted["candidate"].crystal_id
    assert manifest["privacy"] == {"native_kv": False, "memfd_descriptors": False, "prompts": False,
                                   "workspace_content": False, "secrets": False}
    proofs = json.loads(bundle["files"]["proofs.json"])
    assert proofs["heldout_replay"]["successes"] == 3 and proofs["heldout_replay"]["promoted"] is True
    chunks = json.loads(bundle["files"]["chunks.json"])
    assert chunks["authority"] == "data_transport_only" and chunks["native_kv_portability_claimed"] is False
    assert set(bundle["chunks"]) == {c["digest"] for c in chunks["chunks"]}
    blob = b"\n".join(list(bundle["files"].values()) + list(bundle["chunks"].values())).decode()
    root = str(promoted["learned"]["engine"].workspace_root)
    for forbidden in (root, "/home/", "Fix the failing assertion", "RATE = 3", "AssertionError", "BEGIN PRIVATE"):
        assert forbidden not in blob


def test_bundle_refuses_non_promoted(promoted, tmp_path):
    registry = CodingCrystalRegistry(tmp_path / "r.sqlite3")
    registry.add_candidate(promoted["candidate"])
    with pytest.raises(PermissionError):
        build_publication_bundle(registry.get(promoted["candidate"].crystal_id), promoted["key"], key_id="k")


@pytest.mark.parametrize("payload", [
    {"prompt": "x"}, {"nested": [{"native_kv": "..."}]}, {"memfd": 3}, {"note": "password=hunter2-very-secret"},
    {"path": "/home/byron/GitHub/EdgeK-BEAST/calc.py"}, {"stdout": "hello"}, {"workspace_root": "x"},
])
def test_privacy_filter_fails_closed(payload):
    with pytest.raises(ValueError):
        assert_publishable(payload)


# --- Task 2 ---------------------------------------------------------------------------------------

def test_publish_via_private_pr_with_chunk_dedup(promoted):
    hub = FakeHub()
    publisher = CrystalPublisher(hub, DATASET)
    receipt = publisher.publish(promoted["bundle"])
    assert receipt["mode"] == "pr" and receipt["pull_request"] == "pr-1"
    assert hub.datasets[DATASET]["private"] is True
    assert hub.datasets[DATASET]["main"] == {}  # nothing lands on main without review
    prefix = f"crystals/{FAMILY}/{promoted['candidate'].crystal_id}/"
    branch_files = hub.datasets[DATASET]["branches"][receipt["branch"]]
    assert {p for p in branch_files if p.startswith(prefix)} == {prefix + n for n in promoted["bundle"]["files"]}
    assert "README.md" in branch_files
    uploads = [c for c in hub.calls if c[0] == "upload_chunk"]
    assert len(uploads) == len(promoted["bundle"]["chunks"])
    again = publisher.publish(promoted["bundle"])
    assert again["chunks_uploaded"] == 0 and again["chunks_reused"] == len(promoted["bundle"]["chunks"])
    blob = hub.all_bytes(DATASET).decode()
    assert str(promoted["learned"]["engine"].workspace_root) not in blob and "RATE = 3" not in blob


# --- Task 3 ---------------------------------------------------------------------------------------

def _published_main(promoted) -> FakeHub:
    hub = FakeHub()
    CrystalPublisher(hub, DATASET).publish(promoted["bundle"], mode="commit")
    return hub


def test_pull_lands_quarantined_and_is_never_served(promoted, tmp_path):
    hub = _published_main(promoted)
    registry = CodingCrystalRegistry(tmp_path / "remote-node.sqlite3")
    trusted = {"test-key": promoted["key"].public_key()}
    record = CrystalImporter(hub, DATASET, registry).pull(FAMILY, promoted["candidate"].crystal_id, trusted_keys=trusted)
    assert record["status"] == "quarantined"
    assert record["provenance"]["signer_trusted"] is True and record["provenance"]["dataset"] == DATASET
    assert registry.active_for_family(FAMILY) is None
    untrusted = CodingCrystalRegistry(tmp_path / "other.sqlite3")
    rec2 = CrystalImporter(hub, DATASET, untrusted).pull(FAMILY, promoted["candidate"].crystal_id, trusted_keys={})
    assert rec2["status"] == "quarantined" and rec2["provenance"]["signer_trusted"] is False


def test_tampered_chunk_or_manifest_is_refused(promoted, tmp_path):
    hub = _published_main(promoted)
    ds = hub.datasets[DATASET]
    digest = next(iter(ds["chunks"]))
    ds["chunks"][digest] = ds["chunks"][digest][:-1] + b"X"
    with pytest.raises(ValueError):
        CrystalImporter(hub, DATASET, CodingCrystalRegistry(tmp_path / "a.sqlite3")).pull(FAMILY, promoted["candidate"].crystal_id, trusted_keys={})
    hub = _published_main(promoted)
    path = f"crystals/{FAMILY}/{promoted['candidate'].crystal_id}/compatibility.json"
    compat = json.loads(hub.datasets[DATASET]["main"][path])
    compat["opcode_catalog_digest"] = "sha256:" + "0" * 64
    hub.datasets[DATASET]["main"][path] = json.dumps(compat).encode()
    with pytest.raises(ValueError):
        CrystalImporter(hub, DATASET, CodingCrystalRegistry(tmp_path / "b.sqlite3")).pull(FAMILY, promoted["candidate"].crystal_id, trusted_keys={})


def test_quarantined_crystal_promoted_only_after_local_reproduction(promoted, tmp_path):
    hub = _published_main(promoted)
    node = crystal_stack(tmp_path / "node-b")
    importer = CrystalImporter(hub, DATASET, node["registry"])
    crystal_id = promoted["candidate"].crystal_id
    importer.pull(FAMILY, crystal_id, trusted_keys={"test-key": promoted["key"].public_key()})
    failing = reproduce_quarantined(node["registry"], crystal_id, ["a", "b", "c"], lambda v: v != "b")
    assert failing.promoted is False and node["registry"].get(crystal_id)["status"] == "quarantined"
    assert node["registry"].negatives(FAMILY)[-1]["kind"] == "heldout_replay_failed"

    planner = CodingCrystalPlanner(node["registry"], node["authority"], node["ledger"], replay_candidate_id=crystal_id)

    def run_variant(variant):
        result = run_with_planner(tmp_path / f"repro-{variant['module']}", planner, variant=variant)
        return result["final"]["state"] == "completed" and result["provider"].calls == 0

    receipt = reproduce_quarantined(node["registry"], crystal_id, list(HELD_OUT_VARIANTS), run_variant)
    assert receipt.promoted is True
    assert node["registry"].active_for_family(FAMILY).crystal_id == crystal_id


# --- Task 4: gated CLI ---------------------------------------------------------------------------

def _workspace_with_promoted(promoted, tmp_path, monkeypatch):
    import os

    from cryptography.hazmat.primitives import serialization

    key_path = tmp_path / "keys" / "runtime.pem"
    key_path.parent.mkdir(parents=True)
    key_path.write_bytes(Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    os.chmod(key_path, 0o600)
    workspace = tmp_path / "ws"
    registry = CodingCrystalRegistry(workspace / ".beast" / "crystals" / "coding_crystals.sqlite3")
    registry.add_candidate(promoted["candidate"])
    registry.promote(promoted["candidate"].crystal_id, ReplayReceipt(promoted["candidate"].crystal_id, 3, 3, True, "ok"))
    monkeypatch.setenv("BEAST_CODING_CRYSTALS", "1")
    monkeypatch.setenv("BEAST_CODING_CRYSTAL_KEY", str(key_path))
    monkeypatch.delenv("HF_TOKEN", raising=False)
    return workspace


def _cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location("coding_crystals_cli", Path(__file__).resolve().parents[1] / "scripts" / "coding_crystals.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_publish_builds_commons_space_offline_and_never_goes_live_by_default(promoted, tmp_path, monkeypatch, capsys):
    workspace = _workspace_with_promoted(promoted, tmp_path, monkeypatch)
    stage = tmp_path / "stage"
    code = _cli().main(["publish", promoted["candidate"].crystal_id, "--workspace", str(workspace), "--stage", str(stage)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["status"] == "built_offline" and "--live" in out["live_command"]
    assert Path(out["space_bundle"]).is_file() and out["revision_files"] > 5
    prefix = stage / "crystals" / FAMILY / promoted["candidate"].crystal_id
    assert (prefix / "manifest.json").is_file() and (prefix / "signature.json").is_file()
    blob = b"".join(p.read_bytes() for p in stage.rglob("*") if p.is_file()).decode()
    assert str(workspace) not in blob and "BEGIN PRIVATE" not in blob


def test_cli_pull_requires_live_flag(promoted, tmp_path, monkeypatch, capsys):
    workspace = _workspace_with_promoted(promoted, tmp_path, monkeypatch)
    code = _cli().main(["pull", "commons-node-a", promoted["candidate"].crystal_id, "--workspace", str(workspace)])
    assert code == 2 and "--live" in capsys.readouterr().err
