"""Measure same-host Commons fetch and replay against a matched cold solve."""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import os
from pathlib import Path
import random
import re
import shutil
import signal
import subprocess
from statistics import median
from tempfile import TemporaryDirectory
import time
from uuid import uuid4

import httpx
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.commons.chunk_store import ChunkManifest
from app.kernel.commons.discovery import CommonsDiscoveryCatalog
from app.kernel.commons.enterprise_plane import CommonsEnterprisePlane
from app.kernel.commons.lattice_trust import CrystalLatticeTrustStore
from app.kernel.commons.remote_client import CommonsEgressGate, RemoteCommonsGateway, RemoteCommonsRegistry
from app.kernel.commons.remote_protocol import CommonsRequestSigner, canonical_json, sha256_bytes
from app.kernel.compute import crystal_memfd_capsule as cap, governed_egress
from app.kernel.compute.family_crystals import FamilyCrystal, FamilyRegistry
from app.kernel.security.local_provider_keys import KeyStoreError, load_key
from scripts.gauntlet_large_tasks import constant, constant_decoy
from scripts.proof.run_behemoth_phase2 import install_fixture, verify_independent
from scripts.proof.run_stage7b_capsule_replay import select_record, sha, snapshot
from scripts.proof.run_stage7b_lab import commons_lab

OWNER, BUCKET, REVISION = "edgek", "stage7b-receiver", "reviewed-v1"
ARTIFACT_PATH = "crystal/family.json"
MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


def ms(start):
    return (time.perf_counter() - start) * 1000


def apply_edit(path, edit):
    old, new = edit["old_text"], edit["new_text"]
    if not all(isinstance(line, str) and line and line.isascii()
               and all(32 <= ord(char) < 127 for char in line)
               for line in (old, new)):
        raise ValueError("expected two single nonempty printable lines")
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    indices = [index for index, line in enumerate(lines) if line.removesuffix("\n") == old]
    if len(indices) != 1:
        raise ValueError("old line must match exactly once")
    assignment = re.fullmatch(r"([A-Z][A-Z0-9_]*) = -?[0-9]{1,6}", old)
    if assignment:
        if not re.fullmatch(rf"{assignment[1]} = -?[0-9]{{1,6}}", new):
            raise ValueError("can only change the integer of the same assignment")
    elif observed := re.fullmatch(r"( +)return ([A-Z][A-Z0-9_]*)", old):
        if not re.fullmatch(rf"{observed[1]}return {observed[2]} [+-] [0-9]{{1,6}}", new):
            raise ValueError("can only adjust the same return expression by an integer")
    else:
        raise ValueError("unsupported exact-line edit")
    index = indices[0]
    lines[index] = new + ("\n" if lines[index].endswith("\n") else "")
    updated = "".join(lines)
    ast.parse(updated)
    path.write_text(updated, encoding="utf-8")


def load_artifact(raw, artifact_pin, crystal_pin):
    if sha256_bytes(raw) != artifact_pin:
        raise PermissionError("artifact does not match the local byte pin")
    candidate = FamilyCrystal.from_dict(json.loads(raw))
    if candidate.digest != crystal_pin or candidate.component_ids or candidate.task_family != "fix-config-constant":
        raise PermissionError("decoded crystal does not match the local crystal pin and scope")
    return candidate


def reader_identity(node_identity):
    def setup(lab, manifest):
        public = node_identity.public_key().public_bytes(serialization.Encoding.PEM,
                                                        serialization.PublicFormat.SubjectPublicKeyInfo)
        for node in manifest["nodes"]:
            path = lab / node["node_id"]
            (path / "receiver.pub.pem").write_bytes(public)
            config = yaml.safe_load((path / "clients.yaml").read_text())
            config["clients"].append({"node_id": "stage7b-reader", "key_id": "reader-v1",
                                      "public_key_path": "receiver.pub.pem", "scopes": ["bucket:read"]})
            (path / "clients.yaml").write_text(yaml.safe_dump(config))
    return setup


