"""Typed compound patch fragments for Direct Coder.

The module is deliberately mutation-free. It composes independently produced
legacy family plans into one validated plan that the existing Direct Coder
tool path may execute.

Rules:
* every write is bound to a relative repository path;
* independent non-overlapping fragments compose directly;
* overlapping fragment writes are refused unless an explicit merge node
  resolves that exact path;
* merge outputs are provenance-bound to all contributing fragments;
* this layer never writes to the worktree itself.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence


class CompoundFragmentError(ValueError):
    """Fail-closed compound fragment admission error."""


def canonical_digest(value: Any) -> str:
    body = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _safe_path(value: str) -> str:
    path = PurePosixPath(str(value or ""))
    if (
        not str(value or "")
        or path.is_absolute()
        or ".." in path.parts
        or "." == str(path)
    ):
        raise CompoundFragmentError(f"unsafe patch path: {value!r}")
    return str(path)


@dataclass(frozen=True)
class CompoundFragment:
    fragment_id: str
    producer: str
    provenance_lane: str
    rewrite: Mapping[str, str]
    edits: tuple[Mapping[str, Any], ...]
    requires: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        row = {
            "fragment_id": self.fragment_id,
            "producer": self.producer,
            "provenance_lane": self.provenance_lane,
            "rewrite": dict(self.rewrite),
            "edits": [dict(edit) for edit in self.edits],
            "requires": list(self.requires),
        }
        row["fragment_digest"] = canonical_digest(row)
        return row

    @property
    def paths(self) -> tuple[str, ...]:
        paths = set(self.rewrite)
        paths.update(str(edit["path"]) for edit in self.edits)
        return tuple(sorted(paths))


@dataclass(frozen=True)
class MergeNode:
    path: str
    input_fragment_ids: tuple[str, ...]
    rewrite: str | None = None
    edits: tuple[Mapping[str, Any], ...] = ()
    merge_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        path = _safe_path(self.path)
        if bool(self.rewrite is not None) == bool(self.edits):
            raise CompoundFragmentError(
                "merge node must provide exactly one of rewrite or edits"
            )
        if len(set(self.input_fragment_ids)) < 2:
            raise CompoundFragmentError(
                "merge node requires at least two distinct fragment inputs"
            )

        row = {
            "merge_id": self.merge_id or (
                "merge:" + canonical_digest({
                    "path": path,
                    "inputs": list(self.input_fragment_ids),
                }).split(":", 1)[1][:24]
            ),
            "path": path,
            "input_fragment_ids": list(self.input_fragment_ids),
            "rewrite": self.rewrite,
            "edits": [dict(edit) for edit in self.edits],
        }
        row["merge_digest"] = canonical_digest(row)
        return row


def fragment_from_legacy_plan(
    plan: Mapping[str, Any],
    *,
    fragment_id: str,
    producer: str,
    provenance_lane: str,
    requires: Sequence[str] = (),
) -> CompoundFragment:
    """Seal one existing family/resolver plan as a typed fragment."""
    rewrite: dict[str, str] = {}
    for raw_path, content in dict(plan.get("rewrite") or {}).items():
        path = _safe_path(str(raw_path))
        if not isinstance(content, str):
            raise CompoundFragmentError("rewrite content must be text")
        rewrite[path] = content

    edits: list[dict[str, Any]] = []
    for raw in plan.get("edits") or ():
        edit = dict(raw)
        path = _safe_path(str(edit.get("path") or ""))
        edit["path"] = path
        edits.append(edit)

    rewrite_paths = set(rewrite)
    edit_paths = {str(edit["path"]) for edit in edits}
    overlap = rewrite_paths & edit_paths
    if overlap:
        raise CompoundFragmentError(
            "one fragment cannot mix rewrite and structured edits for "
            + ",".join(sorted(overlap))
        )

    if not rewrite and not edits:
        raise CompoundFragmentError("fragment contains no writes")

    fragment = CompoundFragment(
        fragment_id=str(fragment_id),
        producer=str(producer),
        provenance_lane=str(provenance_lane),
        rewrite=rewrite,
        edits=tuple(edits),
        requires=tuple(str(item) for item in requires),
    )
    fragment.to_dict()
    return fragment


def compose_fragments(
    fragments: Sequence[CompoundFragment],
    *,
    merge_nodes: Sequence[MergeNode] = (),
) -> dict[str, Any]:
    """Compose fragments into the legacy plan shape Direct Coder already executes."""
    if not fragments:
        raise CompoundFragmentError("compound plan requires fragments")

    ids = [fragment.fragment_id for fragment in fragments]
    if len(set(ids)) != len(ids):
        raise CompoundFragmentError("duplicate fragment id")

    by_path: dict[str, list[CompoundFragment]] = {}
    for fragment in fragments:
        for path in fragment.paths:
            by_path.setdefault(path, []).append(fragment)

    merges: dict[str, dict[str, Any]] = {}
    for merge in merge_nodes:
        row = merge.to_dict()
        path = row["path"]
        if path in merges:
            raise CompoundFragmentError(f"duplicate merge node for {path}")
        merges[path] = row

    overlaps = {
        path: producers
        for path, producers in by_path.items()
        if len(producers) > 1
    }

    for path, producers in overlaps.items():
        merge = merges.get(path)
        if merge is None:
            raise CompoundFragmentError(
                f"overlapping fragment writes require explicit merge node: {path}"
            )

        expected = {fragment.fragment_id for fragment in producers}
        supplied = set(merge["input_fragment_ids"])
        if supplied != expected:
            raise CompoundFragmentError(
                f"merge provenance mismatch for {path}"
            )

    extra_merges = set(merges) - set(overlaps)
    if extra_merges:
        raise CompoundFragmentError(
            "merge node supplied for non-overlapping path: "
            + ",".join(sorted(extra_merges))
        )

    rewrite: dict[str, str] = {}
    edits: list[dict[str, Any]] = []

    for path in sorted(by_path):
        producers = by_path[path]

        if len(producers) > 1:
            merge = merges[path]
            if merge["rewrite"] is not None:
                rewrite[path] = str(merge["rewrite"])
            else:
                for edit in merge["edits"]:
                    row = dict(edit)
                    row["path"] = path
                    edits.append(row)
            continue

        fragment = producers[0]
        if path in fragment.rewrite:
            rewrite[path] = fragment.rewrite[path]
        else:
            edits.extend(
                dict(edit)
                for edit in fragment.edits
                if str(edit["path"]) == path
            )

    fragment_rows = [fragment.to_dict() for fragment in fragments]
    merge_rows = [merges[path] for path in sorted(merges)]

    legacy_plan = {
        "rewrite": rewrite,
        "edits": edits,
    }

    body = {
        "beast_object_type": "DIRECT_CODER_COMPOUND_PATCH_PLAN",
        "version": "1.0",
        "fragments": fragment_rows,
        "merges": merge_rows,
        "paths": sorted(by_path),
        "provenance_lanes": sorted({
            fragment.provenance_lane
            for fragment in fragments
        }),
        "dependency_edges": sorted({
            f"{required}->{fragment.fragment_id}"
            for fragment in fragments
            for required in fragment.requires
        }),
        "legacy_plan": legacy_plan,
    }

    body["plan_digest"] = canonical_digest(body)
    return body
