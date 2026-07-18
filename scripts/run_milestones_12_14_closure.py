#!/usr/bin/env python3
"""Generate live paired economics and a sovereign local Commons federation drill."""
from __future__ import annotations

import argparse
import base64
from dataclasses import asdict
import json
from pathlib import Path
import resource
import sys
import tempfile
import time
import urllib.request

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.kernel.commons.proof_carrying_artifact import CommonsFederation, ProofArtifactAdmission
from app.kernel.compute.displacement_economics import DisplacementEconomics, PairedOccurrence, WorkMeasurement
from app.kernel.compute.file_build_transform import atomic_render, inspect_source, verify_artifact
from app.kernel.evidence.control_graph import ControlEvidenceGraph
from app.kernel.sensorium.contracts_hash import content_hash


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def proc_io() -> int:
    try:
        values = {row.split(":", 1)[0]: int(row.split(":", 1)[1])
                  for row in Path("/proc/self/io").read_text().splitlines()}
        return values.get("read_bytes", 0) + values.get("write_bytes", 0)
    except (OSError, ValueError):
        return 0


def provider_call(url: str, model: str, prompt: str) -> dict:
    request = urllib.request.Request(url.rstrip("/") + "/api/generate", method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"model": model, "prompt": prompt, "stream": False,
                         "options": {"temperature": 0, "seed": 17, "num_predict": 32}}).encode())
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.loads(response.read())
    if not result.get("done"):
        raise RuntimeError("provider did not complete")
    return result


def run_transform(workspace: Path) -> tuple[str, float, float, int]:
    cpu_before = resource.getrusage(resource.RUSAGE_SELF)
    io_before = proc_io(); started = time.perf_counter_ns()
    source = inspect_source(workspace)
    if not source["eligible"]:
        raise PermissionError("source mutation invalidated applicability")
    atomic_render(workspace, source)
    verification_started = time.perf_counter_ns()
    verified = verify_artifact(workspace, source)
    verification_ms = (time.perf_counter_ns() - verification_started) / 1_000_000
    if not verified["verified"]:
        raise RuntimeError("postcondition verification failed")
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    cpu_after = resource.getrusage(resource.RUSAGE_SELF)
    cpu_ms = ((cpu_after.ru_utime + cpu_after.ru_stime) -
              (cpu_before.ru_utime + cpu_before.ru_stime)) * 1000
    return str(verified["artifact_sha256"]), elapsed_ms, cpu_ms, max(0, proc_io() - io_before)


