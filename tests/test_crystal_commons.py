"""D7 (retargeted): publish promoted coding crystals into BEAST's own Commons, never Hugging Face.

Flow under test: promoted crystal -> privacy-filtered publication bundle -> Commons Space bundle ->
verify_only bucket revisions on several remote nodes (node-signed witness receipts) -> import back as a
quarantined hypothesis -> local held-out reproduction -> sovereign promotion.
"""
from __future__ import annotations

import base64
import json
import sys
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crystal_fabric_support import HELD_OUT_VARIANTS, crystal_stack, run_learn, run_with_planner  # noqa: E402

from app.kernel.commons.enterprise_plane import CommonsEnterprisePlane  # noqa: E402
from app.kernel.commons.remote_protocol import canonical_json, sha256_bytes  # noqa: E402
from app.kernel.commons.remote_store import CommonsBucketStore  # noqa: E402
from app.kernel.compute.coding_crystals import CodingCrystalExtractor, CodingCrystalPlanner  # noqa: E402
from app.kernel.compute.crystal_commons import (  # noqa: E402
    BUCKET,
    OWNER,
    CommonsCrystalImporter,
    CommonsCrystalPublisher,
    build_crystal_space,
    revision_manifest,
    revision_name,
)
from app.kernel.compute.crystal_publication import build_publication_bundle  # noqa: E402
from app.kernel.compute.heldout_replay import ReplayReceipt  # noqa: E402
from app.kernel.networking.commons_spaces import import_space  # noqa: E402

FAMILY = "fix-failing-assertion"
NODES = ("commons-node-a", "commons-node-b", "commons-node-c")


class FakeCommonsTransport:
    """Offline stand-in for the 8101 control-plane routes, backed by real node stores and the real
    local quarantine plane (CommonsEnterprisePlane.admit_remote_revision)."""

    def __init__(self, base: Path, nodes=NODES):
        self.stores = {n: CommonsBucketStore(base / "nodes" / n) for n in nodes}
        self.keys = {n: Ed25519PrivateKey.generate() for n in nodes}
        self.plane = CommonsEnterprisePlane(base / "local-enterprise")
        self.calls: list[tuple] = []
        self.tamper_blob: bytes | None = None

    async def probe(self, node_id):
        self.calls.append(("probe", node_id))
        return {"ok": True, "state": "lattice_attested"}

    def list_buckets(self, node_id):
        rows = self.stores[node_id].list_buckets(include_private=True)
        return {"buckets": rows}

    def create_bucket(self, node_id, payload):
        self.calls.append(("create_bucket", node_id, payload["owner"], payload["name"], payload["visibility"]))
        return {"status": "created", "bucket": self.stores[node_id].create_bucket(actor="beast-control-plane", **payload)}

    def put_blob(self, node_id, payload: bytes):
        self.calls.append(("put_blob", node_id, sha256_bytes(payload)))
        return self.stores[node_id].put_blob(payload, expected_digest=sha256_bytes(payload), actor="beast-control-plane")

    def _signed(self, node_id, result, owner, name, revision):
        receipt = {"beast_object_type": "remote_commons_revision_receipt", "node_id": node_id,
                   "bucket_id": f"{owner}/{name}", "revision": revision, "manifest_digest": result["manifest_digest"],
                   "committed_by": "beast-control-plane", "committed_at": result.get("committed_at", 0),
                   "maximum_authority": "verify_only"}
        return {**result, "receipt": receipt, "receipt_digest": sha256_bytes(canonical_json(receipt)),
                "node_signature": base64.b64encode(self.keys[node_id].sign(canonical_json(receipt))).decode()}

    def commit_revision(self, node_id, *, owner, name, revision, manifest):
        self.calls.append(("commit_revision", node_id, revision))
        result = self.stores[node_id].commit_revision(owner=owner, name=name, revision=revision, manifest=manifest,
                                                      actor="beast-control-plane")
        return {"status": "committed", **self._signed(node_id, result, owner, name, revision)}

    def import_revision(self, node_id, *, owner, name, revision):
        self.calls.append(("import_revision", node_id, revision))
        store = self.stores[node_id]
        value = self._signed(node_id, store.get_revision(owner, name, revision, include_private=True), owner, name, revision)
        blobs = {f["digest"]: store.get_blob(f["digest"]) for f in value["manifest"]["files"]}
        admission, _evidence = self.plane.admit_remote_revision(node_id, value, blobs)
        return {"status": "quarantined_hypothesis", "admission": admission}

    def read_custody(self, digest):
        data = self.plane.vault.get(digest)
        return self.tamper_blob if (self.tamper_blob is not None and b"payload_root_digest" in data) else data


