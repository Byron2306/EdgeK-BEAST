#!/usr/bin/env python3
"""Hydrate ignored BEAST UI runtime state from the tracked JSON seed."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Hydrate BEAST UI runtime seed")
    parser.add_argument("--seed", default=str(ROOT / "seeds" / "ui_runtime"))
    parser.add_argument("--copy-spaces", action="store_true", help="Copy safe seeded Compute Space artifacts into data/commons_spaces")
    args = parser.parse_args()

    seed = Path(args.seed)
    manifest = _read_json(seed / "manifest.json")
    if manifest.get("beast_object_type") != "beast_ui_runtime_seed_manifest":
        raise SystemExit(f"Missing UI runtime seed manifest: {seed / 'manifest.json'}")

    result: Dict[str, Any] = {
        "beast_object_type": "beast_ui_runtime_seed_hydration",
        "version": "1.0",
        "seed": str(seed),
        "manifest_counts": manifest.get("counts") or {},
        "written": [],
        "copied_spaces": 0,
    }

    write_chronicles(seed, result)
    write_kv_metadata(seed, result)
    if args.copy_spaces:
        result["copied_spaces"] = copy_spaces(seed / "commons_spaces", ROOT / "data" / "commons_spaces")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def write_chronicles(seed: Path, result: Dict[str, Any]) -> None:
    payload = _read_json(seed / "chronicles.json")
    rows = payload.get("chronicles") if isinstance(payload.get("chronicles"), list) else []
    target = ROOT / "app" / "data" / "evidence_chronicles"
    target.mkdir(parents=True, exist_ok=True)
    written = 0
    for idx, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            continue
        chronicle_id = str(row.get("chronicle_id") or row.get("task_id") or f"seed_{idx}")
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in chronicle_id)[:96]
        out = dict(row)
        out.setdefault("chronicle_type", row.get("chronicle_type") or "seeded_chronicle_summary")
        out.setdefault("seeded_ui_runtime", True)
        (target / f"{safe}.json").write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        written += 1
    if written:
        result["written"].append({"path": str(target), "records": written})


def write_kv_metadata(seed: Path, result: Dict[str, Any]) -> None:
    payload = _read_json(seed / "kv_cache_state.json")
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    target = ROOT / "data" / "kv_cache"
    target.mkdir(parents=True, exist_ok=True)
    if not state:
        return
    block = {
        "beast_object_type": "kv_cache_block",
        "block_id": "seeded_ui_runtime_kv_cache",
        "engine": "seeded_ui_runtime",
        "model": "seeded-ui-runtime",
        "tokenizer": "seeded-ui-runtime",
        "prompt_hash": "seeded-ui-runtime",
        "size_bytes": int(state.get("total_size_bytes") or 0),
        "compressed": bool(state.get("compressed_blocks")),
        "compression_ratio": 1.0,
        "location": "storage",
        "access_count": int(state.get("operations_logged") or 0),
        "pinned": True,
        "metadata": {
            "source": "ui_runtime_seed",
            "total_blocks": state.get("total_blocks"),
            "display_only": True,
        },
    }
    (target / "seeded_ui_runtime_kv_cache.json").write_text(json.dumps(block, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result["written"].append({"path": str(target / "seeded_ui_runtime_kv_cache.json"), "records": 1})


def copy_spaces(source: Path, target: Path) -> int:
    if not source.is_dir():
        return 0
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for item in source.iterdir():
        if not item.is_dir():
            continue
        dst = target / item.name
        if dst.exists():
            continue
        shutil.copytree(item, dst)
        copied += 1
    return copied


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
