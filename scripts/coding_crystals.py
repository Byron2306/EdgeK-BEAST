#!/usr/bin/env python3
"""Operator CLI for reviewed coding crystals (default OFF; see docs in the phase-6 plan).

  status [--workspace PATH]            show flag/key/registry state (never prints key material)
  learn RUN_ID [--workspace PATH]      extract a candidate from a sealed run, replay on 3 held-out
                                       variants without any model, promote only if all pass
  publish CRYSTAL_ID                   build the privacy-filtered Commons Space bundle + bucket revision plan
                                       (offline; prints the live command)
  publish CRYSTAL_ID --live [--gateway URL] [--nodes a,b,c]
                                       register the Space on the local gateway and commit a verify_only
                                       revision to the lattice-attested Commons nodes (quorum = all nodes)
  pull NODE_ID CRYSTAL_ID --live [--workspace PATH]
                                       import the revision back as a QUARANTINED hypothesis (never served)
  reproduce CRYSTAL_ID [--approve-by NAME]
                                       local no-model held-out reproduction; promotes only on 3/3 AND an
                                       explicit operator approval (PGEC 2.4 Promotion Sovereignty)
  ledger                               shadow-economy balances (ledger-only credits, no money)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.coding_crystal_runtime import (  # noqa: E402
    crystal_runtime_status,
    learn_from_run,
    publication_bundle,
    reproduce_imported,
    stage_bundle,
)

DEFAULT_NODES = "commons-node-a,commons-node-b,commons-node-c"


def _state_root() -> Path:
    return Path(os.environ.get("BEAST_STATE_ROOT") or (ROOT / ".beast")).expanduser()


def _transport(args: argparse.Namespace):
    from app.kernel.compute.crystal_commons import GatewayCommonsTransport

    vault = Path(args.vault_root) if args.vault_root else _state_root() / "commons-enterprise" / "vault"
    return GatewayCommonsTransport(args.gateway, vault_root=vault)


def _trusted_keys(workspace: str) -> dict:
    from app.kernel.compute.coding_crystal_runtime import planner_runtime_extras

    authority = planner_runtime_extras(workspace)["crystal_planner"].authority
    return {authority.key_id: authority.verifier()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status")
    status.add_argument("--workspace", default=str(ROOT))
    learn = sub.add_parser("learn")
    learn.add_argument("run_id")
    learn.add_argument("--workspace", default=str(ROOT))
    learn.add_argument("--approve-by", default="", help="operator name; promotion is a human act (PGEC 2.4)")
    publish = sub.add_parser("publish")
    publish.add_argument("crystal_id")
    publish.add_argument("--workspace", default=str(ROOT))
    publish.add_argument("--stage", help="also write the raw publication layout here (offline)")
    publish.add_argument("--live", action="store_true")
    publish.add_argument("--gateway", default="http://127.0.0.1:8101")
    publish.add_argument("--nodes", default=DEFAULT_NODES)
    publish.add_argument("--vault-root")
    publish.add_argument("--with-economy", action="store_true",
                         help="publish a successor space carrying measured receipts + shadow ledger entries")
    pull = sub.add_parser("pull")
    pull.add_argument("node_id")
    pull.add_argument("crystal_id")
    pull.add_argument("--workspace", default=str(ROOT))
    pull.add_argument("--live", action="store_true")
    pull.add_argument("--gateway", default="http://127.0.0.1:8101")
    pull.add_argument("--vault-root")
    reproduce = sub.add_parser("reproduce")
    reproduce.add_argument("crystal_id")
    reproduce.add_argument("--workspace", default=str(ROOT))
    reproduce.add_argument("--approve-by", default="", help="operator name; promotion is a human act (PGEC 2.4)")
    ledger = sub.add_parser("ledger")
    ledger.add_argument("--workspace", default=str(ROOT))
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except PermissionError as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}), file=sys.stderr)
        return 2


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "status":
        print(json.dumps(crystal_runtime_status(args.workspace), indent=2, sort_keys=True))
        return 0
    if args.command == "learn":
        report = learn_from_run(args.workspace, args.run_id, approved_by=args.approve_by)
        if args.approve_by and report.get("status") == "promoted":
            from app.kernel.compute.coder_crystal_feedback import trial_enabled
            from app.kernel.compute.coding_crystal_runtime import planner_runtime_extras

            if trial_enabled(os.environ):
                planner = planner_runtime_extras(args.workspace)["crystal_planner"]
                report["lattice_admission"] = planner.lattice.add_crystal(
                    report["crystal_id"], publisher_id=planner.authority.key_id)
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 0 if report.get("status") in {"promoted", "verified_awaiting_operator_promotion"} else 1
    if args.command == "ledger":
        from app.kernel.compute.coding_crystal_runtime import planner_runtime_extras

        planner = planner_runtime_extras(args.workspace)["crystal_planner"]
        print(json.dumps(planner.economy.ledger.balances(), indent=2, sort_keys=True, default=str))
        return 0
    if args.command == "publish":
        from app.kernel.compute.crystal_commons import CommonsCrystalPublisher, build_crystal_space, revision_manifest

        bundle = publication_bundle(args.workspace, args.crystal_id)
        if args.stage:
            stage_bundle(bundle, args.stage)
        from app.kernel.compute.coding_crystal_runtime import planner_runtime_extras

        planner = planner_runtime_extras(args.workspace)["crystal_planner"]
        spaces_root = Path(args.workspace) / ".beast" / "crystals" / "commons-spaces"
        space = build_crystal_space(bundle, spaces_root)
        planner.economy.ledger.bind_space(args.crystal_id, space_id=space["space_id"],
                                          space_manifest_hash=space["manifest"]["manifest_hash"],
                                          publisher_id=planner.authority.key_id)
        if args.with_economy:
            space = build_crystal_space(bundle, spaces_root, parent_manifest_hash=space["manifest"]["manifest_hash"],
                                        economy=planner.economy.ledger.export(space_id=space["space_id"]))
        manifest, blobs = revision_manifest(bundle, space)
        summary = {"space_id": space["space_id"], "space_bundle": space["bundle_path"], "space_bundle_id": space["bundle_id"],
                   "revision_files": len(manifest["files"]), "blob_bytes": sum(len(b) for b in blobs.values())}
        if not args.live:
            summary["status"] = "built_offline"
            summary["live_command"] = (f"BEAST_CODING_CRYSTALS=1 .venv/bin/python scripts/coding_crystals.py publish "
                                       f"{args.crystal_id} --live --gateway {args.gateway} --nodes {args.nodes}")
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
        transport = _transport(args)
        summary["space_registration"] = {k: v for k, v in transport.register_space(space["bundle_path"]).items()
                                         if k in {"imported", "duplicate", "reason", "space_id", "bundle_id"}}
        report = CommonsCrystalPublisher(transport).publish(bundle, space, node_ids=args.nodes.split(","))
        print(json.dumps({**summary, **report}, indent=2, sort_keys=True, default=str))
        return 0 if report["status"] == "published" else 1
    if args.command == "pull":
        if not args.live:
            print(json.dumps({"status": "live_required", "command": (
                f"BEAST_CODING_CRYSTALS=1 .venv/bin/python scripts/coding_crystals.py pull {args.node_id} "
                f"{args.crystal_id} --live --workspace {args.workspace}")}, indent=2), file=sys.stderr)
            return 2
        from app.kernel.compute.coding_crystal_runtime import planner_runtime_extras
        from app.kernel.compute.crystal_commons import CommonsCrystalImporter

        registry = planner_runtime_extras(args.workspace)["crystal_planner"].registry
        record = CommonsCrystalImporter(_transport(args), registry).pull(
            args.node_id, args.crystal_id, trusted_keys=_trusted_keys(args.workspace))
        provenance = record.get("provenance") or {}
        print(json.dumps({"status": record["status"], "crystal_id": args.crystal_id,
                          "signer_trusted": provenance.get("signer_trusted"), "commons": provenance.get("commons")},
                         indent=2, sort_keys=True))
        return 0
    report = reproduce_imported(args.workspace, args.crystal_id, approved_by=args.approve_by)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report.get("status") in {"promoted", "verified_awaiting_operator_promotion"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
