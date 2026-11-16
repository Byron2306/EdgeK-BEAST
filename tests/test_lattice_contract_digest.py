"""Distiller lattice nodes carry a deterministic capability_contract_digest the dispatcher can route on."""

from __future__ import annotations

import asyncio
import json
import sys

from app.kernel.compute.adaptive_dispatcher import AdaptiveDispatcher
from app.kernel.compute.crystal_distillation import (
    CONTRACT_SCHEMA,
    CrystalToAdapterDistiller,
    CrystalTrainingSignal,
    capability_contract_digest,
    contract_digest_for_node,
)
from app.kernel.compute.perceive import EdgeKIR


def signal(family="schema_validation", fp="sha256:a", provider="groq", positive=True):
    return CrystalTrainingSignal(**{**_signal_defaults(), "task_family": family, "fingerprint_hash": fp,
                                    "provider": provider, "positive": positive})


def _signal_defaults():
    import dataclasses

    defaults = {}
    for f in dataclasses.fields(CrystalTrainingSignal):
        defaults[f.name] = [] if "labels" in f.name else ({} if f.name == "metadata" else "x")
    return defaults


def test_digest_is_deterministic_and_order_independent():
    a = capability_contract_digest("fam", ["sha256:b", "sha256:a"], verifier_labels=["v2", "v1"], behavior_labels=["b"])
    b = capability_contract_digest("fam", ["sha256:a", "sha256:b"], verifier_labels=["v1", "v2"], behavior_labels=["b"])
    assert a == b and a.startswith("sha256:")


def test_digest_binds_family_fingerprints_and_contract_fields():
    base = capability_contract_digest("fam", ["sha256:a"], verifier_labels=["v"], behavior_labels=["b"])
    assert capability_contract_digest("other", ["sha256:a"], verifier_labels=["v"], behavior_labels=["b"]) != base
    assert capability_contract_digest("fam", ["sha256:z"], verifier_labels=["v"], behavior_labels=["b"]) != base
    assert capability_contract_digest("fam", ["sha256:a"], verifier_labels=["w"], behavior_labels=["b"]) != base
    assert capability_contract_digest("fam", ["sha256:a"], verifier_labels=["v"], behavior_labels=["c"]) != base


def test_distiller_writes_digest_and_node_id_on_lattice_nodes(tmp_path):
    distiller = CrystalToAdapterDistiller(results_root=tmp_path / "r", output_root=tmp_path / "o")
    lattice = distiller.build_lattice([signal(fp="sha256:a"), signal(fp="sha256:b", provider="cohere")])
    node = lattice["nodes"][0]
    assert node["contract_schema"] == CONTRACT_SCHEMA
    assert node["capability_contract_digest"] == contract_digest_for_node(node)
    assert node["node_id"] == node["capability_contract_digest"].split(":")[1][:16]
    on_disk = json.loads((tmp_path / "o" / "capability_lattice_latest.json").read_text())
    assert on_disk["nodes"][0]["capability_contract_digest"] == node["capability_contract_digest"]


def _route_dispatcher(tmp_path, node, metadata):
    distiller = CrystalToAdapterDistiller(results_root=tmp_path / "r", output_root=tmp_path / "o")
    (tmp_path / "o").mkdir(parents=True, exist_ok=True)
    (tmp_path / "o" / "adapter_candidate_evaluation_latest.json").write_text(
        json.dumps({"decision": "candidate_ready_for_local_training"}))
    (tmp_path / "o" / "capability_lattice_latest.json").write_text(json.dumps({"nodes": [node]}))
    dispatcher = AdaptiveDispatcher.__new__(AdaptiveDispatcher)
    dispatcher.distiller = distiller
    ir = EdgeKIR(messages=[{"role": "user", "content": "x"}], model="m", metadata=metadata)
    return asyncio.run(dispatcher.route(ir))


BOUNDARY = {"impact_fingerprint_hash": "i", "repo_fingerprint": "r", "policy_digest": "p", "verifier_digest": "v",
            "state_digest": "s"}


def test_real_distilled_node_routes_to_specialist_on_contract_and_boundaries(tmp_path):
    distiller = CrystalToAdapterDistiller(results_root=tmp_path / "r", output_root=tmp_path / "o")
    node = {**distiller.build_lattice([signal()])["nodes"][0], **BOUNDARY}
    route = _route_dispatcher(tmp_path, node, {"task_class": node["task_family"],
                                               "capability_contract_digest": node["capability_contract_digest"],
                                               **BOUNDARY})
    assert route["execution_mode"] == "local_specialist_adapter"
    assert route["model_ref"] == f"ollama://beast-specialist-{node['node_id']}"


def test_tampered_node_digest_never_routes(tmp_path):
    distiller = CrystalToAdapterDistiller(results_root=tmp_path / "r", output_root=tmp_path / "o")
    node = {**distiller.build_lattice([signal()])["nodes"][0], **BOUNDARY}
    forged = {**node, "verifier_labels": ["attacker"]}  # contract changed, digest kept
    assert _route_dispatcher(tmp_path, forged, {"task_class": node["task_family"],
                                                "capability_contract_digest": node["capability_contract_digest"],
                                                **BOUNDARY}) is None


def test_missing_request_digest_or_boundary_never_routes(tmp_path):
    distiller = CrystalToAdapterDistiller(results_root=tmp_path / "r", output_root=tmp_path / "o")
    node = {**distiller.build_lattice([signal()])["nodes"][0], **BOUNDARY}
    assert _route_dispatcher(tmp_path, node, {"task_class": node["task_family"], **BOUNDARY}) is None
    assert _route_dispatcher(tmp_path, node, {"task_class": node["task_family"],
                                              "capability_contract_digest": node["capability_contract_digest"]}) is None


def test_oqs_import_notice_goes_to_stderr(tmp_path, monkeypatch, capsys):
    from app.kernel.security import crystal_seal

    fake = tmp_path / "fakeoqs"
    (fake / "oqs").mkdir(parents=True)
    (fake / "oqs" / "__init__.py").write_text(
        "import logging, sys\nlog = logging.getLogger('fakeoqs')\nlog.addHandler(logging.StreamHandler(sys.stdout))\n"
        "log.setLevel(logging.INFO)\nlog.info('liboqs-python faulthandler is disabled')\n")
    monkeypatch.syspath_prepend(str(fake))
    monkeypatch.delitem(sys.modules, "oqs", raising=False)
    module = crystal_seal._import_oqs()
    module.log.info("later notice")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "faulthandler is disabled" in captured.err and "later notice" in captured.err
