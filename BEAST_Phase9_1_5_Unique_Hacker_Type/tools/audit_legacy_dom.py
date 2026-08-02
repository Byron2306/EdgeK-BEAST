#!/usr/bin/env python3
from pathlib import Path
import re, sys, json

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
html = next((p for p in [root/"index.html", root/"index-v2.html"] if p.exists()), None)
if not html:
    raise SystemExit("No index.html or index-v2.html found")
text = html.read_text(encoding="utf-8", errors="ignore")
ids = re.findall(r'\bid=["\']([^"\']+)', text)
panels = re.findall(r'\bdata-page-panel=["\']([^"\']+)', text)
dupe_ids = sorted({x for x in ids if ids.count(x) > 1})
print(json.dumps({
    "html": str(html),
    "id_count": len(ids),
    "duplicate_ids": dupe_ids,
    "legacy_page_panel_count": len(panels),
    "page_panel_counts": {x: panels.count(x) for x in sorted(set(panels))}
}, indent=2))
