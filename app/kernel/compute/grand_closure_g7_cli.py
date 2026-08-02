from __future__ import annotations
import argparse, json
from dataclasses import asdict
from pathlib import Path
from app.kernel.compute.grand_closure_g7 import GrandClosureG7

def main() -> int:
    p=argparse.ArgumentParser(description='Run BEAST Grand Closure G7 economics and pressure ceremony')
    p.add_argument('root')
    p.add_argument('workspace_id', nargs='?', default='edgek-beast')
    p.add_argument('privacy_domain', nargs='?', default='workspace:edgek-beast')
    a=p.parse_args()
    evidence=Path(a.root)/'evidence'/'grand_closure'
    receipt=GrandClosureG7(evidence_dir=evidence).run(workspace_id=a.workspace_id,privacy_domain=a.privacy_domain)
    print(json.dumps(asdict(receipt),sort_keys=True,indent=2))
    return 0
if __name__=='__main__': raise SystemExit(main())