async def gateway(lab, entry, root, signer):
    g = RemoteCommonsGateway(
        RemoteCommonsRegistry(root / "nodes.sqlite3"),
        CommonsEgressGate(allowed_hosts=("127.0.0.1",), allow_insecure_loopback=True),
        signer=signer, lattice_trust_store=CrystalLatticeTrustStore.from_file(lab / "trust-commons" / "lattice-trust.yaml"),
        discovery_catalog=CommonsDiscoveryCatalog(root / "discovery.sqlite3"),
    )
    discovery = await g.discover_origins((f"http://127.0.0.1:{entry['port']}",),
                                         source="static_seed", auto_register=True)
    if len(discovery["results"]) != 1 or not discovery["results"][0].get("registered"):
        raise PermissionError("Commons endpoint failed live admission")
    return g


async def publish(lab, entry, root, signer, raw):
    start = time.perf_counter()
    g = await gateway(lab, entry, root, signer)
    node = entry["node_id"]
    await g.create_bucket(node, {"owner": OWNER, "name": BUCKET, "visibility": "private"})
    blob = await g.put_blob(node, raw)
    if blob["digest"] != sha256_bytes(raw):
        raise PermissionError("Commons stored a different blob")
    committed = await g.commit_revision(node, owner=OWNER, name=BUCKET, revision=REVISION, manifest={
        "authority": "remote_hypothesis", "maximum_authority": "verify_only",
        "files": [{"path": ARTIFACT_PATH, "digest": blob["digest"], "size": len(raw)}],
        "metadata": {"kind": "proof_carrying_crystal"},
        "proof": {"local_reproduction_required": True},
    })
    return committed["manifest_digest"], ms(start)


async def receive(lab, entry, root, signer, artifact_pin, crystal_pin, manifest_pin, run_id):
    start = time.perf_counter()
    g = await gateway(lab, entry, root, signer)
    discovery_ms = ms(start)
    pull_start = time.perf_counter()
    node = entry["node_id"]
    revision, blobs = await g.pull_revision(node, owner=OWNER, name=BUCKET, revision=REVISION,
                                             maximum_total_bytes=65536)
    pull_ms = ms(pull_start)
    custody_start = time.perf_counter()
    files = revision["manifest"]["files"]
    if revision["manifest_digest"] != manifest_pin or list(blobs) != [artifact_pin] or len(files) != 1:
        raise PermissionError("unexpected signed revision or artifact set")
    item = files[0]
    if item["path"] != ARTIFACT_PATH or item["digest"] != artifact_pin:
        raise PermissionError("unexpected artifact path or digest in signed manifest")
    plane = CommonsEnterprisePlane(root / "enterprise")
    admitted, _ = plane.admit_remote_revision(node, revision, blobs, workspace_id=run_id)
    reconstructed = plane.chunks.get(ChunkManifest(
        artifact_pin, plane.chunks.chunk_size, tuple(admitted["custody"][0]["chunks"]), item["size"]))
    if plane.vault.get(artifact_pin) != reconstructed:
        raise PermissionError("vault bytes differ from reconstructed chunks")
    crystal = load_artifact(reconstructed, artifact_pin, crystal_pin)
    return crystal, {
        "node_id": node, "discovery_ms": discovery_ms, "pull_ms": pull_ms,
        "custody_and_reconstruction_ms": ms(custody_start), "total_ms": ms(start),
        "blob_payload_bytes": len(blobs[artifact_pin]), "reconstructed_bytes": len(reconstructed),
        "manifest_digest": revision["manifest_digest"], "receipt_digest": revision["receipt_digest"],
        "local_admission_digest": admitted["admission_digest"], "artifact_digest": artifact_pin,
        "maximum_authority": admitted["maximum_authority"],
    }


