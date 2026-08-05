#!/usr/bin/env python3
"""Independent-evidence validation for the DAI-Diode publication envelope.

The final publication uses a two-stage design:

1. build and freeze ``core/CORE_CAPSULE.zip``;
2. collect signed reports that refer to that immutable core digest;
3. build a separately signed publication envelope containing the core and reports.

This avoids impossible self-referential release digests and gives every external
operator one stable subject to reproduce, mutate, ablate, or witness.
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

import dai_publication_core as core


SIGNED_DOMAIN = b"DAI-DIODE-SIGNED-OBJECT-V1\x00"
CORE_CAPSULE_PATH = "core/CORE_CAPSULE.zip"
CORE_TRUST_PATH = "core/CORE_CAPSULE.TRUST.json"
QUORUM_CONTEXT_PATH = "evidence/quorum/QUORUM_CONTEXT.json"
SIGNATURE_FIELDS: dict[str, str] = {
    "dai.independent-reproduction.v1": "operator_key_fingerprint",
    "dai.commons-witness-packet.v1": "signing_key_fingerprint",
    "dai.network-denial-witness.v1": "observer_key_fingerprint",
    "dai.independent-oracle.v1": "oracle_author_key_fingerprint",
    "dai.case-author-attestation.v1": "author_key_fingerprint",
    "dai.independent-prior-art-review.v1": "reviewer_key_fingerprint",
}
RFC3339_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


class EvidenceError(core.PublicationError):
    """A fail-closed independent-evidence validation error."""


def fail(message: str) -> None:
    raise EvidenceError(message)


def _zip_entry_is_special_compat(info: zipfile.ZipInfo) -> bool:
    import stat

    unix_mode = (info.external_attr >> 16) & 0xFFFF
    if not unix_mode:
        return False
    file_type = stat.S_IFMT(unix_mode)
    if file_type == 0:
        return False
    return file_type not in {stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}


# Keep standalone use consistent with the hardened public entry point.
core._zip_entry_is_special = _zip_entry_is_special_compat


def _require_object(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    return value


def _require_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        fail(f"{label} must be a non-empty string")
    return value


def _require_digest(value: Any, *, label: str) -> str:
    text = _require_string(value, label=label)
    if not core.SHA256_RE.fullmatch(text):
        fail(f"{label} must be sha256:<64 lowercase hex>")
    return text


def _require_authority_false(value: Mapping[str, Any], *, label: str) -> None:
    if value.get("production_authority_allowed") is not False:
        fail(f"{label} must deny production authority")
    if value.get("execution_authority_allowed") is not False:
        fail(f"{label} must deny execution authority")


def _parse_utc(value: Any, *, label: str) -> datetime:
    text = _require_string(value, label=label)
    if not RFC3339_Z_RE.fullmatch(text):
        fail(f"{label} must be a canonical RFC3339 UTC timestamp ending in Z")
    parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        fail(f"{label} must be UTC")
    return parsed


def _relative_file(root: Path, relative: Any, *, label: str) -> Path:
    canonical = core.normalize_relative_path(_require_string(relative, label=label))
    candidate = root.joinpath(*Path(canonical).parts)
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        fail(f"{label} escapes candidate root: {canonical}")
    if not candidate.is_file() or candidate.is_symlink():
        fail(f"{label} does not identify a regular file: {canonical}")
    return candidate


def signature_payload(document: Mapping[str, Any]) -> bytes:
    schema = _require_string(document.get("schema"), label="signed object schema")
    payload = copy.deepcopy(dict(document))
    payload.pop("signature_base64", None)
    return SIGNED_DOMAIN + schema.encode("utf-8") + b"\x00" + core.canonical_json_bytes(payload)


def _public_fingerprint(key: Ed25519PublicKey) -> str:
    raw = key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return core.sha256_bytes(raw)


def sign_document(
    path: Path,
    *,
    private_key_path: Path,
    public_key_path: str,
) -> dict[str, Any]:
    document = _require_object(core.load_json_file(path), label=str(path))
    schema = _require_string(document.get("schema"), label="schema")
    fingerprint_field = SIGNATURE_FIELDS.get(schema)
    if fingerprint_field is None:
        fail(f"schema is not admitted for independent signing: {schema}")
    private_key = core.load_ed25519_private_key(private_key_path)
    public_key = private_key.public_key()
    document["signature_algorithm"] = "Ed25519"
    document["public_key_path"] = core.normalize_relative_path(public_key_path)
    document[fingerprint_field] = _public_fingerprint(public_key)
    document.pop("signature_base64", None)
    document["signature_base64"] = base64.b64encode(
        private_key.sign(signature_payload(document))
    ).decode("ascii")
    core.write_canonical_json(path, document)
    return {
        "signed": True,
        "schema": schema,
        "path": str(path),
        "key_fingerprint": document[fingerprint_field],
        "object_digest": core.sha256_file(path),
    }


def verify_signed_document(
    root: Path,
    path: Path,
    *,
    expected_schema: str,
) -> dict[str, Any]:
    document = _require_object(core.load_json_file(path), label=str(path))
    if document.get("schema") != expected_schema:
        fail(f"unexpected schema for {path}: {document.get('schema')!r}")
    fingerprint_field = SIGNATURE_FIELDS.get(expected_schema)
    if fingerprint_field is None:
        fail(f"schema is not admitted for independent verification: {expected_schema}")
    if document.get("signature_algorithm") != "Ed25519":
        fail(f"unsupported signature algorithm in {path}")
    public_path = _relative_file(root, document.get("public_key_path"), label=f"{path}:public_key_path")
    public_key = core.load_ed25519_public_key(public_path)
    fingerprint = _public_fingerprint(public_key)
    if document.get(fingerprint_field) != fingerprint:
        fail(f"key fingerprint mismatch in {path}")
    encoded = _require_string(document.get("signature_base64"), label=f"{path}:signature_base64")
    try:
        signature = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        fail(f"invalid base64 signature in {path}: {exc}")
    if len(signature) != 64:
        fail(f"invalid Ed25519 signature length in {path}")
    try:
        public_key.verify(signature, signature_payload(document))
    except InvalidSignature:
        fail(f"invalid independent signature in {path}")
    return document


def _green_report(path: Path, *, schema: str | None = None) -> dict[str, Any]:
    report = _require_object(core.load_json_file(path), label=str(path))
    if schema is not None and report.get("schema") != schema:
        fail(f"unexpected report schema for {path}: {report.get('schema')!r}")
    _require_authority_false(report, label=str(path))
    green = False
    for key in ("verified", "passed", "result"):
        value = report.get(key)
        if value is True or (isinstance(value, str) and value.lower() in {"pass", "passed", "green", "verified"}):
            green = True
            break
    if not green:
        fail(f"report is not green: {path}")
    return report


def verify_core_capsule(candidate: Path) -> dict[str, Any]:
    capsule = candidate / CORE_CAPSULE_PATH
    trust_path = candidate / CORE_TRUST_PATH
    if not capsule.is_file() or capsule.is_symlink():
        fail(f"missing immutable core capsule: {CORE_CAPSULE_PATH}")
    trust = _require_object(core.load_json_file(trust_path), label=CORE_TRUST_PATH)
    if trust.get("schema") != "dai.core-capsule-trust.v1":
        fail("unsupported core capsule trust schema")
    actual_digest = core.sha256_file(capsule)
    if trust.get("core_capsule_sha256") != actual_digest:
        fail("core capsule digest does not match trust record")
    fingerprint = _require_digest(trust.get("publisher_fingerprint"), label="core publisher fingerprint")
    report = core.verify_release_zip(capsule, trusted_fingerprint=fingerprint)
    if report.get("outer_zip_sha256") != actual_digest:
        fail("core capsule verifier reported a different outer digest")
    expected_release_id = trust.get("core_release_id")
    if expected_release_id is not None and report.get("release_id") != expected_release_id:
        fail("core capsule release_id mismatch")
    return {"core_capsule_sha256": actual_digest, "verification": report}


def _require_subject(document: Mapping[str, Any], subject_digest: str, *, label: str) -> None:
    if document.get("subject_core_capsule_sha256") != subject_digest:
        fail(f"{label} refers to a different core capsule")


def validate_independent_oracle(candidate: Path, subject_digest: str) -> dict[str, Any]:
    cases_path = candidate / "arena" / "ARENA_CASES.json"
    oracle_path = candidate / "arena" / "INDEPENDENT_ORACLE.json"
    author_path = candidate / "arena" / "CASE_AUTHOR_ATTESTATION.json"
    cases = _require_object(core.load_json_file(cases_path), label=str(cases_path))
    oracle = verify_signed_document(candidate, oracle_path, expected_schema="dai.independent-oracle.v1")
    author = verify_signed_document(candidate, author_path, expected_schema="dai.case-author-attestation.v1")
    _require_subject(oracle, subject_digest, label="independent oracle")
    _require_subject(author, subject_digest, label="case-author attestation")
    cases_digest = core.sha256_file(cases_path)
    if oracle.get("case_set_digest") != cases_digest or author.get("case_set_digest") != cases_digest:
        fail("case set digest is not consistently bound by oracle and author attestation")
    if oracle.get("solver_freeze_commit") != author.get("solver_freeze_commit"):
        fail("oracle and author attestation disagree on solver freeze commit")
    if oracle.get("solver_freeze_tag") != author.get("solver_freeze_tag"):
        fail("oracle and author attestation disagree on solver freeze tag")
    statements = _require_object(author.get("statements"), label="case author statements")
    required_true = {
        "cases_authored_after_solver_freeze",
        "author_did_not_modify_solver",
        "author_did_not_receive_private_solver_outputs_before_oracle_freeze",
        "failed_cases_will_not_be_removed_without_append_only_correction",
        "oracle_was_signed_before_solver_execution",
    }
    for field in required_true:
        if statements.get(field) is not True:
            fail(f"case author statement is not true: {field}")
    case_list = cases.get("cases")
    oracle_list = oracle.get("cases")
    if not isinstance(case_list, list) or not isinstance(oracle_list, list) or not case_list:
        fail("arena cases and oracle cases must be non-empty lists")
    case_ids = [_require_string(item.get("case_id"), label="arena case_id") for item in case_list if isinstance(item, dict)]
    oracle_ids = [_require_string(item.get("case_id"), label="oracle case_id") for item in oracle_list if isinstance(item, dict)]
    if len(case_ids) != len(case_list) or len(set(case_ids)) != len(case_ids):
        fail("arena case IDs are missing or duplicated")
    if sorted(case_ids) != sorted(oracle_ids) or len(set(oracle_ids)) != len(oracle_ids):
        fail("oracle does not cover exactly the arena case IDs")
    return {
        "verified": True,
        "case_count": len(case_ids),
        "case_set_digest": cases_digest,
        "oracle_author": oracle.get("oracle_author_id"),
    }


def validate_network_witness(candidate: Path, subject_digest: str) -> dict[str, Any]:
    path = candidate / "reports" / "NETWORK_DENIAL_WITNESS.json"
    witness = verify_signed_document(candidate, path, expected_schema="dai.network-denial-witness.v1")
    _require_subject(witness, subject_digest, label="network witness")
    _require_authority_false(witness, label="network witness")
    if witness.get("result") != "pass":
        fail("network-denial witness did not pass")
    if witness.get("provider_calls_observed") != 0:
        fail("network witness observed provider calls")
    if witness.get("observed_outbound_connections") != []:
        fail("network witness observed outbound connections")
    policy = _require_object(witness.get("network_policy"), label="network policy")
    if policy.get("default_egress") != "deny" or policy.get("dns_allowed") is not False:
        fail("network witness did not enforce deny-by-default egress and DNS denial")
    started = _parse_utc(witness.get("started_at"), label="network witness started_at")
    ended = _parse_utc(witness.get("ended_at"), label="network witness ended_at")
    if not started < ended:
        fail("network witness time interval is invalid")
    required_sources = {
        "network_namespace_or_firewall_rules",
        "socket_or_ebpf_trace",
        "packet_capture_summary",
        "process_tree",
        "dns_attempt_log",
    }
    observed_sources = witness.get("observation_sources")
    if not isinstance(observed_sources, list) or not required_sources.issubset(set(observed_sources)):
        fail("network witness lacks required independent observation sources")
    return {
        "verified": True,
        "observer_operator_id": witness.get("observer_operator_id"),
        "interval": [witness.get("started_at"), witness.get("ended_at")],
    }


def validate_reproductions(candidate: Path, subject_digest: str) -> dict[str, Any]:
    directory = candidate / "reports" / "reproductions"
    paths = sorted(directory.glob("*.json")) if directory.is_dir() else []
    if len(paths) < 2:
        fail("at least two independent reproduction reports are required")
    operators: set[str] = set()
    keys: set[str] = set()
    control_domains: set[str] = set()
    semantic_digests: set[str] = set()
    reports: list[dict[str, Any]] = []
    for path in paths:
        report = verify_signed_document(candidate, path, expected_schema="dai.independent-reproduction.v1")
        _require_subject(report, subject_digest, label=str(path))
        _require_authority_false(report, label=str(path))
        if report.get("result") != "pass":
            fail(f"independent reproduction did not pass: {path}")
        if report.get("private_help_received") is not False:
            fail(f"reproduction was not clean-room independent: {path}")
        operator = _require_string(report.get("operator_id"), label=f"{path}:operator_id")
        control = _require_string(report.get("operator_control_domain"), label=f"{path}:operator_control_domain")
        key = _require_digest(report.get("operator_key_fingerprint"), label=f"{path}:operator key")
        semantic = _require_digest(report.get("semantic_result_digest"), label=f"{path}:semantic result")
        _require_digest(report.get("environment_digest"), label=f"{path}:environment digest")
        _require_digest(report.get("verifier_digest"), label=f"{path}:verifier digest")
        _require_digest(report.get("mutation_report_digest"), label=f"{path}:mutation digest")
        operators.add(operator)
        control_domains.add(control)
        keys.add(key)
        semantic_digests.add(semantic)
        reports.append(report)
    if min(len(operators), len(control_domains), len(keys)) < 2:
        fail("reproduction reports do not establish two distinct operators, control domains, and keys")
    if len(semantic_digests) != 1:
        fail("independent reproductions disagree on normalized semantic result digest")
    return {
        "verified": True,
        "report_count": len(reports),
        "distinct_operator_count": len(operators),
        "distinct_control_domain_count": len(control_domains),
        "semantic_result_digest": next(iter(semantic_digests)),
    }


def _verify_raw_evidence(candidate: Path, packet: Mapping[str, Any], *, label: str) -> int:
    entries = packet.get("raw_attestation_evidence")
    if not isinstance(entries, list) or not entries:
        fail(f"{label} must preserve at least one raw attestation evidence object")
    count = 0
    for index, entry in enumerate(entries):
        item = _require_object(entry, label=f"{label}:raw evidence {index}")
        path = _relative_file(candidate, item.get("path"), label=f"{label}:raw evidence path")
        digest = _require_digest(item.get("sha256"), label=f"{label}:raw evidence digest")
        if core.sha256_file(path) != digest:
            fail(f"raw attestation evidence digest mismatch: {path}")
        count += 1
    return count


def validate_quorum(candidate: Path, subject_digest: str) -> dict[str, Any]:
    context_path = candidate / QUORUM_CONTEXT_PATH
    context = _require_object(core.load_json_file(context_path), label=QUORUM_CONTEXT_PATH)
    if context.get("schema") != "dai.commons-quorum-context.v1":
        fail("unsupported quorum context schema")
    _require_subject(context, subject_digest, label="quorum context")
    _require_authority_false(context, label="quorum context")
    evaluation_time = _parse_utc(context.get("evaluation_time"), label="quorum evaluation_time")
    expected = _require_object(context.get("expected_binding"), label="quorum expected_binding")
    binding_fields = (
        "proposal_digest",
        "capability_digest",
        "evidence_root",
        "world_state_hash",
        "governance_epoch",
        "challenge_nonce",
        "verifier_digest",
    )
    for field in binding_fields:
        value = expected.get(field)
        if field.endswith("digest") or field in {"evidence_root", "world_state_hash", "proposal_digest", "capability_digest", "verifier_digest"}:
            _require_digest(value, label=f"quorum expected {field}")
        else:
            _require_string(str(value) if value is not None else value, label=f"quorum expected {field}")
    policy = _require_object(context.get("policy"), label="quorum policy")
    minimum_approvals = policy.get("minimum_approvals")
    minimum_operators = policy.get("minimum_distinct_operators")
    minimum_keys = policy.get("minimum_distinct_keys")
    minimum_providers = policy.get("minimum_distinct_providers")
    minimum_control_domains = policy.get("minimum_distinct_control_domains")
    integers = [minimum_approvals, minimum_operators, minimum_keys, minimum_providers, minimum_control_domains]
    if any(not isinstance(value, int) or value < 1 for value in integers):
        fail("quorum policy minima must be positive integers")
    required_roles_raw = policy.get("required_approve_roles")
    if not isinstance(required_roles_raw, list) or not required_roles_raw:
        fail("quorum policy must declare required approve roles")
    required_roles = {_require_string(role, label="required quorum role") for role in required_roles_raw}
    packet_paths = sorted((candidate / "evidence" / "quorum").glob("*.witness.json"))
    if len(packet_paths) < minimum_approvals:
        fail("insufficient witness packets for quorum policy")
    operators: set[str] = set()
    keys: set[str] = set()
    providers: set[str] = set()
    controls: set[str] = set()
    approve_roles: set[str] = set()
    seen_vote_identity: set[tuple[str, str, str]] = set()
    approve_count = 0
    raw_evidence_count = 0
    for path in packet_paths:
        packet = verify_signed_document(candidate, path, expected_schema="dai.commons-witness-packet.v1")
        _require_subject(packet, subject_digest, label=str(path))
        _require_authority_false(packet, label=str(path))
        for field in binding_fields:
            if packet.get(field) != expected.get(field):
                fail(f"quorum packet binding mismatch for {field}: {path}")
        issued = _parse_utc(packet.get("issued_at"), label=f"{path}:issued_at")
        expires = _parse_utc(packet.get("expires_at"), label=f"{path}:expires_at")
        if not issued <= evaluation_time < expires:
            fail(f"quorum packet is not valid at evaluation_time: {path}")
        operator = _require_string(packet.get("operator_id"), label=f"{path}:operator_id")
        control = _require_string(packet.get("operator_control_domain"), label=f"{path}:operator_control_domain")
        provider = _require_string(packet.get("infrastructure_provider"), label=f"{path}:infrastructure_provider")
        key = _require_digest(packet.get("signing_key_fingerprint"), label=f"{path}:signing key")
        role = _require_string(packet.get("witness_role"), label=f"{path}:witness_role")
        identity = (operator, key, role)
        if identity in seen_vote_identity:
            fail(f"duplicate witness vote identity: {identity}")
        seen_vote_identity.add(identity)
        operators.add(operator)
        controls.add(control)
        providers.add(provider)
        keys.add(key)
        raw_evidence_count += _verify_raw_evidence(candidate, packet, label=str(path))
        decision = packet.get("decision")
        if decision not in {"approve", "reject", "abstain"}:
            fail(f"invalid quorum decision in {path}")
        if decision == "approve":
            approve_count += 1
            approve_roles.add(role)
    if approve_count < minimum_approvals:
        fail("quorum has too few approvals")
    if len(operators) < minimum_operators:
        fail("quorum has too few distinct operators")
    if len(keys) < minimum_keys:
        fail("quorum has too few distinct signing keys")
    if len(providers) < minimum_providers:
        fail("quorum has too few distinct infrastructure providers")
    if len(controls) < minimum_control_domains:
        fail("quorum has too few distinct operator control domains")
    if not required_roles.issubset(approve_roles):
        fail(f"quorum lacks required approving roles: {sorted(required_roles - approve_roles)}")
    return {
        "verified": True,
        "approve_count": approve_count,
        "distinct_operator_count": len(operators),
        "distinct_key_count": len(keys),
        "distinct_provider_count": len(providers),
        "distinct_control_domain_count": len(controls),
        "approve_roles": sorted(approve_roles),
        "raw_attestation_evidence_count": raw_evidence_count,
        "evaluation_time": context.get("evaluation_time"),
    }


def _validate_claims_and_gates(candidate: Path) -> dict[str, Any]:
    claims_path = candidate / "docs" / "CLAIMS_REGISTRY.json"
    criteria_path = candidate / "docs" / "BDI_VALIDITY_CRITERIA.json"
    gates_path = candidate / "docs" / "FINAL_GATE_CHECKLIST.json"
    claims = _require_object(core.load_json_file(claims_path), label=str(claims_path))
    criteria = _require_object(core.load_json_file(criteria_path), label=str(criteria_path))
    gates = _require_object(core.load_json_file(gates_path), label=str(gates_path))
    _require_authority_false(claims, label="claims registry")
    _require_authority_false(criteria, label="BDI criteria")
    _require_authority_false(gates, label="final gate checklist")
    criteria_items = criteria.get("criteria")
    if not isinstance(criteria_items, list) or not criteria_items:
        fail("BDI validity criteria are missing")
    red_criteria = [item.get("id") for item in criteria_items if not isinstance(item, dict) or item.get("status") != "pass"]
    if red_criteria:
        fail(f"BDI validity criteria are not all pass: {red_criteria}")
    gate_items = gates.get("gates")
    if not isinstance(gate_items, list):
        fail("final gate checklist is missing")
    gate_status = {item.get("id"): item.get("status") for item in gate_items if isinstance(item, dict)}
    required_technical = {f"G{number:02d}" for number in range(1, 25)} | {"G27", "G28"}
    red_gates = sorted(gate for gate in required_technical if gate_status.get(gate) != "pass")
    if red_gates:
        fail(f"technical publication gates are not all pass: {red_gates}")
    claim_items = claims.get("claims")
    if not isinstance(claim_items, list):
        fail("claims registry entries are missing")
    claim_status = {item.get("id"): item.get("status") for item in claim_items if isinstance(item, dict)}
    required_claims = {
        "CLAIM-INTEGRITY",
        "CLAIM-LINEAGE",
        "CLAIM-BDI",
        "CLAIM-COMPOSITION",
        "CLAIM-EXPRESSION",
        "CLAIM-OFFLINE",
        "CLAIM-QUORUM",
        "CLAIM-REPRODUCTION",
    }
    red_claims = sorted(claim for claim in required_claims if claim_status.get(claim) != "pass")
    if red_claims:
        fail(f"technical claims are not all pass: {red_claims}")
    world_first_status = claim_status.get("CLAIM-WORLD-FIRST")
    if world_first_status == "pass":
        if gate_status.get("G25") != "pass" or gate_status.get("G26") != "pass":
            fail("world-first claim is pass without prior-art source completion and independent review")
        world_first_allowed = True
    elif world_first_status in {"withheld_pending_prior_art_and_external_review", "withheld"}:
        world_first_allowed = False
    else:
        fail("world-first claim must be pass or explicitly withheld")
    return {
        "verified": True,
        "technical_claims_allowed": True,
        "world_first_claim_allowed": world_first_allowed,
    }


def validate_candidate_hardened(candidate: Path, *, stage: str) -> dict[str, Any]:
    core.refuse_optimized_python()
    candidate = candidate.resolve()
    # Reuse the fail-closed RC checks, but replace the weaker first-generation
    # final checks with cryptographic independent-evidence verification.
    rc_report = core.validate_candidate(candidate, stage="rc")
    if stage == "rc":
        return rc_report
    core_report = verify_core_capsule(candidate)
    subject = core_report["core_capsule_sha256"]
    mutation = _green_report(candidate / "reports" / "MUTATION_REPORT.json", schema="dai.mutation-report.v1")
    ablation = _green_report(candidate / "reports" / "ABLATION_REPORT.json", schema="dai.ablation-report.v1")
    for label, report in (("mutation", mutation), ("ablation", ablation)):
        _require_subject(report, subject, label=f"{label} report")
    oracle = validate_independent_oracle(candidate, subject)
    network = validate_network_witness(candidate, subject)
    reproductions = validate_reproductions(candidate, subject)
    quorum = validate_quorum(candidate, subject)
    claims = _validate_claims_and_gates(candidate)
    return {
        "verified": True,
        "stage": "final",
        "core": core_report,
        "oracle": oracle,
        "network": network,
        "reproductions": reproductions,
        "quorum": quorum,
        "claims": claims,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }


def verify_publication_release(
    release: Path,
    *,
    expected_zip_sha256: str,
    trusted_fingerprint: str,
) -> dict[str, Any]:
    expected = _require_digest(expected_zip_sha256, label="expected publication ZIP digest")
    actual = core.sha256_file(release)
    if actual != expected:
        fail(f"outer publication ZIP digest mismatch: expected {expected}, got {actual}")
    # Deterministic publication ZIPs contain no explicit directory entries.
    with zipfile.ZipFile(release, "r") as archive:
        directories = [info.filename for info in archive.infolist() if info.is_dir()]
        if directories:
            fail(f"publication ZIP contains unlisted explicit directory entries: {directories}")
        if archive.comment:
            fail("publication ZIP comment is forbidden")
    report = core.verify_release_zip(release, trusted_fingerprint=trusted_fingerprint)
    if report.get("outer_zip_sha256") != actual:
        fail("publication verifier reported a different outer digest")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sign = sub.add_parser("sign-object")
    sign.add_argument("object", type=Path)
    sign.add_argument("--private-key", type=Path, required=True)
    sign.add_argument("--public-key-path", required=True)

    verify = sub.add_parser("verify-object")
    verify.add_argument("candidate", type=Path)
    verify.add_argument("object", type=Path)
    verify.add_argument("--schema", required=True)

    final = sub.add_parser("validate-final")
    final.add_argument("candidate", type=Path)

    release = sub.add_parser("verify-release")
    release.add_argument("release", type=Path)
    release.add_argument("--expected-zip-sha256", required=True)
    release.add_argument("--trusted-fingerprint", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "sign-object":
            result = sign_document(
                args.object,
                private_key_path=args.private_key,
                public_key_path=args.public_key_path,
            )
        elif args.command == "verify-object":
            result = verify_signed_document(args.candidate, args.object, expected_schema=args.schema)
        elif args.command == "validate-final":
            result = validate_candidate_hardened(args.candidate, stage="final")
        elif args.command == "verify-release":
            result = verify_publication_release(
                args.release,
                expected_zip_sha256=args.expected_zip_sha256,
                trusted_fingerprint=args.trusted_fingerprint,
            )
        else:
            fail(f"unknown command: {args.command}")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (core.PublicationError, OSError, zipfile.BadZipFile) as exc:
        print(f"DAI evidence failure: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