@pytest.fixture(scope="module")
def promoted(tmp_path_factory):
    base = tmp_path_factory.mktemp("commons")
    stack = crystal_stack(base / "stack")
    learned = run_learn(base / "learn", base / "envelopes.sqlite3")
    candidate = CodingCrystalExtractor().extract(learned["envelope"], learned["observations"])
    stack["registry"].add_candidate(candidate)
    stack["registry"].promote(candidate.crystal_id, ReplayReceipt(
        candidate.crystal_id, 3, 3, True, "held-out replay passed", ("pricing", "limits", "greeting"), (True, True, True)))
    key = Ed25519PrivateKey.generate()
    bundle = build_publication_bundle(stack["registry"].get(candidate.crystal_id), key, key_id="test-key")
    return {"base": base, "stack": stack, "candidate": candidate, "key": key, "bundle": bundle}


def test_crystal_space_is_a_valid_privacy_scanned_commons_bundle(promoted, tmp_path):
    space = build_crystal_space(promoted["bundle"], tmp_path / "spaces")
    manifest = space["manifest"]
    assert manifest["task_class"] == "coding_crystal" and manifest["authority"] == "advisory"
    assert manifest["privacy"]["contains_raw_prompts"] is False and manifest["privacy"]["contains_source_code"] is False
    assert space["receipt_validation"]["valid"] is True
    with zipfile.ZipFile(space["bundle_path"]) as archive:
        names = set(archive.namelist())
        blob = b"".join(archive.read(n) for n in names)
    prefix = f"crystals/{FAMILY}/{promoted['candidate'].crystal_id}/"
    assert {prefix + n for n in ("manifest.json", "compatibility.json", "proofs.json", "chunks.json", "signature.json")} <= names
    assert any(n.startswith("xet/objects/") for n in names)
    assert b"BEGIN PRIVATE" not in blob and str(tmp_path).encode() not in blob and b"\"memfd_descriptors\":true" not in blob
    imported = import_space(Path(space["bundle_path"]), tmp_path / "registry", approved=True, dry_run=False)
    assert imported["imported"] is True and imported["validation"]["valid"] is True


def test_revision_manifest_is_verify_only_hypothesis_bound_to_space(promoted, tmp_path):
    space = build_crystal_space(promoted["bundle"], tmp_path / "spaces")
    manifest, blobs = revision_manifest(promoted["bundle"], space)
    assert manifest["authority"] == "remote_hypothesis" and manifest["maximum_authority"] == "verify_only"
    assert manifest["metadata"]["space_manifest_hash"] == space["manifest"]["manifest_hash"]
    assert manifest["metadata"]["crystal_id"] == promoted["candidate"].crystal_id
    assert manifest["proof"]["bundle_digest"] == promoted["bundle"]["bundle_digest"]
    for item in manifest["files"]:
        assert sha256_bytes(blobs[item["digest"]]) == item["digest"] and len(blobs[item["digest"]]) == item["size"]
    assert revision_name(promoted["candidate"].crystal_id).startswith("cc-")


async def test_publish_to_three_nodes_with_matching_witness_receipts(promoted, tmp_path):
    transport = FakeCommonsTransport(tmp_path)
    space = build_crystal_space(promoted["bundle"], tmp_path / "spaces")
    report = await CommonsCrystalPublisher(transport).publish(promoted["bundle"], space, node_ids=NODES)
    assert report["status"] == "published" and report["quorum"] == 3
    assert len({r["manifest_digest"] for r in report["nodes"].values()}) == 1
    assert all(r["receipt"]["maximum_authority"] == "verify_only" for r in report["nodes"].values())
    assert ("create_bucket", "commons-node-a", OWNER, BUCKET, "private") in transport.calls
    again = await CommonsCrystalPublisher(transport).publish(promoted["bundle"], space, node_ids=NODES)
    assert again["status"] == "published" and all(r.get("existing") for r in again["nodes"].values())
    stored = b"".join(p.read_bytes() for p in (tmp_path / "nodes").rglob("*") if p.is_file() and "blobs" in p.parts)
    assert b"BEGIN PRIVATE" not in stored and str(promoted["base"]).encode() not in stored


async def _published(promoted, tmp_path):
    transport = FakeCommonsTransport(tmp_path)
    space = build_crystal_space(promoted["bundle"], tmp_path / "spaces")
    await CommonsCrystalPublisher(transport).publish(promoted["bundle"], space, node_ids=NODES)
    return transport


