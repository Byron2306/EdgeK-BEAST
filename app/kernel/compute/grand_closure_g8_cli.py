from __future__ import annotations
import argparse, json
from dataclasses import asdict
from pathlib import Path
from app.kernel.compute.grand_closure_g8 import GrandClosureG8


def main() -> int:
    p=argparse.ArgumentParser(description='Run Grand Closure G8 capsule-required promotion ceremony')
    p.add_argument('root', nargs='?', default='/home/byron/EdgeK-BEAST')
    p.add_argument('--approval-digest')
    a=p.parse_args()
    evidence=Path(a.root)/'evidence'/'grand_closure'
    r=GrandClosureG8(evidence_dir=evidence).run(operator_approval_digest=a.approval_digest)
    print(json.dumps(asdict(r), indent=2, sort_keys=True))
    return 0 if r.status=='closed' else 1

if __name__=='__main__':
    raise SystemExit(main())
