from __future__ import annotations
import argparse, importlib, json
from pathlib import Path
from typing import Any
from .x2_runtime import LibbpfBackend, X2AttachManifest, X2RingRuntime, install_signal_handlers

def load_callable(spec: str):
    module, symbol = spec.split(":", 1)
    obj = getattr(importlib.import_module(module), symbol)
    if not callable(obj): raise TypeError(f"{spec} is not callable")
    return obj

def main() -> int:
    p=argparse.ArgumentParser(description="BEAST X2 loss-aware BPF ring runtime")
    p.add_argument("--manifest", required=True)
    p.add_argument("--loader", required=True, help="shared library exposing beast_x2_* ABI")
    p.add_argument("--sink", required=True, help="module:callable Sensorium sink")
    p.add_argument("--lease-resolver", required=True, help="module:callable ProcessLease resolver")
    p.add_argument("--receipt", required=True)
    a=p.parse_args()
    receipts=[]
    runtime=X2RingRuntime(manifest=X2AttachManifest.from_json(a.manifest), backend=LibbpfBackend(a.loader),
        sink=load_callable(a.sink), lease_resolver=load_callable(a.lease_resolver), receipt_sink=receipts.append)
    install_signal_handlers(runtime)
    result=runtime.run()
    out=Path(a.receipt); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"result":result.to_dict(),"periodic_health":receipts}, indent=2, sort_keys=True)+"\n")
    print(out)
    return 0

if __name__=="__main__": raise SystemExit(main())
