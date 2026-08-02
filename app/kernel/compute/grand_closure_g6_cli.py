from __future__ import annotations
import argparse, json
from dataclasses import asdict
from pathlib import Path
from app.kernel.compute.grand_closure_g6 import G6HostileRefusalGauntlet

def main() -> int:
    p=argparse.ArgumentParser(description='Run BEAST Grand Closure G6 hostile refusal gauntlet')
    p.add_argument('workspace_root')
    p.add_argument('--output', default='')
    a=p.parse_args()
    receipt=G6HostileRefusalGauntlet().run(workspace_root=a.workspace_root)
    data=asdict(receipt)
    path=Path(a.output) if a.output else Path(a.workspace_root)/'evidence'/'grand_closure'/'grand_closure_g6_hostile_refusal.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n',encoding='utf-8'); tmp.replace(path)
    print(json.dumps({'status':'passed','receipt':str(path),'evidence_digest':receipt.evidence_digest,'cases':receipt.case_count},sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
