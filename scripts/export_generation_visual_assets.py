#!/usr/bin/env python3
"""Export promoted BEAST visual-region assets as raw RGBA plus PNG previews."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.residual_contracts import sha256_digest, utc_now_iso


def export_visual_assets(
    *,
    state_root: str | Path,
    output_root: str | Path = REPO_ROOT / "artifacts" / "generation-visual-assets",
    scale: int = 32,
) -> dict[str, Any]:
    state = Path(state_root)
    source = state / "visual_assets"
    index_path = source / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"visual asset index not found: {index_path}")
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)
    rows = json.loads(index_path.read_text(encoding="utf-8"))
    exported = []
    for row in rows:
        asset = dict(row.get("asset") or {})
        width = int(asset.get("width") or 0)
        height = int(asset.get("height") or 0)
        asset_id = str(asset.get("asset_id") or "")
        if width <= 0 or height <= 0 or not asset_id:
            continue
        source_path = Path(str(row.get("source_path") or source / (asset_id + ".rgba")))
        if not source_path.exists():
            source_path = source / (asset_id.replace(":", "_") + ".rgba")
        raw = source_path.read_bytes()
        if len(raw) != width * height * 4:
            raise ValueError(f"{source_path} size {len(raw)} does not match {width}x{height} RGBA")
        safe = asset_id.replace(":", "_")
        raw_out = output / f"{safe}.rgba"
        png_out = output / f"{safe}.png"
        preview_out = output / f"{safe}.preview-{width * scale}x{height * scale}.png"
        shutil.copyfile(source_path, raw_out)
        _write_png(raw, width=width, height=height, path=png_out, scale=1)
        _write_png(raw, width=width, height=height, path=preview_out, scale=scale)
        exported.append({
            "asset_id": asset_id,
            "asset_digest": asset.get("digest"),
            "raw_path": str(raw_out),
            "png_path": str(png_out),
            "preview_path": str(preview_out),
            "width": width,
            "height": height,
            "observation_count": int(row.get("observation_count") or 0),
            "source_lanes": list(row.get("source_lanes") or []),
            "quality_receipt_digest": row.get("quality_receipt_digest"),
            "intent_receipt_digest": row.get("intent_receipt_digest"),
            "perceptual_receipt_digest": row.get("perceptual_receipt_digest"),
        })
    manifest = {
        "beast_object_type": "generation_visual_asset_export",
        "version": "1.0",
        "exported_at": utc_now_iso(),
        "state_root": str(state),
        "source_index": str(index_path),
        "asset_count": len(exported),
        "assets": exported,
    }
    manifest["export_digest"] = sha256_digest(manifest)
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    markdown_path = output / "README.md"
    markdown_path.write_text(_markdown(manifest), encoding="utf-8")
    return {**manifest, "manifest_path": str(manifest_path), "markdown_path": str(markdown_path)}


def _write_png(raw: bytes, *, width: int, height: int, path: Path, scale: int) -> None:
    from PIL import Image

    image = Image.frombytes("RGBA", (width, height), raw)
    if scale > 1:
        image = image.resize((width * scale, height * scale), Image.Resampling.NEAREST)
    image.save(path, format="PNG")


def _markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# BEAST generation visual asset export",
        "",
        f"- Export digest: `{manifest['export_digest']}`",
        f"- Source state root: `{manifest['state_root']}`",
        f"- Asset count: {manifest['asset_count']}",
        "",
    ]
    for asset in manifest["assets"]:
        lines.extend([
            f"## {asset['asset_id']}",
            "",
            f"- PNG: `{Path(asset['png_path']).name}`",
            f"- Preview: `{Path(asset['preview_path']).name}`",
            f"- Raw RGBA: `{Path(asset['raw_path']).name}`",
            f"- Size: {asset['width']}×{asset['height']}",
            f"- Observations: {asset['observation_count']}",
            f"- Source lanes: `{asset['source_lanes']}`",
            f"- Quality receipt: `{asset['quality_receipt_digest']}`",
            f"- Intent receipt: `{asset['intent_receipt_digest']}`",
            f"- Perceptual receipt: `{asset['perceptual_receipt_digest']}`",
            "",
        ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", default=".beast/state/generation_gauntlets_guardian_handoff_live")
    parser.add_argument("--output-root", default="artifacts/generation-visual-assets")
    parser.add_argument("--scale", type=int, default=32)
    args = parser.parse_args()
    result = export_visual_assets(state_root=args.state_root, output_root=args.output_root, scale=args.scale)
    print(json.dumps({
        "manifest_path": result["manifest_path"],
        "markdown_path": result["markdown_path"],
        "asset_count": result["asset_count"],
        "export_digest": result["export_digest"],
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