def control_proposal(task, content, failure):
    # Known edits test the harness only. Never count this as a cold-solve model result.
    if task["role"] == "decoy":
        return {"old_text": "    return RETRIES", "new_text": "    return RETRIES + 2"}
    line = next(line for line in content.splitlines() if line.startswith("MAX_BATCH_SIZE = "))
    return {"old_text": line, "new_text": f"MAX_BATCH_SIZE = {int(line.split(' = ')[1]) + 13}"}


def cold_attempt(task, fixture, worktree, api_key, model):
    started = time.perf_counter()
    source = (fixture / task["target"]).read_text(encoding="utf-8")
    observed = cap._run_verify(task["verify"], fixture)
    row = {"model_id": model if api_key else None, "http_requests": 0, "usage": None}
    if observed["returncode"] == 0:
        raise RuntimeError("cold fixture must fail before edits")
    try:
        if api_key:
            messages = [{"role": "system", "content": "Repair the coding fixture using one exact line replacement. "
                         "Return only JSON with string fields old_text and new_text. Preserve indentation."},
                        {"role": "user", "content": f"File: {task['target']}\n{source}\n"
                         f"Visible failing test output:\n{observed['output'][-1800:]}"}]
            with httpx.Client(timeout=60, follow_redirects=False, trust_env=False) as client:
                class MeteredClient:
                    def post(self, *args, **kwargs):
                        row["http_requests"] += 1
                        return client.post(*args, **kwargs)
                response = governed_egress.post(
                    MeteredClient(), "stage7b_receiver_cold", NIM_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model, "messages": messages, "temperature": 0,
                          "max_tokens": 2048, "stream": False})
            row["http_status"] = response.status_code
            response.raise_for_status()
            response_body = response.json()
            usage = response_body.get("usage") or {}
            row["usage"] = {key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                            if type(usage.get(key)) is int} or None
            choice = response_body["choices"][0]["message"]["content"]
            edit = json.loads(re.sub(r"<think>.*?</think>", "", choice, flags=re.S).strip())
        else:
            edit = control_proposal(task, source, observed["output"])
        shutil.copytree(fixture, worktree)
        apply_edit(worktree / task["target"], edit)
        oracle = verify_independent(worktree, task, True)
        row.update(verified=oracle["passed"], oracle=oracle)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError, PermissionError) as exc:
        row.update(verified=False, error=type(exc).__name__)
    row["wall_ms"] = ms(started)
    return row


def replay_attempt(task, fixture, destination, crystal, record, run_id):
    started = time.perf_counter()
    payload = cap.build_payload(
        crystal, registry_record_digest=record["record_digest"], promotion=record["promotion"],
        parameters={"implementation_target": task["target"], "verify_command": task["verify"]},
        postcondition={"implementation_target": task["target"], "verify_command": task["verify"],
                       "tests_run": task["tests_run"]},
        binding={"root": str(fixture), "worktree": str(destination)},
    )
    manifest = cap.build_manifest(payload, crystal_id=crystal.crystal_id, crystal_digest=crystal.digest)
    fd, sealed = cap.seal_capsule(manifest, payload, env={cap.CAPSULE_ENV: "1"})
    try:
        execution = cap.handoff_to_replay_child(fd, manifest, admit_token=run_id)
    finally:
        os.close(fd)
    oracle = verify_independent(destination, task, True) if destination.exists() else None
    verified = bool(execution.get("ok") and execution["capsule"]["manifest_digest"] == manifest["manifest_digest"]
                    and execution.get("peer_pid_is_parent") and execution.get("admit_token_echo") == run_id
                    and oracle and oracle["passed"])
    return {"verified": verified, "worker_accepted": execution.get("ok") is True,
            "wall_ms": ms(started), "oracle": oracle, "model_calls_worker_reported":
            (execution.get("replay") or {}).get("model_calls"), "local_manifest_digest": manifest["manifest_digest"],
            "transport": execution.get("parent_observed"), "sealed_bytes": sealed["capsule_bytes"]}


