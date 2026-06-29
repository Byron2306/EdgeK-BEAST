#!/usr/bin/env python3
"""Summarize Proof-Local Compute phase implementation status."""

from __future__ import annotations

import json
import re
from pathlib import Path


DOC = Path("docs/beast-proof-local-compute-integration-proposal.md")


def main() -> int:
    text = DOC.read_text(encoding="utf-8")
    phases = []
    matches = list(re.finditer(r"^### Phase (\d+): (.+)$", text, flags=re.MULTILINE))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end]
        status_match = re.search(r"Status:\s*\*\*(.+?)\*\*", body)
        status = status_match.group(1) if status_match else "pending"
        implemented = "implemented" in status.lower()
        phases.append({
            "phase": int(match.group(1)),
            "name": match.group(2).strip(),
            "status": status,
            "implemented": implemented,
            "next_action": "maintain_and_harden" if implemented else "implement_and_exercise",
        })
    report = {
        "beast_object_type": "proof_local_phase_backlog",
        "version": "1.0",
        "implemented": sum(1 for p in phases if p["implemented"]),
        "pending": sum(1 for p in phases if not p["implemented"]),
        "phases": phases,
    }
    out = Path("benchmarks/results/crystal_to_adapter_distillation/proof_local_phase_backlog_latest.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

