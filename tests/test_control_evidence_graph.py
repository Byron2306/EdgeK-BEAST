from app.kernel.evidence.control_graph import ControlEvidenceGraph
from app.kernel.sensorium.observatory import project_observatory
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def test_evidence_graph_links_release_chain():
    graph = ControlEvidenceGraph()
    commit = graph.add("commit", {"source_digest": "sha256:abc"})
    build = graph.add("build", {"artifact_digest": "sha256:def"})
    graph.link(commit, "PRODUCES", build)
    assert graph.query("build")[0].digest == build.digest
    assert graph.links == [(commit.node_id, "PRODUCES", build.node_id)]


def test_observatory_is_payload_free_and_non_actuating():
    view = project_observatory({"socket_topology": ({"service_id": "beast"},), "recent_event_types": {"socket.reconciled": 1}})
    assert view["actuator_available"] is False
    assert view["socket_topology"][0]["service_id"] == "beast"

def test_evidence_graph_reconstructs_and_detects_tampering(tmp_path):
    path = tmp_path / "evidence.jsonl"
    graph = ControlEvidenceGraph(path)
    node = graph.add("build", {"artifact_digest": "sha256:x"})
    assert ControlEvidenceGraph(path).integrity_ok is True
    path.write_text(path.read_text().replace("sha256:x", "sha256:tampered"), encoding="utf-8")
    restored = ControlEvidenceGraph(path)
    assert restored.integrity_ok is False
    assert restored.query("build") == ()
    assert restored.integrity_fracture["reason"] == "hash_chain_mismatch"
    assert len(restored.quarantined_records) == 1


def test_evidence_graph_quarantines_malformed_tail(tmp_path):
    path = tmp_path / "evidence.jsonl"
    graph = ControlEvidenceGraph(path)
    graph.add("build", {"artifact_digest": "sha256:x"})
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"truncated":')
    restored = ControlEvidenceGraph(path)
    assert restored.integrity_ok is False
    assert len(restored.query("build")) == 1
    assert restored.integrity_fracture["reason"] == "malformed_json"


def test_signed_head_checkpoint_detects_truncation(tmp_path):
    path = tmp_path / "evidence.jsonl"
    private = Ed25519PrivateKey.generate()
    graph = ControlEvidenceGraph(path, head_signer=private, head_verifier=private.public_key())
    graph.add("build", {"artifact_digest": "sha256:one"})
    graph.add("deployment", {"artifact_digest": "sha256:two"})
    path.write_text(path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    restored = ControlEvidenceGraph(path, head_verifier=private.public_key())
    assert restored.integrity_ok is False
    assert restored.integrity_fracture["reason"] == "head_checkpoint_mismatch"
    assert len(restored.query("build")) == 1
