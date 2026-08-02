from __future__ import annotations
import argparse, json
from dataclasses import asdict
from pathlib import Path
from app.kernel.compute.grand_closure_g5 import G5BoundedWriteRollbackCanary


def main() -> int:
    p=argparse.ArgumentParser(description='Run BEAST Grand Closure G5 bounded write and rollback canary')
    p.add_argument('workspace_root')
    p.add_argument('--workspace', required=True)
    p.add_argument('--privacy-domain', required=True)
    p.add_argument('--policy-digest', required=True)
    p.add_argument('--source-state-digest', required=True)
    p.add_argument('--relative-path', default='.beast_g5_canary.txt')
    p.add_argument('--output', required=True)
    args=p.parse_args()
    receipt=G5BoundedWriteRollbackCanary().run(
        workspace_root=args.workspace_root,
        workspace_id=args.workspace,
        privacy_domain=args.privacy_domain,
        policy_digest=args.policy_digest,
        source_state_digest=args.source_state_digest,
        relative_path=args.relative_path,
    )
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(asdict(receipt),indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(out)
    return 0

if __name__=='__main__': raise SystemExit(main())
