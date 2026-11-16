"""Experimental Task 1: real context compression tiers, routed through the Compute Governor (default-off).

Tiers
- ``repo_map``: RepoRelay-style AST symbol map ranked by import in-degree and focus relevance, packed to budget.
- ``longcodezip``: LongCodeZip-style coarse (function-level) selection by query relevance; non-selected bodies
  become signature stubs; edit targets stay byte-exact.
- ``rtk`` / ``sqz``: the real binaries only when on PATH *and* identified by a ``--version`` probe; otherwise the
  BEAST native stand-ins run and report ``ready=false, real_tool=false`` (never falsely ready).

Claim boundary: token counts are chars/4 estimates (labelled); savings count only when the fidelity check passes
(IEI v0.9 runtime contract: no compute saving counts unless verification quality is preserved). The repo-map and
LongCodeZip tiers are BEAST-native implementations of the published ideas, not the upstream tools.
"""
from __future__ import annotations

import ast
import hashlib
import math
import os
import re
import shutil
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

TIERS_ENV = "BEAST_COMPRESSION_TIERS"
TIERS = ("repo_map", "longcodezip", "rtk", "sqz")
TOKEN_KIND = "estimated_chars_div_4"
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".beast", ".mypy_cache", ".pytest_cache",
             "dist", "build"}
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
STUB_MARK = "# [beast-lcz: body elided"


def tiers_enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get(TIERS_ENV, "")).strip().lower() in {"1", "true", "yes", "on"}


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text or "") / 4)


def measure(original: str, compressed: str, *, fidelity_passed: bool) -> dict[str, Any]:
    before, after = estimate_tokens(original), estimate_tokens(compressed)
    saved = max(0, before - after)
    return {"original_tokens": before, "compressed_tokens": after, "token_count_kind": TOKEN_KIND,
            "savings_tokens": saved, "savings_ratio": round(saved / before, 4) if before else 0.0,
            "counted_savings_tokens": saved if fidelity_passed else 0, "fidelity_passed": bool(fidelity_passed)}


# -- detection -----------------------------------------------------------------------------------------------
def _probe(name: str, path: str) -> tuple[bool, str]:
    try:
        done = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    first = (done.stdout or done.stderr or "").strip().splitlines()
    version = first[0].strip() if first else ""
    return bool(done.returncode == 0 and re.match(rf"^\s*{re.escape(name)}\b", version, re.I)), version


def detect_compressors(env: Mapping[str, str] | None = None) -> dict[str, dict[str, Any]]:
    env = os.environ if env is None else env
    search = env.get("PATH", "")
    status: dict[str, dict[str, Any]] = {}
    for name in ("rtk", "sqz", "longcodezip", "reporelay"):
        path = shutil.which(name, path=search)
        identified, version = _probe(name, path) if path else (False, "")
        native = name in {"longcodezip", "reporelay"}
        entry = {"binary_path": path, "version": version, "real_tool": identified,
                 "ready": identified or native,
                 "implementation": "upstream_binary" if identified else ("beast_native" if native else "native_stub"),
                 "fallback": "beast_native"}
        if not identified:
            entry["reason"] = "binary_identity_unverified" if path else "binary_not_on_path"
        status[name] = entry
    return status


# -- repo map ----------------------------------------------------------------------------------------------
def _signature(node: ast.AST) -> str:
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(ast.unparse(b) for b in node.bases)
        return f"class {node.name}({bases})" if bases else f"class {node.name}"
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({ast.unparse(node.args)}){returns}"


def _python_files(root: Path, limit: int = 2000) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for filename in sorted(filenames):
            if filename.endswith(".py"):
                found.append(Path(dirpath) / filename)
                if len(found) >= limit:
                    return found
    return found


def _module_targets(rel: str, node: ast.AST) -> list[str]:
    names: list[str] = []
    if isinstance(node, ast.Import):
        names = [a.name for a in node.names]
    elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
        names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
    return names