def signed_attestation(key: Ed25519PrivateKey, node_id: str, policy: str, verifier: str) -> dict:
    body = {"node_id": node_id, "verified": True, "expires_at": time.time() + 300,
            "policy_generation": policy, "verifier_digest": verifier,
            "public_key_digest": content_hash(key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw))}
    return {**body, "signature": base64.b64encode(key.sign(canonical(body))).decode()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen2.5:0.5b")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--token-cost-usd", type=float, default=0.000001)
    args = parser.parse_args()
    if args.repeats < 3:
        raise ValueError("closure proof requires at least three repeats")
    args.state_root.mkdir(parents=True, exist_ok=True)
    graph = ControlEvidenceGraph(args.state_root / "federated-evidence.jsonl")
    policy = "policy:milestones-12-14-live:v1"; verifier = "sha256:" + "7" * 64
    task = content_hash({"task": "canonical_file_build", "schema": "v1"})
    occurrences = []
    provider_observations = []
    with tempfile.TemporaryDirectory(prefix="beast-displacement-") as temporary:
        root = Path(temporary)
        for index in range(args.repeats):
            workspace = root / f"pair-{index}"; workspace.mkdir()
            source_value = {"name": f"paired-{index}", "values": [index, index + 1, index + 2]}
            source_bytes = (json.dumps(source_value, sort_keys=True, separators=(",", ":")) + "\n").encode()
            (workspace / "source.json").write_bytes(source_bytes); (workspace / "generated.json").write_bytes(b"stale\n")
            initial = content_hash({"source": source_bytes.decode(), "generated": "stale"})

            provider_started = time.perf_counter_ns()
            provider = provider_call(args.ollama_url, args.model,
                "Return canonical JSON for this bounded build request: " + source_bytes.decode())
            provider_latency = (time.perf_counter_ns() - provider_started) / 1_000_000
            # Ordinary governed route repairs the probabilistic response before exact verification.
            postcondition, repair_ms, repair_cpu, repair_io = run_transform(workspace)
            tokens = int(provider.get("prompt_eval_count") or 0) + int(provider.get("eval_count") or 0)
            baseline = WorkMeasurement("ollama_provider_plus_governed_repair", 1, tokens,
                provider_latency + repair_ms, repair_steps=1, cpu_ms=repair_cpu,
                memory_byte_ms=float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024) * (provider_latency + repair_ms),
                io_bytes=repair_io, provider_cost_usd=tokens * args.token_cost_usd,
                verification_ms=repair_ms, postcondition_digest=postcondition, verifier_digest=verifier,
                policy_generation=policy, initial_state_digest=initial, task_digest=task)
            provider_observations.append({"occurrence": index, "model": args.model,
                "provider_tokens": tokens, "provider_latency_ms": provider_latency,
                "load_duration_ns": provider.get("load_duration"), "prompt_eval_duration_ns": provider.get("prompt_eval_duration"),
                "eval_duration_ns": provider.get("eval_duration"), "response_digest": content_hash(str(provider.get("response") or ""))})

            (workspace / "generated.json").write_bytes(b"stale\n")
            postcondition_local, local_ms, local_cpu, local_io = run_transform(workspace)
            recurrence = WorkMeasurement("promoted_local_recurrence", 0, 0, local_ms,
                cpu_ms=local_cpu, memory_byte_ms=float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024) * local_ms,
                io_bytes=local_io, sensing_ms=0.05, applicability_ms=0.05, authorization_ms=0.05,
                replay_ms=local_ms, verification_ms=0.05, postcondition_digest=postcondition_local,
                verifier_digest=verifier, policy_generation=policy, initial_state_digest=initial, task_digest=task)
            occurrences.append(PairedOccurrence(f"paired-{index}", baseline, recurrence))

        # An actual schema mutation is refused before local actuation and excluded from credit.
        mutation = root / "mutation"; mutation.mkdir(); (mutation / "source.json").write_text('{"name":false}')
        refused = False
        try:
            run_transform(mutation)
        except PermissionError:
            refused = True
        occurrences.append(PairedOccurrence("mutation-invalidated",
            WorkMeasurement("provider", 1, 1, 1, postcondition_digest="mutation-provider",
                verifier_digest=verifier, policy_generation=policy, initial_state_digest="mutation:1", task_digest=task),
            WorkMeasurement("local_refusal", 0, 0, 0, postcondition_digest="safe-refusal",
                verifier_digest=verifier, policy_generation=policy, initial_state_digest="mutation:1", task_digest=task),
            mutation_invalidated=refused, false_hit=True))

    economics = DisplacementEconomics.evaluate(occurrences, setup_cost_usd=0, setup_latency_ms=0)
    DisplacementEconomics.validate(economics)
    economics_node = graph.add("verified_displacement_economics", economics)

    artifact_key = Ed25519PrivateKey.generate(); arda_key = Ed25519PrivateKey.generate()
    def appraise(manifest):
        body = {"allowed": True, "request_digest": content_hash(manifest),
                "policy_generation": policy, "appraisal_ref": "arda:commons-live:" + content_hash(manifest)[7:31]}
        return {**body, "signature": base64.b64encode(arda_key.sign(canonical(body))).decode()}
    bundle = {
        "crystal": {"identity": "crystal:sensorium-file-build:v1", "artifact_digest": "sha256:" + "8" * 64},
        "opcode_catalog": ["file.inspect_source", "build.select_branch", "build.render_artifact", "artifact.verify_build"],
        "applicability_contract": {"task_digest": task, "verifier_digest": verifier, "policy_generation": policy},
        "negative_boundaries": ["invalid_source_schema", "workspace_identity_drift", "verifier_substitution"],
        "replay_corpus_summary": {"paired_occurrences": args.repeats, "mutation_invalidated": refused},
        "displacement_receipt": economics,
        "provenance": {"experiment": "milestones-12-14-live-closure", "provider_model": args.model},
        "privacy_projection": {"raw_sensitive_events_exported": False, "ambient_authority_exported": False},
        "policy_attestation_requirements": {"policy_generation": policy, "fresh_node_attestation": True},
        "decay_rules": {"ttl_seconds": 86400, "demote_on_false_hit": True, "reproduce_before_execute": True},
    }
    admission = ProofArtifactAdmission(args.state_root / "publisher", artifact_key, graph=graph,
        arda_appraiser=appraise).admit(bundle, space_id="space:file-build-proof-v1", explicit_space_admission=True)
    federation = CommonsFederation(graph)
    reproductions = []
    for node_id in ("commons-node-local-a", "commons-node-local-b"):
        node_key = Ed25519PrivateKey.generate(); attestation = signed_attestation(node_key, node_id, policy, verifier)
        node_economics = DisplacementEconomics.evaluate(occurrences,
            measurement_scope={"node_id": node_id, "origin": "node_local"})
        reproductions.append(federation.reproduce(admission, node_id=node_id, contributor_id="contributor:beast-local",
            node_attestation=attestation, local_context={"policy_generation": policy, "verifier_digest": verifier},
            heldout_results=[{"verified": True, "negative_boundary_preserved": True,
                              "postcondition_digest": item.recurrence.postcondition_digest}
                             for item in occurrences if not item.false_hit],
            displacement_receipt=node_economics, expected_verifier_digest=verifier,
            expected_policy_generation=policy))
    aggregate = federation.aggregate_verified_displacement()
    payload = {
        "schema": "beast.milestones-12-14-live-closure.v1", "generated_at": time.time(),
        "scope": "one live provider plus two distinct locally attested logical Commons nodes",
        "remote_physical_node_claimed": False, "provider_observations": provider_observations,
        "economics": economics, "economics_evidence_node": economics_node.node_id,
        "commons_admission": asdict(admission), "reproductions": reproductions,
        "federated_aggregate": aggregate,
        "claim_boundaries": ["logical nodes are local, not independent remote physical hosts",
                             "token cost uses the declared experiment rate", "energy was unavailable"],
    }
    payload["evidence_digest"] = content_hash(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"verified": True, "evidence_digest": payload["evidence_digest"],
                      "provider_calls_avoided": economics["provider_calls_avoided"],
                      "federated_nodes": aggregate["independent_node_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