def experiment(args, api_key):
    args.out.mkdir(mode=0o700, exist_ok=False)
    report = args.out / "report"
    report.mkdir()
    with TemporaryDirectory(prefix="stage7b-registry-") as scratch:
        saved = Path(scratch) / "registry.sqlite3"
        snapshot(args.db, saved)
        registry_digest = sha(saved)
        record = select_record(FamilyRegistry(saved), composite_id=args.composite_id)
    raw = canonical_json(record["crystal_object"].to_dict())
    artifact_pin = sha256_bytes(raw)
    crystal_pin = record["crystal_object"].digest
    rng = random.Random(args.seed)
    cases = []
    for index in range(args.repeats):
        old = rng.randrange(150, 850)
        cases.append((f"receiver-{index + 1}", constant(
            "heldout", f"receivercase{index + 1}", "MAX_BATCH_SIZE", old, old + 13, ("RETRY_DELAY", 8))))
    cases.append(("near-miss", constant_decoy("receivernear")))
    rows = []
    batch_id = "stage7b-receiver-" + uuid4().hex
    key = Ed25519PrivateKey.generate()
    reader = CommonsRequestSigner(key, node_id="stage7b-reader", key_id="reader-v1")
    with commons_lab(args.out, args.lattice_root, args.base_port, before_launch=reader_identity(key)) as (lab, manifest, _):
        entry = manifest["nodes"][0]
        env = manifest["gateway_env"]
        writer = CommonsRequestSigner.from_pem_file(env["BEAST_COMMONS_REMOTE_CLIENT_KEY"],
                                                    node_id=env["BEAST_COMMONS_REMOTE_CLIENT_NODE_ID"],
                                                    key_id=env["BEAST_COMMONS_REMOTE_CLIENT_KEY_ID"])
        manifest_pin, publishing_ms = asyncio.run(publish(lab, entry, args.out / "writer", writer, raw))
        for case, task in cases:
            trial = args.out / case
            source = install_fixture(trial / "fixture", task)
            order = ["cold", "replay"]
            rng.shuffle(order)
            run_id = f"{batch_id}-{case}"
            row = {"run_id": run_id, "case": case, "order": order, "role": task["role"]}
            for arm in order:
                if arm == "cold":
                    row["cold"] = cold_attempt(task, source, trial / "cold", api_key, args.model)
                    continue
                candidate, receipt = asyncio.run(receive(
                    lab, entry, trial / "receiver-state", reader, artifact_pin, crystal_pin, manifest_pin, run_id))
                replay = replay_attempt(task, source, trial / "replayed", candidate, record, run_id)
                # A refused replay never publishes its tree. Fallback always starts from the pristine fixture.
                fallback = (cold_attempt(task, source, trial / "fallback", api_key, args.model)
                            if not replay["verified"] and not replay["worker_accepted"] else None)
                row.update(transfer=receipt, replay=replay, fallback=fallback,
                           receiver_verified=replay["verified"] or bool(fallback and fallback["verified"]),
                           receiver_wall_ms=receipt["total_ms"] + replay["wall_ms"] +
                           (fallback["wall_ms"] if fallback else 0),
                           receiver_cold_http_requests=fallback["http_requests"] if fallback else 0)
            if row["cold"]["verified"] and row["replay"]["verified"]:
                row["equal_final_trees"] = (row["cold"]["oracle"]["source_tree_hash"] ==
                                            row["replay"]["oracle"]["source_tree_hash"])
            else:
                row["equal_final_trees"] = None
            rows.append(row)
            print(f"{case} cold={row['cold']['verified']} replay={row['replay']['verified']} "
                  f"receiver={row['receiver_verified']}", flush=True)
    main_rows = [row for row in rows if row["role"] == "heldout"]
    near = rows[-1]
    positives = sum(row["replay"]["verified"] and row["replay"]["model_calls_worker_reported"] == 0 for row in main_rows)
    near_refused = not near["replay"]["worker_accepted"] and near["fallback"] is not None
    matched_live = [row for row in main_rows if api_key and row["equal_final_trees"] and
                    row["replay"]["model_calls_worker_reported"] == 0 and row["cold"]["http_requests"] == 1]
    summary = {
        "schema": "beast.stage7b.receiver.v1", "run_id": batch_id, "scope": "Fresh client custody per trial, one localhost Commons source, "
        "one synthetic config family, no network wire bytes or billed compute inferred. Nodes use a historical lattice trust anchor.",
        "code_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "mode": "live_nim" if api_key else "scripted_control", "model": args.model if api_key else None,
        "seed": args.seed, "crystal_id": record["crystal_object"].crystal_id, "crystal_digest": crystal_pin,
        "registry_snapshot_sha256": registry_digest, "artifact_digest": artifact_pin,
        "registry_record_digest": record["record_digest"], "commons_manifest_digest": manifest_pin,
        "publishing_wall_ms_one_time": publishing_ms, "published_blob_payload_bytes": len(raw),
        "positive_pairs": len(main_rows), "replay_positive_verified_zero_model": positives,
        "cold_positive_verified": sum(row["cold"]["verified"] for row in main_rows),
        "equal_final_trees": sum(row["equal_final_trees"] is True for row in main_rows),
        "near_miss_replay_refused": near_refused,
        "near_miss_fallback_verified": bool(near["fallback"] and near["fallback"]["verified"]),
        "paired_live_requests_avoided_equal_verified_trees": len(matched_live) if api_key else None,
        "median_live_receiver_minus_cold_wall_ms": (
            median(row["receiver_wall_ms"] - row["cold"]["wall_ms"] for row in matched_live)
            if matched_live else None),
        "cold_http_statuses": [row["cold"].get("http_status") for row in rows],
        "total_cold_http_requests": sum(row["cold"]["http_requests"] for row in rows),
        "total_receiver_fallback_http_requests": sum(row["receiver_cold_http_requests"] for row in rows),
    }
    paths = (report / "summary.json", report / "attempts.jsonl")
    paths[0].write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    paths[1].write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    (report / "SHA256SUMS").write_text("".join(f"{sha(path)}  {path.name}\n" for path in paths))
    print(f"REPORT={report}")
    controls_ok = positives == len(main_rows) and near_refused
    if not api_key:
        controls_ok &= summary["equal_final_trees"] == len(main_rows) and summary["near_miss_fallback_verified"]
    if not controls_ok:
        return 1
    # Distinguish an intact report with missing live cold solves from a completed comparison.
    if api_key and (not matched_live or len(matched_live) != len(main_rows)
                    or not near["cold"]["verified"] or not summary["near_miss_fallback_verified"]):
        return 2
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--composite-id", required=True)
    parser.add_argument("--lattice-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base-port", type=int, default=18111)
    parser.add_argument("--seed", type=int, default=38731)
    parser.add_argument("--repeats", type=int, default=3, choices=range(1, 11), metavar="1..10")
    parser.add_argument("--mode", choices=("controls", "nim"), default="controls")
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args()
    args.db, args.out, args.lattice_root = args.db.resolve(), args.out.resolve(), args.lattice_root.resolve()
    if not args.db.is_file() or not (args.lattice_root / "lattice_checkpoints.jsonl").is_file():
        parser.error("requires an existing custody registry and lattice ledger")
    if not 1024 <= args.base_port <= 65532:
        parser.error("base port must leave room for three unprivileged ports")
    api_key = os.environ.pop("NVIDIA_API_KEY", "")  # Do not pass the secret to any lab or replay subprocess.
    if args.mode == "nim" and not api_key:
        try:
            api_key = load_key("nvidia_nim")
        except KeyStoreError as exc:
            parser.error(str(exc))
        if not api_key:
            parser.error("NVIDIA_API_KEY not set and no saved key. Run "
                         "python -m app.kernel.security.local_provider_keys set nvidia_nim once.")

    def interrupted(_sig, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        return experiment(args, api_key if args.mode == "nim" else "")
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