def repo_map(root: str | Path, *, focus: Iterable[str] = (), budget_tokens: int = 1024,
             max_symbols_per_file: int = 12) -> dict[str, Any]:
    root = Path(root)
    focus_terms = [t.lower() for t in focus if str(t).strip()]
    files = _python_files(root)
    rel_of = {f: f.relative_to(root).as_posix() for f in files}
    module_to_rel = {}
    for rel in rel_of.values():
        module = rel[:-3].replace("/", ".")
        module_to_rel[module.removesuffix(".__init__")] = rel
    indegree: dict[str, int] = dict.fromkeys(rel_of.values(), 0)
    symbols: dict[str, list[dict[str, Any]]] = {}
    sources: dict[str, str] = {}
    for f, rel in rel_of.items():
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except (SyntaxError, ValueError, OSError):
            continue
        sources[rel] = text
        targets: set[str] = set()
        rows: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            for module in _module_targets(rel, node):
                hit = module_to_rel.get(module)
                if hit and hit != rel:
                    targets.add(hit)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                rows.append({"name": node.name, "line": node.lineno, "signature": _signature(node)})
                if isinstance(node, ast.ClassDef):
                    for child in node.body:
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            rows.append({"name": f"{node.name}.{child.name}", "line": child.lineno,
                                         "signature": "  " + _signature(child)})
        symbols[rel] = rows
        for target in targets:
            indegree[target] = indegree.get(target, 0) + 1

    def score(rel: str) -> float:
        names = " ".join(s["name"].lower() for s in symbols.get(rel, ())) + " " + rel.lower()
        return indegree.get(rel, 0) + 3.0 * sum(1 for t in focus_terms if t in names)

    ranked = sorted((rel for rel in symbols if symbols[rel]), key=lambda r: (-score(r), r))
    entries, lines, used = [], [], 0
    for rel in ranked:
        header = f"{rel}:"
        if used + estimate_tokens(header + "\n") > budget_tokens and entries:
            break
        kept = []
        used += estimate_tokens(header + "\n")
        ordered = sorted(symbols[rel], key=lambda s: (not any(t in s["name"].lower() for t in focus_terms),
                                                      s["line"]))[:max_symbols_per_file]
        for sym in sorted(ordered, key=lambda s: s["line"]):
            row = f"  L{sym['line']} {sym['signature'].strip()}"
            cost = estimate_tokens(row + "\n")
            if used + cost > budget_tokens:
                break
            kept.append(sym)
            lines_row = row
            used += cost
            lines.append((rel, lines_row))
        entries.append({"file": rel, "score": score(rel), "indegree": indegree.get(rel, 0), "symbols": kept})
        if used >= budget_tokens:
            break
    content_lines: list[str] = []
    for entry in entries:
        content_lines.append(f"{entry['file']}:")
        content_lines.extend(row for rel, row in lines if rel == entry["file"])
    content = "\n".join(content_lines)
    checked, failures = 0, []
    for entry in entries:
        src_lines = sources[entry["file"]].splitlines()
        for sym in entry["symbols"]:
            checked += 1
            leaf = sym["name"].split(".")[-1]
            if not (0 < sym["line"] <= len(src_lines)) or leaf not in src_lines[sym["line"] - 1]:
                failures.append(f"{entry['file']}:{sym['line']}:{sym['name']}")
    fidelity = {"passed": not failures and checked > 0, "symbols_checked": checked, "failures": failures,
                "check": "every symbol resolves to its source line"}
    original = "\n".join(sources[e["file"]] for e in entries) if entries else ""
    full = "\n".join(sources.values())
    metrics = measure(full, content, fidelity_passed=fidelity["passed"])
    metrics["files_scanned"] = len(files)
    metrics["files_in_map"] = len(entries)
    metrics["mapped_files_tokens"] = estimate_tokens(original)
    return {"tier": "repo_map", "implementation": "beast_native_reporelay_style", "real_tool": False,
            "entries": entries, "content": content, "metrics": metrics, "fidelity": fidelity}


# -- LongCodeZip-style -----------------------------------------------------------------------------------
def _idents(text: str) -> set[str]:
    out: set[str] = set()
    for word in IDENT_RE.findall(text):
        low = word.lower()
        out.add(low)
        out.update(part for part in low.split("_") if len(part) > 2)
    return out


def _units(tree: ast.Module) -> list[ast.AST]:
    units: list[ast.AST] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            units.append(node)
        elif isinstance(node, ast.ClassDef):
            units.extend(c for c in node.body if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef)))
    return units


