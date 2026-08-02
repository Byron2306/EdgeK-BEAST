from __future__ import annotations
import argparse, json
from pathlib import Path
from .x1_runtime import write_prerequisite_receipt

def main() -> int:
    p = argparse.ArgumentParser(description="BEAST X1 BPF Sensorium preflight")
    p.add_argument("--receipt", required=True)
    args = p.parse_args()
    report = write_prerequisite_receipt(args.receipt)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["load_ready"] else 3
if __name__ == "__main__": raise SystemExit(main())
