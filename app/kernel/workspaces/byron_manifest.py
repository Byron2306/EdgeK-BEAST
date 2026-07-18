"""Inherited `.byron` policy and exclusion manifests."""
from __future__ import annotations
from pathlib import Path
import yaml

DEFAULT_EXCLUSIONS={".git",".venv","venv","node_modules","data","logs",".beast"}
MANIFEST_FILES=("project.yaml","services.yaml","tools.yaml","workloads.yaml","policy.yaml")
def load(root: str | Path) -> dict:
    root=Path(root).resolve(); chain=[]; current=root
    while current != current.parent:
        directory=current/'.byron'
        if directory.is_dir(): chain.append(directory)
        current=current.parent
    result={"exclusions":sorted(DEFAULT_EXCLUSIONS),"manifests":[]}
    for directory in reversed(chain):
        for name in MANIFEST_FILES:
            path=directory/name
            if not path.exists(): continue
            data=yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data,dict): raise ValueError(f"manifest must be a mapping: {path}")
            result["manifests"].append(str(path))
            result["exclusions"]=sorted(set(result["exclusions"]) | set(data.get("exclusions") or []))
            key=name.removesuffix(".yaml")
            if name=="project.yaml":
                for field in ("family","canonical_repo"):
                    if field in data: result[field]=data[field]
            else:
                current_value=result.get(key,{})
                result[key]={**current_value,**data}
    return result