def long_code_compress(code: str, *, query: str = "", budget_ratio: float = 0.5,
                       edit_targets: Iterable[str] = ()) -> dict[str, Any]:
    targets = {str(t) for t in edit_targets if str(t).strip()}
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError) as exc:
        fidelity = {"passed": False, "reason": f"source_unparseable:{type(exc).__name__}"}
        return {"tier": "longcodezip", "implementation": "beast_native_longcodezip_style", "real_tool": False,
                "content": code, "fidelity": fidelity, "metrics": measure(code, code, fidelity_passed=False),
                "kept": [], "stubbed": []}
    lines = code.splitlines(keepends=True)
    query_ids = _idents(query)
    budget = max(1, int(len(code) * max(0.05, min(1.0, budget_ratio))))
    scored = []
    for unit in _units(tree):
        start = (unit.decorator_list[0].lineno if unit.decorator_list else unit.lineno)
        segment = "".join(lines[start - 1:unit.end_lineno])
        name_ids = _idents(unit.name)
        relevance = 3 * len(name_ids & query_ids) + len(_idents(segment) & query_ids)
        body_lines = unit.end_lineno - unit.body[0].lineno + 1
        forced = unit.name in targets
        scored.append({"node": unit, "start": start, "segment": segment, "score": relevance,
                       "forced": forced, "small": body_lines <= 2})
    kept_size = len(code) - sum(len(s["segment"]) for s in scored)
    keep: set[int] = set()
    for item in sorted(scored, key=lambda s: (not s["forced"], -s["score"], s["start"])):
        if item["forced"] or item["small"] or (item["score"] > 0 and kept_size + len(item["segment"]) <= budget):
            keep.add(id(item["node"]))
            kept_size += len(item["segment"])
    out_lines = list(lines)
    stubbed = []
    for item in sorted(scored, key=lambda s: -s["start"]):
        node = item["node"]
        if id(node) in keep:
            continue
        first_body = node.body[0]
        doc_end = None
        if isinstance(first_body, ast.Expr) and isinstance(getattr(first_body, "value", None), ast.Constant) \
                and isinstance(first_body.value.value, str):
            doc_end = first_body.end_lineno
        body_start = doc_end + 1 if doc_end else first_body.lineno
        if body_start > node.end_lineno:
            continue
        indent = re.match(r"\s*", lines[first_body.lineno - 1]).group(0)
        elided = node.end_lineno - body_start + 1
        stub = f"{indent}...  {STUB_MARK} {elided} lines]\n"
        out_lines[body_start - 1:node.end_lineno] = [stub]
        stubbed.append(node.name)
    content = "".join(out_lines)
    failures: list[str] = []
    try:
        ast.parse(content)
    except SyntaxError as exc:
        failures.append(f"output_unparseable:{exc.msg}")
    for item in scored:
        if id(item["node"]) in keep and item["segment"] not in content:
            failures.append(f"kept_not_exact:{item['node'].name}")
        if not re.search(rf"\bdef {re.escape(item['node'].name)}\(", content):
            failures.append(f"signature_lost:{item['node'].name}")
    for ident in query_ids:
        if re.search(rf"\b{re.escape(ident)}\b", code) and not re.search(rf"\b{re.escape(ident)}\b", content):
            failures.append(f"query_identifier_lost:{ident}")
    fidelity = {"passed": not failures, "failures": failures,
                "check": "parses; kept units byte-exact; all signatures kept; query identifiers preserved"}
    if failures:
        content = code
    return {"tier": "longcodezip", "implementation": "beast_native_longcodezip_style", "real_tool": False,
            "content": content, "fidelity": fidelity,
            "metrics": measure(code, content, fidelity_passed=fidelity["passed"]),
            "kept": [s["node"].name for s in scored if id(s["node"]) in keep], "stubbed": stubbed}


# -- sqz native stand-in -------------------------------------------------------------------------------------
SQZ_ARGS = ("compress", "--no-cache", "--no-abbrev")
SQZ_FORMATTER = {"test": "pytest", "lint": "ruff", "log": "log"}  # sqz per-command formatter label


def _sqz_env() -> dict[str, str]:
    """Isolated sqz state: no dedup refs, its SQLite DB under a private temp dir (never the user's ~/.sqz)."""
    import tempfile

    root = Path(tempfile.gettempdir()) / f"beast-sqz-{os.getuid()}"
    root.mkdir(mode=0o700, exist_ok=True)
    return {**os.environ, "SQZ_DB_PATH": str(root / "session.db"), "SQZ_NO_DEDUP": "1"}


