from __future__ import annotations
import argparse, importlib, json, time
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from .x7_contracts import X7Approval
from .x7_runtime import X7ProductionCanary


def load(spec: str):
    module, symbol = spec.split(":", 1)
    obj = getattr(importlib.import_module(module), symbol)
    return obj() if isinstance(obj, type) else obj


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("object")
    p.add_argument("interface")
    p.add_argument("sender")
    p.add_argument("receiver")
    p.add_argument("backend", help="module:symbol")
    p.add_argument("--max-packets", type=int, default=4096)
    p.add_argument("--max-bytes", type=int, default=8 * 1024 * 1024)
    p.add_argument("--ttl-seconds", type=int, default=300)
    p.add_argument("--receipt", required=True)
    args = p.parse_args()
    path = Path(args.object)
    digest = "sha256:" + sha256(path.read_bytes()).hexdigest()
    approval = X7Approval(args.interface, args.sender, args.receiver, digest,
                          args.max_packets, args.max_bytes,
                          time.time_ns() + args.ttl_seconds * 1_000_000_000,
                          f"x7:{time.time_ns()}")
    receipt = X7ProductionCanary(load(args.backend)).run(approval, path, Path(args.receipt))
    print(json.dumps(asdict(receipt), indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
