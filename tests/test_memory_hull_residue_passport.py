import json
from datetime import datetime, timedelta, timezone

from app.kernel.security.agent_passport import AgentPassport, AgentPassportPolicy
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.memory_hull import MemoryHull


def test_memory_hull_writes_editable_markdown_and_signed_sidecar(tmp_path):
    hull = MemoryHull(tmp_path / "vault", seal=ResidueSeal(tmp_path / "keys"))
    receipt = hull.write_residue(
        task="Fix proxy auth conflict",
        provider="local/ollama first, cloud fallback second",
        cost_saved={"cloud_calls": 1, "tokens": 3900},
        files_touched=["app/cli/api.py"],
        decision="Use local verifier before cloud escalation.",
        evidence={"verification": "passed"},
        policy_tags=["quality_cascade", "local_first"],
    )

    assert receipt["verified"] is True
    assert receipt["markdown_path"].endswith(".md")
    markdown = (tmp_path / "vault" / "tasks" / f"{receipt['residue_id']}.md").read_text(encoding="utf-8")
    assert "Fix proxy auth conflict" in markdown
    assert "Cost saved" in markdown

    verification = hull.verify_sidecar(tmp_path / "vault" / "tasks" / f"{receipt['residue_id']}.residue.json")
    assert verification["verified"] is True
    assert hull.inventory(verify=True)["failed_sidecars"] == 0
    assert hull.search("proxy auth")[0]["residue_id"] == receipt["residue_id"]


def test_memory_hull_rejects_markdown_and_sidecar_tampering(tmp_path):
    hull = MemoryHull(tmp_path / "vault", seal=ResidueSeal(tmp_path / "keys"))
    receipt = hull.write_residue(task="Seal markdown", decision="Original")
    markdown_path = tmp_path / "vault" / "tasks" / f"{receipt['residue_id']}.md"
    sidecar_path = tmp_path / "vault" / "tasks" / f"{receipt['residue_id']}.residue.json"

    markdown_path.write_text("# rewritten\n", encoding="utf-8")
    assert hull.verify_sidecar(sidecar_path)["verified"] is False

    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["payload"]["decision"] = "Changed"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    assert hull.verify_sidecar(sidecar_path)["verified"] is False


def test_residue_seal_rejects_tampered_payload(tmp_path):
    seal = ResidueSeal(tmp_path / "keys")
    payload = {"task": "seal me", "decision": "local first"}
    signature = seal.sign(payload)
    assert seal.verify(payload, signature)["verified"] is True
    assert seal.verify(payload, signature, expected_purpose="wrong")["verified"] is False

    tampered = dict(payload)
    tampered["decision"] = "cloud first"
    assert seal.verify(tampered, signature)["verified"] is False


def test_agent_passport_policy_prevents_unapproved_cloud_calls():
    policy = AgentPassportPolicy()
    proxy = AgentPassport.local("proxy/gateway")
    governor = AgentPassport.local("runtime-governor")
    scout = AgentPassport.local("scout/repo-reader")

    denied = policy.evaluate(caller=proxy, target="spiffe://beast.local/provider/cloud", action="call")
    assert denied["allowed"] is False
    assert denied["reason"] == "explicit_deny"
    assert denied["policy_gate"]["decision"] == "block"

    approved = policy.evaluate(
        caller=governor,
        target="spiffe://beast.local/provider/cloud",
        action="call",
        facts={"quality_cascade": {"approved": True}},
    )
    assert approved["allowed"] is True
    assert approved["policy_gate"]["decision"] == "allow"

    memory = policy.evaluate(caller=scout, target="spiffe://beast.local/memory/vault", action="append")
    assert memory["allowed"] is True


def test_agent_passport_decisions_can_be_sealed_and_expiry_is_enforced(tmp_path):
    seal = ResidueSeal(tmp_path / "keys")
    policy = AgentPassportPolicy(seal=seal, sign_decisions=True)
    caller = AgentPassport.local("runtime-governor")

    decision = policy.evaluate(
        caller=caller,
        target="spiffe://beast.local/provider/cloud",
        action="call",
        facts={"quality_cascade": {"approved": True}},
    )
    assert decision["allowed"] is True
    assert decision["policy_gate"]["decision"] == "allow"
    assert seal.verify(decision, decision["residue_seal"], expected_purpose="agent_passport_policy_decision")["verified"] is True

    expired = AgentPassport(
        component="runtime-governor",
        spiffe_id="spiffe://beast.local/runtime-governor",
        expires_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
    )
    denied = policy.evaluate(
        caller=expired,
        target="spiffe://beast.local/provider/cloud",
        action="call",
        facts={"quality_cascade": {"approved": True}},
    )
    assert denied["allowed"] is False
    assert denied["reason"] == "passport_expired"


def test_recall_uses_authenticated_payload_not_index_projection(tmp_path):
    hull = MemoryHull(tmp_path / "vault", seal=ResidueSeal(tmp_path / "keys"))
    valid = hull.write_residue(task="Amber control", decision="Use marker 47.")
    index_path = tmp_path / "vault" / ".index" / "residue_index.json"
    index = json.loads(index_path.read_text())
    index["records"][0]["decision"] = "Use forged marker 99."
    index_path.write_text(json.dumps(index))
    assert hull.search("Amber control") == []  # unsigned edit to the index
    hull._write_index(index["records"])  # signed but stale projection, not the sidecar payload
    records = hull.search("Amber control")
    assert len(records) == 1 and records[0]["residue_id"] == valid["residue_id"]
    assert records[0]["decision"] == "Use marker 47."
    assert hull.search("forged marker") == []


def test_recall_rejects_a_valid_signature_from_another_vault_signer(tmp_path):
    root = tmp_path / "vault"
    local = MemoryHull(root, seal=ResidueSeal(tmp_path / "local-keys"))
    local.write_residue(task="Trusted control", decision="Local fact.")
    foreign = MemoryHull(root, seal=ResidueSeal(tmp_path / "other-keys"))
    receipt = foreign.write_residue(task="Foreign control", decision="Foreign fact.")
    assert receipt["verified"]
    assert local.search("Foreign control") == []  # foreign index signature
    local.rebuild_index()  # authentic local index must still not vouch for a foreign sidecar
    assert local.search("Foreign control") == []
    assert local.search("Trusted control")[0]["decision"] == "Local fact."