async def test_import_lands_quarantined_with_custody_and_is_never_served(promoted, tmp_path):
    transport = await _published(promoted, tmp_path)
    node = crystal_stack(tmp_path / "local")
    crystal_id = promoted["candidate"].crystal_id
    record = await CommonsCrystalImporter(transport, node["registry"]).pull(
        "commons-node-b", crystal_id, trusted_keys={"test-key": promoted["key"].public_key()})
    assert record["status"] == "quarantined"
    assert record["provenance"]["signer_trusted"] is True
    assert record["provenance"]["commons"]["node_id"] == "commons-node-b"
    assert record["provenance"]["commons"]["admission_digest"].startswith("sha256:")
    assert record["provenance"]["commons"]["local_reproduction_required"] is True
    assert node["registry"].active_for_family(FAMILY) is None


async def test_tampered_custody_is_refused(promoted, tmp_path):
    transport = await _published(promoted, tmp_path)
    transport.tamper_blob = json.dumps({"schema": "beast.coding_crystal_publication.v1", "payload_root_digest": "x"}).encode()
    node = crystal_stack(tmp_path / "local")
    with pytest.raises(ValueError):
        await CommonsCrystalImporter(transport, node["registry"]).pull("commons-node-a", promoted["candidate"].crystal_id,
                                                                 trusted_keys={})


async def test_import_then_local_reproduction_is_the_only_promotion(promoted, tmp_path):
    from app.kernel.compute.crystal_publication import reproduce_quarantined

    transport = await _published(promoted, tmp_path)
    node = crystal_stack(tmp_path / "local")
    crystal_id = promoted["candidate"].crystal_id
    await CommonsCrystalImporter(transport, node["registry"]).pull("commons-node-c", crystal_id, trusted_keys={})
    planner = CodingCrystalPlanner(node["registry"], node["authority"], node["ledger"], replay_candidate_id=crystal_id)

    def run_variant(variant):
        result = run_with_planner(tmp_path / f"repro-{variant['module']}", planner, variant=variant)
        return result["final"]["state"] == "completed" and result["provider"].calls == 0

    receipt = reproduce_quarantined(node["registry"], crystal_id, list(HELD_OUT_VARIANTS), run_variant)
    assert receipt.promoted is True
    assert node["registry"].active_for_family(FAMILY).crystal_id == crystal_id


def test_gateway_transport_is_loopback_only(tmp_path):
    from app.kernel.compute.crystal_commons import GatewayCommonsTransport

    with pytest.raises(PermissionError):
        GatewayCommonsTransport("https://commons.example.org", vault_root=tmp_path / "vault")


async def test_import_binds_publishing_space_for_shadow_accounting(promoted, tmp_path):
    transport = await _published(promoted, tmp_path)
    node = crystal_stack(tmp_path / "local")
    record = await CommonsCrystalImporter(transport, node["registry"]).pull(
        "commons-node-a", promoted["candidate"].crystal_id, trusted_keys={})
    commons = record["provenance"]["commons"]
    assert commons["space_id"].startswith("coding-crystal-") and commons["space_manifest_hash"].startswith("sha256:")


def test_economy_receipts_attach_to_a_successor_space_bundle(promoted, tmp_path):
    from app.kernel.compute.crystal_economy import CrystalShadowLedger, validate_receipt

    base_space = build_crystal_space(promoted["bundle"], tmp_path / "spaces")
    with pytest.raises(ValueError):
        build_crystal_space(promoted["bundle"], tmp_path / "spaces", economy={"receipts": []})
    ledger = CrystalShadowLedger(tmp_path / "shadow.sqlite3", local_node_id="node-b")
    export = ledger.export(space_id=base_space["space_id"])
    space = build_crystal_space(promoted["bundle"], tmp_path / "spaces", economy=export,
                                parent_manifest_hash=base_space["manifest"]["manifest_hash"])
    assert space["space_id"] != base_space["space_id"]
    assert space["manifest"]["lineage"]["parent_manifest_hash"] == base_space["manifest"]["manifest_hash"]
    paths = {a["path"] for a in space["manifest"]["artifacts"]}
    assert {"economy/reduction_receipts.json", "economy/shadow_ledger.json"} <= paths
    shadow = json.loads((Path(space["space_root"]) / "economy/shadow_ledger.json").read_text())
    assert shadow["transferable"] is False and shadow["settlement"] == "none"
    assert validate_receipt(json.loads((Path(space["space_root"]) / "compute_reduction_receipt.json").read_text()))["valid"]
