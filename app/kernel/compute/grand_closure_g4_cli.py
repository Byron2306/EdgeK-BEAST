from __future__ import annotations
import argparse, json
from dataclasses import asdict
from pathlib import Path
from .grand_closure_g4 import G4ReadOnlyCanary


def main() -> int:
    p=argparse.ArgumentParser(description="Run BEAST Grand Closure G4 read-only sealed-capsule canary")
    p.add_argument("repository_root")
    p.add_argument("--workspace", required=True)
    p.add_argument("--privacy-domain", required=True)
    p.add_argument("--policy-digest", required=True)
    p.add_argument("--source-state-digest", required=True)
    p.add_argument("--arda-ref", default="arda:g4-read-only-approved")
    p.add_argument("--max-entries", type=int, default=10_000)
    p.add_argument("--output")
    args=p.parse_args()
    receipt=G4ReadOnlyCanary().run(
        repository_root=args.repository_root,
        workspace_id=args.workspace,
        privacy_domain=args.privacy_domain,
        policy_digest=args.policy_digest,
        source_state_digest=args.source_state_digest,
        arda_ref=args.arda_ref,
        max_entries=args.max_entries,
    )
    text=json.dumps(asdict(receipt),indent=2,sort_keys=True)
    if args.output:
        path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text+"\n",encoding="utf-8")
    print(text)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