def _sqz(text: str, status: Mapping[str, Any], kind: str = "log") -> dict[str, Any]:
    from app.kernel.data_processing.cascade_output_compressor import exact_lines

    if status.get("real_tool") and status.get("binary_path"):
        out = ""
        try:
            done = subprocess.run([status["binary_path"], *SQZ_ARGS, "--cmd", SQZ_FORMATTER.get(kind, "log")], input=text, capture_output=True, text=True,
                                  timeout=20, check=False, env=_sqz_env())
            out = done.stdout if done.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            out = ""
        if out.strip():
            required = exact_lines(text)
            missing = [line for line in required if line not in out]
            return {"content": out if not missing else text, "backend": "sqz_binary",
                    "fidelity": {"passed": not missing, "missing": len(missing), "required": len(required),
                                 "check": "failure/error lines, file:line locations and traceback frames byte-exact"}}
    rows, previous, run = [], None, 0
    for line in [ln.rstrip() for ln in text.splitlines() if ln.strip()] + [None]:
        if line == previous:
            run += 1
            continue
        if previous is not None:
            rows.append(previous if run == 1 else f"{previous}  # [repeated {run}x]")
        previous, run = line, 1
    out = "\n".join(rows)
    unique = {ln.rstrip() for ln in text.splitlines() if ln.strip()}
    missing = [ln for ln in unique if ln not in out]
    return {"content": out if not missing else text, "backend": "beast_native_sqz_stub",
            "fidelity": {"passed": not missing, "check": "every distinct non-blank line retained",
                         "missing": len(missing)}}


# -- governor routing ---------------------------------------------------------------------------------------
class CompressionTierRouter:
    """Every tier call is a Compute Governor ``deterministic_tool`` proposal executed only behind admit."""

    def __init__(self, *, governor: Any, env: Mapping[str, str] | None = None):
        self.governor = governor
        self.env = dict(os.environ if env is None else env)

    def compress(self, tier: str, payload: str, *, query: str = "", edit_targets: Iterable[str] = (),
                 budget_ratio: float = 0.5, budget_tokens: int = 1024, kind: str = "test") -> dict[str, Any]:
        from app.kernel.governance.governor_spine import Episode, Proposal

        if not tiers_enabled(self.env):
            raise PermissionError(f"compression tiers are disabled (set {TIERS_ENV}=1)")
        if tier not in TIERS:
            raise ValueError(f"unknown compression tier: {tier}")
        payload_sha = "sha256:" + hashlib.sha256(str(payload).encode()).hexdigest()
        proposal = Proposal(kind="deterministic_tool", lane="agent", tool_id=f"compression_tier:{tier}",
                            signature_material={"tier": tier, "payload": payload_sha, "query": query},
                            estimate={"tool_calls": 1.0})
        decision = self.governor.admit(Episode(run_id=f"compression:{tier}:{payload_sha[7:19]}"), proposal)
        status = detect_compressors(self.env)
        targets = list(edit_targets)

        def run() -> dict[str, Any]:
            if tier == "repo_map":
                return repo_map(payload, focus=IDENT_RE.findall(query), budget_tokens=budget_tokens)
            if tier == "longcodezip":
                return long_code_compress(payload, query=query, budget_ratio=budget_ratio, edit_targets=targets)
            if tier == "rtk":
                from app.kernel.data_processing.cascade_output_compressor import compress_cascade_output

                out = compress_cascade_output(payload, kind=kind, edit_targets=targets)
                safe = bool(out["safe"])
                return {"tier": "rtk", "content": out["content"], "backend": out["backend"],
                        "real_tool": out["backend"] == "rtk_binary" and status["rtk"]["real_tool"],
                        "fidelity": {"passed": safe, "check": "failing assertions/locations/edit targets exact"},
                        "metrics": measure(payload, out["content"], fidelity_passed=safe)}
            out = _sqz(payload, status["sqz"], kind)
            return {"tier": "sqz", "content": out["content"], "backend": out["backend"],
                    "real_tool": out["backend"] == "sqz_binary", "fidelity": out["fidelity"],
                    "metrics": measure(payload, out["content"], fidelity_passed=out["fidelity"]["passed"])}

        result = self.governor.run_admitted(decision, proposal, run)
        result["governor"] = {"outcome": decision.outcome, "receipt_id": decision.receipt_id,
                              "receipt_hash": decision.receipt_hash, "reasons": list(decision.reasons)}
        result["detection"] = {k: {"ready": v["ready"], "real_tool": v["real_tool"]} for k, v in status.items()}
        return result


_DEFAULT_ROUTER: CompressionTierRouter | None = None


def default_router() -> CompressionTierRouter:
    global _DEFAULT_ROUTER
    if _DEFAULT_ROUTER is None:
        from app.kernel.governance.governor_spine import ComputeGovernorSpine

        _DEFAULT_ROUTER = CompressionTierRouter(governor=ComputeGovernorSpine())
    _DEFAULT_ROUTER.env = dict(os.environ)
    return _DEFAULT_ROUTER


__all__ = ["TIERS", "TIERS_ENV", "CompressionTierRouter", "default_router", "detect_compressors",
           "estimate_tokens", "long_code_compress", "measure", "repo_map", "tiers_enabled"]
