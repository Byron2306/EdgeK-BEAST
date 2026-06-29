#!/usr/bin/env python3
"""Compare baseline Qwen, BEAST wrapper, loaded LoRA, crystal-only, and cloud route."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.adapter_comparison import AdapterComparisonGauntlet


def main() -> int:
    parser = argparse.ArgumentParser(description="Run held-out BEAST adapter comparison")
    parser.add_argument("--live-ollama", action="store_true")
    parser.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    parser.add_argument("--skip-loaded-lora", action="store_true", help="Do not execute the local PEFT LoRA runtime lane")
    parser.add_argument("--live-cloud", action="store_true", help="Run BEAST_CLOUD_PROVIDER_COMMAND as the external fallback lane")
    args = parser.parse_args()
    report = AdapterComparisonGauntlet().run(
        live_ollama=bool(args.live_ollama),
        ollama_host=str(args.ollama_host),
        run_loaded_lora=not bool(args.skip_loaded_lora),
        live_cloud=bool(args.live_cloud),
    )
    latest = Path("benchmarks/results/heldout_adapter_comparison_latest.json")
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
