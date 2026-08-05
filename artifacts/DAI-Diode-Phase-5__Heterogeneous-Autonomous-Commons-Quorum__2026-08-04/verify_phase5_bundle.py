#!/usr/bin/env python3
import hashlib, json, unicodedata
from pathlib import Path
ROOT = Path(__file__).resolve().parent
EXPECTED = {"azure_admission_report_digest": "sha256:df5675269c407631b902d706759686b2662d45ac8888ff63ffe75843560b136a", "azure_harvest_digest": "sha256:6b156024ccf83f7106b175b75e65f56b0e2bd4b119004d49125fff1bf96e2bcd", "azure_jwks_digest": "sha256:46b7ff1df1b903f9e9b1c1c43363199eea990025ea2852af44add3d14ed677a9", "azure_live_verification_digest": "sha256:13cd905ca91ef07b86752d8874d4e6d21e300214e111e883099a943899fd7316", "azure_offline_verification_digest": "sha256:e164ff3d76bb6fa6f7eb53dd7f99e1e860f5d2cf0f630a1e5053a2722c168b94", "gcp_governance_envelope_digest": "sha256:e443ec62d6406f1ea2af14e630bd1d69f2285a2df20536ed97ca01213f02b019", "gcp_physical_envelope_digest": "sha256:de095c739633f7c06a48207b9bdd58085335b0dccf0bdda81e3811cfdb0b2462", "gcp_provider_signature_verification_digest": "sha256:966bf9fb70c48cd9b0cec71132ba6fc4ba90cc3e64e3a27da8ce3d85901c2edf", "github_live_envelope_digest": "sha256:3440cb4385a732ff7160df7061149cb8772e87e8fb2c89caa0912e2e83cf2996", "github_live_verification_digest": "sha256:4ce16441ae173eafcaad2b4a12f01220e8cbdb7ee81805bdf75f3002121b4f4f", "hf_shared_packet_digest": "sha256:334699f9c5d21687874c7ec8a54b1ecd04196b2c877518b1ffc9423d290365f9", "hf_shared_receipt_digest": "sha256:a1737d69a90592873087c7a3bdf40d7e118923db53bf6fd96120c99fa9c8da0d", "remote_packet_gauntlet_receipt_digest": "sha256:d73ee9ce91657c4492d31561303f15c59d17664a138c2ac3620115ea65c03ce4", "shared_proposal_digest": "sha256:5df338a298b4f95abcc6edfcdc98772b787848c3cc0694a144110ac3553fcaff", "shared_proposal_packet_digest": "sha256:974d47dcb8f3d46b78f72de97b86a1f7960176423dcea46c37574810650bea86", "shared_quorum_replay_digest": "sha256:40a463606d84606260aaaaedde538ff691dd37e7f6cf939c4673a56c809e5a16", "shared_quorum_report_digest": "sha256:a031335809e7e98609691d56ea297829204eeb6500bfc48a135f3767d558be4d"}
CONTROL = {"SHA256_MANIFEST.json", "SHA256SUMS.txt", "RELEASE_MANIFEST.json"}
def canonical(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
def od(value): return "sha256:"+hashlib.sha256(canonical(value).encode()).hexdigest()
def fd(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""): h.update(block)
    return "sha256:"+h.hexdigest()
def check(cond, msg):
    if not cond: raise RuntimeError(str(msg))
def read(path): return json.loads((ROOT/path).read_text())
def self_digest(payload, field, expected, label):
    body=dict(payload); claimed=body.pop(field, "")
    check(claimed == expected, {label+"_expected_mismatch": claimed})
    check(od(body) == claimed, {label+"_digest_recompute_failed": claimed})
def validate_manifest():
    manifest = read(Path("SHA256_MANIFEST.json"))
    entries = manifest["entries"]
    seen=set(); folded=set(); nfc=set()
    for row in entries:
        rel=row["path"]; path=ROOT/rel
        check(path.is_file(), {"missing_manifest_path": rel})
        check(not path.is_symlink(), {"symlink_manifest_path": rel})
        check(not Path(rel).is_absolute() and all(part not in ("", ".", "..") for part in Path(rel).parts), {"unsafe_manifest_path": rel})
        check(path.name not in CONTROL or rel in CONTROL, {"nested_control_file": rel})
        check(rel not in seen and rel.casefold() not in folded and unicodedata.normalize("NFC", rel) not in nfc, {"colliding_manifest_path": rel})
        seen.add(rel); folded.add(rel.casefold()); nfc.add(unicodedata.normalize("NFC", rel))
        check(fd(path)==row["sha256"], {"manifest_digest_mismatch": rel})
        check(path.stat().st_size==row["size_bytes"], {"manifest_size_mismatch": rel})
    check(od(entries)==manifest["manifest_digest"], "manifest digest does not recompute")
    release = read(Path("RELEASE_MANIFEST.json"))
    body=dict(release); claimed=body.pop("release_manifest_digest", "")
    check(claimed and od(body)==claimed, "release manifest digest does not recompute")
    check(release["file_manifest_digest"]==manifest["manifest_digest"], "release/file manifest digest mismatch")
def validate_evidence():
    proposal = read(Path("evidence/dai-diode/phase5-shared-quorum/dio_phase5_shared_proposal.json"))
    quorum = read(Path("evidence/dai-diode/phase5-shared-quorum/dio_phase5_shared_quorum_replay.json"))
    hf = read(Path("evidence/dai-diode/phase5-shared-quorum/hf/dio_hf_shared_proposal_witness_receipt.json"))
    github = read(Path("evidence/dai-diode/phase5-shared-quorum/github/run-30960436614/dio_github_actions_autonomous_witness_verification.json"))
    gcp_phys = read(Path("evidence/dai-diode/phase5-shared-quorum/gcp-physical-remote/dio_gcp_autonomous_witness_envelope.json"))
    gcp_gov = read(Path("evidence/dai-diode/phase5-shared-quorum/gcp-governance-remote/dio_gcp_autonomous_witness_envelope.json"))
    gcp_provider = read(Path("evidence/dai-diode/phase5-shared-quorum/gcp/google-confidential-space-provider-signature-reverification.json"))
    azure_harvest = read(Path("evidence/dai-diode/phase5-shared-quorum/azure-live-maa-001/dio_azure_tee_attestation_harvest.json"))
    azure_live = read(Path("evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_maa_token_verification.json"))
    azure_offline = read(Path("evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_maa_token_verification.offline.json"))
    gauntlet = read(Path("evidence/dai-diode/phase5-remote-witness-packet/phase5_remote_witness_packet_gauntlet_receipt.json"))
    self_digest(proposal, "packet_digest", EXPECTED["shared_proposal_packet_digest"], "proposal")
    check(proposal["proposal_digest"]==EXPECTED["shared_proposal_digest"], "proposal digest mismatch")
    self_digest(quorum, "replay_digest", EXPECTED["shared_quorum_replay_digest"], "quorum")
    self_digest(hf, "receipt_digest", EXPECTED["hf_shared_receipt_digest"], "hf")
    self_digest(github, "verification_digest", EXPECTED["github_live_verification_digest"], "github")
    self_digest(gcp_provider, "verification_digest", EXPECTED["gcp_provider_signature_verification_digest"], "gcp_provider")
    self_digest(azure_harvest, "harvest_digest", EXPECTED["azure_harvest_digest"], "azure_harvest")
    self_digest(azure_live, "verification_digest", EXPECTED["azure_live_verification_digest"], "azure_live")
    self_digest(azure_offline, "verification_digest", EXPECTED["azure_offline_verification_digest"], "azure_offline")
    self_digest(gauntlet, "receipt_digest", EXPECTED["remote_packet_gauntlet_receipt_digest"], "gauntlet")
    check(hf.get("verified") is True and hf.get("red_gates")==[], "HF not green")
    check((hf.get("autonomous_packet") or dict()).get("packet", dict()).get("packet_digest")==EXPECTED["hf_shared_packet_digest"], "HF packet digest mismatch")
    check(github.get("verified") is True and github.get("red_gates")==[], "GitHub not green")
    check(github.get("envelope_digest")==EXPECTED["github_live_envelope_digest"], "GitHub envelope mismatch")
    check(gcp_phys.get("envelope_digest")==EXPECTED["gcp_physical_envelope_digest"] and gcp_phys.get("remote_runtime_observed") is True, "GCP physical mismatch")
    check(gcp_gov.get("envelope_digest")==EXPECTED["gcp_governance_envelope_digest"] and gcp_gov.get("remote_runtime_observed") is True, "GCP governance mismatch")
    check(gcp_provider.get("passed") is True and gcp_provider.get("red_gates")==[], "GCP provider verification not green")
    check(azure_harvest.get("green") is True and azure_harvest.get("admission_report_digest")==EXPECTED["azure_admission_report_digest"], "Azure harvest not green")
    check(azure_live.get("passed") is True and azure_live.get("red_gates")==[] and azure_live.get("jwks_digest")==EXPECTED["azure_jwks_digest"], "Azure live verifier not green")
    check(azure_offline.get("passed") is True and azure_offline.get("red_gates")==[] and azure_offline.get("jwks_digest")==EXPECTED["azure_jwks_digest"], "Azure offline verifier not green")
    report = quorum["quorum"]
    check(quorum.get("green") is True and quorum.get("red_gates")==[] and quorum.get("provider_calls_used")==0, "quorum replay not green/zero-provider")
    check(report.get("report_digest")==EXPECTED["shared_quorum_report_digest"], "quorum report digest mismatch")
    check(report.get("decision")=="approve" and report.get("quorum_class")=="heterogeneous_distributed_quorum", "quorum decision/class mismatch")
    check(report.get("valid_vote_count")==4 and report.get("admitted_node_count")==4 and report.get("hardware_rooted_node_count")==2, "quorum count mismatch")
    check(set(report.get("roles_present") or [])=={"semantic_witness","adversarial_witness","physical_execution_witness","governance_witness"}, "quorum role mismatch")
    for payload in (quorum, azure_harvest, azure_live, azure_offline):
        check(payload.get("production_authority_allowed") in (None, False), "production authority boundary violated")
        check(payload.get("execution_authority_allowed") in (None, False), "execution authority boundary violated")
validate_manifest()
validate_evidence()
print(json.dumps({"verified": True, "release_id": "DAI-Diode-Phase-5__Heterogeneous-Autonomous-Commons-Quorum__2026-08-04", "entry_count": read(Path("SHA256_MANIFEST.json"))["entry_count"], "shared_quorum_report_digest": EXPECTED["shared_quorum_report_digest"], "provider_calls_used": 0, "production_authority_allowed": False, "execution_authority_allowed": False}, sort_keys=True))
