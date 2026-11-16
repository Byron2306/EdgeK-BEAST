"""Multi-family coding crystals (experimental, default-off ``BEAST_FAMILY_CRYSTALS``).

The reviewed v1 coding catalog only knows ``repair.resolve_constant``. This module adds a *separate* reviewed
catalog (``beast.coding_opcodes.families.v1``) so the v1 catalog digest -- and every crystal already promoted
against it -- is untouched. Each family has one deterministic, model-free resolver:

* ``repair.resolve_constant`` -- unittest literal mismatch -> module constant (delegates to coding_crystals)
* ``repair.operator_swap``    -- one arithmetic/boolean operator mutation that strictly reduces failing tests
* ``repair.boundary_shift``   -- one off-by-one mutation (``<``/``<=``, ``range`` stop, ``± 1``) that reduces failures
* ``repair.guard_exception``  -- wrap the raising ``return`` in the target with ``except <Exc>: return <expected>``
* ``repair.rename_symbol``    -- ``cannot import name NEW`` -> rename the unique token-matching symbol repo-wide
* ``toolchain.resolve_declared`` + ``toolchain.run_declared`` -- run the repo-declared regenerator under ``tools/``

A crystal is a recipe over these opcodes; replay derives every edit from the *observed* failure and the repo, never
from crystal text. Mutation resolvers pick the unique candidate that strictly reduces failures, probing scratch
copies. Similarity only nominates; the verifier (expect fail -> pass) grants nothing until it passes. Composites
(lattice) chain two promoted children with intermediate ``improve`` verifications.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from app.kernel.compute.coding_crystals import _spec, resolve_constant
from app.kernel.compute.typed_crystal_ir import OpcodeRegistry

FAMILY_ENV = "BEAST_FAMILY_CRYSTALS"
CATALOG_VERSION = "beast.coding_opcodes.families.v1"
KIND = "family_crystal"
MAX_CANDIDATES = 80

FAMILIES: dict[str, dict[str, str]] = {
    "fix-config-constant": {"resolver": "repair.resolve_constant", "actuator": "worktree.apply_plan",
                            "signature": r"^AssertionError: .+ != .+$"},
    "fix-logic-operator": {"resolver": "repair.operator_swap", "actuator": "worktree.apply_plan",
                           "signature": r"^AssertionError: "},
    "fix-off-by-one": {"resolver": "repair.boundary_shift", "actuator": "worktree.apply_plan",
                       "signature": r"^AssertionError: "},
    "fix-unhandled-exception": {"resolver": "repair.guard_exception", "actuator": "worktree.apply_plan",
                                "signature": r"^(?:ZeroDivisionError|ValueError|KeyError|IndexError): "},
    "refactor-rename-symbol": {"resolver": "repair.rename_symbol", "actuator": "worktree.apply_plan",
                               "signature": r"ImportError: cannot import name '\w+' from '[\w.]+'"},
    "toolchain-regenerate": {"resolver": "toolchain.resolve_declared", "actuator": "toolchain.run_declared",
                             "signature": r"stale: run tools/[\w/]+\.py"},
}
# data-shaped errors only; NotImplementedError/TypeError/AttributeError are real bugs, never guarded
GUARDABLE = ("ZeroDivisionError", "ValueError", "KeyError", "IndexError")
EXPECTS = frozenset({"", "fail", "pass", "improve"})


def family_crystals_enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get(FAMILY_ENV, "")).strip().lower() in {"1", "true", "yes", "on"}


def family_opcode_registry() -> OpcodeRegistry:
    target = ("implementation_target",)
    return OpcodeRegistry([
        _spec("worktree.inspect", "observation", "context_only", "agent_runtime.tool:workspace.read_range", parameters=target),
        _spec("worktree.bind", "actuation", "bounded_execute", "agent_runtime.tool:worktree.bind", rollback="worktree.discard"),
        _spec("worktree.verify", "verification", "verify_only", "agent_runtime.tool:worktree.verify", parameters=("verify_command",)),
        *[_spec(op, "decision", "proposal_only", f"family_crystals.{op}", parameters=target, descriptors=())
          for op in sorted({f["resolver"] for f in FAMILIES.values()})],
        _spec("worktree.apply_plan", "actuation", "bounded_execute", "agent_runtime.tool:worktree.replace_exact",
              parameters=target, rollback="worktree.discard"),
        _spec("toolchain.run_declared", "actuation", "bounded_execute", "agent_runtime.tool:worktree.run_declared_tool",
              parameters=("verify_command",), rollback="worktree.discard"),
        _spec("crystal.complete", "verification", "verify_only", "agent_runtime.decision:complete", descriptors=()),
    ])


def _canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(value if isinstance(value, bytes) else _canon(value)).hexdigest()


def catalog_digest() -> str:
    return str(family_opcode_registry().catalog()["catalog_digest"])


RESOLVER_OPS = frozenset(f["resolver"] for f in FAMILIES.values())
ACTUATORS = frozenset({"worktree.apply_plan", "toolchain.run_declared"})


def recipe(families: Sequence[str]) -> tuple[dict[str, str], ...]:
    steps = [{"opcode": "worktree.inspect", "expect": ""}, {"opcode": "worktree.bind", "expect": ""},
             {"opcode": "worktree.verify", "expect": "fail"}]
    for index, family in enumerate(families):
        spec = FAMILIES[family]
        steps += [{"opcode": spec["resolver"], "expect": ""}, {"opcode": spec["actuator"], "expect": ""},
                  {"opcode": "worktree.verify", "expect": "pass" if index == len(families) - 1 else "improve"}]
    return (*steps, {"opcode": "crystal.complete", "expect": ""})


OPCODE_TOOLS = {"worktree.inspect": "workspace.read_range", "worktree.bind": "worktree.bind",
                "worktree.verify": "worktree.verify", "worktree.apply_plan": "worktree.replace_exact",
                "toolchain.run_declared": "worktree.run_declared_tool"}


def recipe_authority(families: Sequence[str]) -> set[str]:
    return {OPCODE_TOOLS[s["opcode"]] for s in recipe(families) if s["opcode"] in OPCODE_TOOLS}


@dataclass(frozen=True)
class FamilyCrystal:
    crystal_id: str
    task_family: str
    steps: tuple[Mapping[str, str], ...]
    catalog_digest: str
    source_run_id: str
    source_envelope_digest: str
    expected_failures: int = 1
    learned_budget: Mapping[str, float] = field(default_factory=dict)
    component_ids: tuple[str, ...] = ()
    component_families: tuple[str, ...] = ()
    authority: tuple[str, ...] = ()  # composites: A_L = intersection of the children's tool authority
    kind: str = KIND
    digest: str = ""

    def _body(self) -> dict[str, Any]:
        body = asdict(self)
        body.pop("digest")
        body.pop("crystal_id")
        if not body.get("authority"):
            body.pop("authority", None)
        return body

    def sealed(self) -> FamilyCrystal:
        digest = _digest(self._body())
        return replace(self, digest=digest, crystal_id="family-crystal:" + digest.split(":", 1)[1][:24])

    def validate(self) -> None:
        if self.kind != KIND or not self.digest or self.digest != _digest(self._body()):
            raise ValueError("family crystal digest mismatch")
        if self.crystal_id != "family-crystal:" + self.digest.split(":", 1)[1][:24]:
            raise ValueError("family crystal identity is not bound to its digest")
        if self.catalog_digest != catalog_digest():
            raise ValueError("family crystal compiled against an unreviewed opcode catalog")
        families = self.component_families or (self.task_family,)
        if any(f not in FAMILIES for f in families):
            raise ValueError("unreviewed task family")
        if [dict(s) for s in self.steps] != [dict(s) for s in recipe(families)]:
            raise ValueError("family crystal steps are not the reviewed recipe for its families")
        registry = family_opcode_registry()
        for step in self.steps:
            if set(step) != {"opcode", "expect"} or step["expect"] not in EXPECTS:
                raise ValueError("family crystal step has unreviewed fields")
            registry.resolve(str(step["opcode"]))
        if self.component_ids:
            if len(set(self.component_ids)) < 2 or len(self.component_ids) != len(self.component_families):
                raise ValueError("a composite needs at least two distinct children")
            if self.expected_failures != len(self.component_ids):
                raise ValueError("composite failure contract mismatch")
            authority = set(self.authority)
            if not authority or list(self.authority) != sorted(authority):
                raise ValueError("composite authority must be a sorted non-empty tool set")
            if not authority <= set.intersection(*(recipe_authority([f]) for f in self.component_families)):
                raise ValueError("composite authority exceeds the intersection of its children (A_L)")
            if not recipe_authority(self.component_families) <= authority:
                raise ValueError("composite steps exceed the intersected authority A_L")
        elif self.authority:
            raise ValueError("authority is only declared on composites")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [dict(s) for s in self.steps]
        data["component_ids"] = list(self.component_ids)
        data["component_families"] = list(self.component_families)
        data["authority"] = list(self.authority)
        return data

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> FamilyCrystal:
        data = dict(value)
        data["steps"] = tuple(dict(s) for s in data.get("steps") or ())
        data["learned_budget"] = dict(data.get("learned_budget") or {})
        data["component_ids"] = tuple(data.get("component_ids") or ())
        data["component_families"] = tuple(data.get("component_families") or ())
        data["authority"] = tuple(data.get("authority") or ())
        crystal = cls(**data)
        crystal.validate()
        return crystal


# -- verification helpers ------------------------------------------------------------------------------------------
def run_verify(command: Sequence[str], cwd: Path) -> dict[str, Any]:
    started = time.perf_counter()
    done = subprocess.run(list(command), cwd=cwd, capture_output=True, text=True, timeout=120, check=False,
                          env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"})
    out = (done.stdout + "\n" + done.stderr).strip()
    ran = 0
    for line in out.splitlines():
        if line.startswith("Ran ") and " test" in line:
            ran = int(line.split()[1])
    return {"returncode": done.returncode, "output": out, "tests_run": ran, "failures": failure_count(out, done.returncode),
            "ms": round((time.perf_counter() - started) * 1000, 3)}


def failure_count(output: str, returncode: int = 1) -> int:
    found = re.search(r"^FAILED \(([^)]*)\)", output, re.M)
    if not found:
        return 0 if returncode == 0 else 1
    return sum(int(n) for n in re.findall(r"(?:failures|errors)=(\d+)", found.group(1)))


def _safe_rel(path: str) -> Path:
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts or not path:
        raise PermissionError(f"unsafe path: {path}")
    return rel


def apply_plan(worktree: Path, plan: Mapping[str, Any]) -> list[str]:
    changed = []
    for rel_text, content in dict(plan.get("rewrite") or {}).items():
        rel = _safe_rel(rel_text)
        if rel.suffix != ".py" or (worktree / rel).is_symlink():
            raise PermissionError("rewrite limited to regular .py files")
        (worktree / rel).write_text(content, encoding="utf-8")
        changed.append(str(rel))
    for edit in plan.get("edits") or ():
        rel = _safe_rel(str(edit["path"]))
        path = worktree / rel
        if rel.suffix != ".py" or path.is_symlink() or not path.is_file():
            raise PermissionError("edits limited to existing regular .py files")
        from app.kernel.compute.structured_edit import apply_one_edit
        apply_one_edit(path, edit)
        changed.append(str(rel))
    return sorted(set(changed))


def tree_digest(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): _digest(p.read_bytes()) for p in sorted(root.rglob("*.py"))
            if p.is_file() and "__pycache__" not in p.parts}


# -- resolvers -----------------------------------------------------------------------------------------------------
@dataclass
class Context:
    worktree: Path
    target: str
    verify_command: list[str]
    verify: dict[str, Any]


def _select_reducing(ctx: Context, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Unique candidate that strictly reduces failures; prefer full passes. Probes scratch copies only."""
    base = int(ctx.verify["failures"])
    scored = []
    with tempfile.TemporaryDirectory(prefix="beast-probe-") as tmp:
        for index, plan in enumerate(candidates[:MAX_CANDIDATES]):
            scratch = Path(tmp) / str(index)
            shutil.copytree(ctx.worktree, scratch)
            try:
                apply_plan(scratch, plan)
            except PermissionError:
                continue
            result = run_verify(ctx.verify_command, scratch)
            if result["failures"] < base and result["tests_run"] >= int(ctx.verify["tests_run"]):
                scored.append((result["failures"], index, plan))
    if not scored:
        return None
    best = min(s[0] for s in scored)
    winners = [s for s in scored if s[0] == best]
    return dict(winners[0][2], probes=len(candidates[:MAX_CANDIDATES])) if len(winners) == 1 else None


def _line_mutations(ctx: Context, rules: Sequence[tuple[str, Callable[[re.Match[str]], str]]]) -> list[dict[str, Any]]:
    text = (ctx.worktree / ctx.target).read_text(encoding="utf-8")
    lines = text.splitlines()
    out = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "def ", "class ", "import ", "from ", '"""')) or text.count(line) != 1:
            continue
        for pattern, repl in rules:
            for match in re.finditer(pattern, line):
                new = line[:match.start()] + repl(match) + line[match.end():]
                if new != line:
                    out.append({"edits": [{"path": ctx.target, "old_text": line, "new_text": new}]})
    return out


_OPS = {" + ": " - ", " - ": " + ", " * ": " / ", " / ": " * ", " and ": " or ", " or ": " and ",
        " == ": " != ", " != ": " == ", "max(": "min(", "min(": "max("}


def resolve_operator(ctx: Context) -> dict[str, Any] | None:
    rules = [(re.escape(a), (lambda _m, b=b: b)) for a, b in _OPS.items()]
    rules.append((r" \* ", lambda _m: " + "))
    rules.append((r" \+ ", lambda _m: " * "))
    return _select_reducing(ctx, _line_mutations(ctx, rules))


def _range_stop(match: re.Match[str]) -> str:
    args = [a.strip() for a in match.group(1).split(",")]
    index = 0 if len(args) == 1 else 1
    stop = args[index]
    args[index] = stop[:-4].strip() if stop.endswith(" + 1") else f"{stop} + 1"
    return "range(" + ", ".join(args) + ")"


def resolve_boundary(ctx: Context) -> dict[str, Any] | None:
    rules = [(r" <= ", lambda _m: " < "), (r" < ", lambda _m: " <= "), (r" >= ", lambda _m: " > "),
             (r" > ", lambda _m: " >= "), (r"range\(([^()]*)\)", _range_stop), (r" - 1\b", lambda _m: ""),
             (r" \+ 1\b", lambda _m: ""), (r"\[:(\w+)\]", lambda m: f"[:{m.group(1)} + 1]")]
    return _select_reducing(ctx, _line_mutations(ctx, rules))


def resolve_constant_plan(ctx: Context) -> dict[str, Any] | None:
    content = (ctx.worktree / ctx.target).read_text(encoding="utf-8")
    proposal = resolve_constant(ctx.verify["output"], content)
    if not proposal:
        return None
    return {"edits": [{"path": ctx.target, "old_text": proposal["old_text"], "new_text": proposal["new_text"]}]}


_FRAME = re.compile(r'^\s*File "([^"]+)", line (\d+), in (\w+)\n\s*(.+)$', re.M)


def resolve_guard(ctx: Context) -> dict[str, Any] | None:
    output = ctx.verify["output"]
    exc = re.findall(r"^(" + "|".join(GUARDABLE) + r"): ", output, re.M)
    frames = _FRAME.findall(output)
    if len(set(exc)) != 1 or not frames:
        return None
    target_abs = str((ctx.worktree / ctx.target).resolve())
    last = frames[-1]
    if str(Path(last[0]).resolve()) != target_abs:
        return None  # raised outside the implementation target: not this recipe
    test_frames = [f for f in frames if Path(f[0]).name.startswith("test_")]
    if not test_frames:
        return None
    try:
        call = ast.parse(test_frames[-1][3].strip()).body[0].value
    except (SyntaxError, IndexError, AttributeError):
        return None
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
        return None
    if call.func.attr == "assertIsNone" and len(call.args) == 1:
        default: Any = None
    elif call.func.attr == "assertEqual" and len(call.args) == 2:
        try:
            default = ast.literal_eval(call.args[1])
        except ValueError:
            return None
    else:
        return None
    lines = (ctx.worktree / ctx.target).read_text(encoding="utf-8").splitlines()
    lineno = int(last[1])
    if lineno > len(lines):
        return None
    line = lines[lineno - 1]
    found = re.match(r"^(\s+)return (.+)$", line)
    if not found or "\n".join(lines).count(line) != 1:
        return None
    ind, expr = found.groups()
    new = f"{ind}try:\n{ind}    return {expr}\n{ind}except {exc[0]}:\n{ind}    return {default!r}"
    return {"edits": [{"path": ctx.target, "old_text": line, "new_text": new}]}


def _tokens(name: str) -> set[str]:
    return {t for t in name.lower().split("_") if t}


def resolve_rename(ctx: Context) -> dict[str, Any] | None:
    found = re.findall(r"ImportError: cannot import name '(\w+)' from '([\w.]+)'", ctx.verify["output"])
    if len(set(found)) != 1:
        return None
    new, module = found[0]
    module_path = ctx.worktree / (module.replace(".", "/") + ".py")
    if not module_path.is_file():
        return None
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    public = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and not n.name.startswith("_")]
    if new in public:
        return None
    scored = sorted(((len(_tokens(p) & _tokens(new)), p) for p in public), reverse=True)
    if not scored or scored[0][0] == 0 or (len(scored) > 1 and scored[1][0] == scored[0][0]):
        return None
    old = scored[0][1]
    # Scope-aware, reference-resolving rename (code.rename_symbol); strings/comments are flagged, never rewritten.
    # Replaces the earlier repo-wide ``\bold\b`` regex, which also rewrote strings, comments and unrelated locals.
    from app.kernel.compute.symbol_rename import RenameError, plan_rename

    try:
        plan = plan_rename(ctx.worktree, str(module_path.relative_to(ctx.worktree)), old, new, exclude=("test_*.py",))
    except RenameError:
        return None
    rewrite = {p: plan.new_text[p] for p in plan.changed_files}
    return {"rewrite": rewrite, "rename": {"old": old, "new": new, "tool": "code.rename_symbol",
                                           "flagged": len([r for r in plan.refs if not r.changed])}} if rewrite else None


def resolve_declared_tool(ctx: Context) -> dict[str, Any] | None:
    found = set(re.findall(r"stale: run (tools/[\w/]+\.py)", ctx.verify["output"]))
    if len(found) != 1:
        return None
    rel = _safe_rel(found.pop())
    path = ctx.worktree / rel
    if not path.is_file() or path.is_symlink() or rel.parts[0] != "tools":
        return None
    return {"command": [ctx.verify_command[0], str(rel)]}


RESOLVERS: dict[str, Callable[[Context], dict[str, Any] | None]] = {
    "repair.resolve_constant": resolve_constant_plan, "repair.operator_swap": resolve_operator,
    "repair.boundary_shift": resolve_boundary, "repair.guard_exception": resolve_guard,
    "repair.rename_symbol": resolve_rename, "toolchain.resolve_declared": resolve_declared_tool,
}


def run_declared(worktree: Path, argv: Sequence[str]) -> dict[str, Any]:
    started = time.perf_counter()
    done = subprocess.run(list(argv), cwd=worktree, capture_output=True, text=True, timeout=60, check=False,
                          env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"})
    return {"returncode": done.returncode, "ms": round((time.perf_counter() - started) * 1000, 3)}


# -- reviewed replay interpreter -------------------------------------------------------------------------------------
def replay_family(crystal: FamilyCrystal, parameters: Mapping[str, Any], root: Path, worktree: Path) -> dict[str, Any]:
    crystal.validate()
    return _interpret(crystal.steps, parameters, root, worktree)


def stage_steps(composite: FamilyCrystal, child: FamilyCrystal, index: int) -> tuple[Mapping[str, str], ...]:
    """Child recipe re-bound to its lattice stage: its final verify takes the composite's stage expectation."""
    composite.validate()
    child.validate()
    if not composite.component_ids or not 0 <= index < len(composite.component_ids):
        raise PermissionError("not a lattice stage")
    if composite.component_ids[index] != child.crystal_id or composite.component_families[index] != child.task_family:
        raise PermissionError("child is not this composite's stage")
    if child.component_ids:
        raise PermissionError("nested composites are not reviewed")
    expect = "pass" if index == len(composite.component_ids) - 1 else "improve"
    steps = [dict(s) for s in child.steps]
    finals = [i for i, s in enumerate(steps) if s["opcode"] == "worktree.verify"]
    steps[finals[-1]]["expect"] = expect
    if index > 0:
        steps[finals[0]]["expect"] = "fail"  # input of a later stage still fails (remaining capability)
    return tuple(steps)


def replay_stage(composite: FamilyCrystal, child: FamilyCrystal, index: int, parameters: Mapping[str, Any],
                 root: Path, worktree: Path) -> dict[str, Any]:
    out = _interpret(stage_steps(composite, child, index), parameters, root, worktree)
    out["lattice_stage"] = {"composite_id": composite.crystal_id, "child_id": child.crystal_id, "index": index,
                            "expect_after": "pass" if index == len(composite.component_ids) - 1 else "improve"}
    return out


def _interpret(steps: Sequence[Mapping[str, str]], parameters: Mapping[str, Any], root: Path, worktree: Path) -> dict[str, Any]:
    registry = family_opcode_registry()
    target = str(_safe_rel(str(parameters["implementation_target"])))
    command = [str(x) for x in parameters["verify_command"]]
    trace: list[dict[str, Any]] = []
    plan: dict[str, Any] | None = None
    last: dict[str, Any] | None = None
    tool_calls, changed = 0, []
    started = time.perf_counter()
    for index, step in enumerate(steps):
        spec = registry.resolve(str(step["opcode"]))
        t0 = time.perf_counter()
        row: dict[str, Any] = {"index": index, "opcode": spec.opcode}
        if spec.opcode == "worktree.inspect":
            row["sha256"] = _digest((root / target).read_bytes())
            tool_calls += 1
        elif spec.opcode == "worktree.bind":
            if worktree.exists():
                raise PermissionError("worktree already exists")
            shutil.copytree(root, worktree)
            tool_calls += 1
        elif spec.opcode == "worktree.verify":
            before = last["failures"] if last else None
            last = run_verify(command, worktree)
            tool_calls += 1
            expect = step["expect"]
            ok = {"fail": last["returncode"] != 0, "pass": last["returncode"] == 0,
                  "improve": before is not None and last["failures"] < before, "": True}[expect]
            row.update(expect=expect, returncode=last["returncode"], failures=last["failures"], tests_run=last["tests_run"])
            if not ok:
                trace.append({**row, "refused": f"verify expectation {expect!r} not met"})
                return {"ok": False, "reason": "expectation_failed", "trace": trace, "tool_calls": tool_calls,
                        "model_calls": 0, "changed": changed}
        elif spec.opcode in RESOLVER_OPS:
            plan = RESOLVERS[spec.opcode](Context(worktree, target, command, last or {}))
            if not plan:
                trace.append({**row, "refused": "resolver not applicable"})
                return {"ok": False, "reason": "not_applicable", "trace": trace, "tool_calls": tool_calls,
                        "model_calls": 0, "changed": changed}
            row["plan"] = {k: v for k, v in plan.items() if k != "rewrite"} | (
                {"rewrite_files": sorted(plan["rewrite"])} if plan.get("rewrite") else {})
        elif spec.opcode == "worktree.apply_plan":
            if not plan or "command" in plan:
                raise PermissionError("apply_plan needs an edit plan")
            changed += apply_plan(worktree, plan)
            tool_calls += 1
            plan = None
        elif spec.opcode == "toolchain.run_declared":
            if not plan or "command" not in plan:
                raise PermissionError("run_declared needs a declared tool plan")
            before_tree = tree_digest(worktree)
            row["tool"] = run_declared(worktree, plan["command"])
            after_tree = tree_digest(worktree)
            changed += [k for k in after_tree if before_tree.get(k) != after_tree[k]]
            tool_calls += 1
            plan = None
        row["ms"] = round((time.perf_counter() - t0) * 1000, 3)
        trace.append(row)
    return {"ok": True, "trace": trace, "tool_calls": tool_calls, "model_calls": 0, "changed": sorted(set(changed)),
            "wall_ms": round((time.perf_counter() - started) * 1000, 3)}


# -- extraction ------------------------------------------------------------------------------------------------------
def extract_family(family: str, envelope: Any, *, root: Path, parameters: Mapping[str, Any], model_worktree: Path,
                   scratch: Path) -> tuple[FamilyCrystal | None, dict[str, Any]]:
    """Distil a verified model episode into the family recipe only if the reviewed resolver reproduces it."""
    try:
        envelope.validate()
    except ValueError:
        return None, {"refused": "tampered_envelope"}
    if not envelope.verification.get("passed") or int(envelope.verification.get("failures_before_pass") or 0) < 1:
        return None, {"refused": "unverified_or_no_failure_to_parameterize"}
    crystal = FamilyCrystal(crystal_id="", task_family=family, steps=recipe([family]), catalog_digest=catalog_digest(),
                            source_run_id=envelope.run_id, source_envelope_digest=envelope.envelope_digest,
                            learned_budget={k: float(v) for k, v in dict(envelope.budget).items()}).sealed()
    if scratch.exists():
        shutil.rmtree(scratch)
    replay = replay_family(crystal, parameters, root, scratch)
    if not replay["ok"]:
        return None, {"refused": f"resolver_did_not_reproduce:{replay.get('reason')}", "replay": replay}
    pristine, model, resolved = tree_digest(root), tree_digest(model_worktree), tree_digest(scratch)
    model_changed = sorted(k for k in model if pristine.get(k) != model[k])
    resolved_changed = sorted(k for k in resolved if pristine.get(k) != resolved[k])
    if model_changed != resolved_changed:
        return None, {"refused": "changed_file_set_differs", "model_changed": model_changed,
                      "resolver_changed": resolved_changed}
    exact = all(model[k] == resolved[k] for k in model_changed)
    return crystal, {"reproduced": True, "changed": model_changed, "exact_state_match": exact,
                     "equivalence": "byte_identical" if exact else "verifier_equivalent", "replay": replay}


def compose(children: Sequence[FamilyCrystal], *, source_run_id: str) -> FamilyCrystal:
    families = tuple(c.task_family for c in children)
    return FamilyCrystal(crystal_id="", task_family="composite:" + "+".join(families), steps=recipe(families),
                         catalog_digest=catalog_digest(), source_run_id=source_run_id,
                         source_envelope_digest=_digest([c.source_envelope_digest for c in children]),
                         expected_failures=len(children), component_ids=tuple(c.crystal_id for c in children),
                         component_families=families,
                         authority=tuple(sorted(set.intersection(*(recipe_authority([f]) for f in families))))).sealed()


# -- applicability (nominates only) ------------------------------------------------------------------------------------
WEIGHTS = {"unittest_verify": 0.15, "failure_signature": 0.40, "failure_count": 0.15, "python_target": 0.15,
           "resolver_plan": 0.15}


def applicability(crystal: FamilyCrystal, root: Path, task: Mapping[str, Any], observed: Mapping[str, Any]) -> dict[str, Any]:
    families = crystal.component_families or (crystal.task_family,)
    first = FAMILIES[families[0]]
    with tempfile.TemporaryDirectory(prefix="beast-match-") as tmp:
        scratch = Path(tmp) / "w"
        shutil.copytree(root, scratch)
        local = run_verify(list(task["verify"]), scratch)  # tracebacks must name the scratch paths the resolver reads
        try:
            plan = RESOLVERS[first["resolver"]](Context(scratch, str(task["target"]), list(task["verify"]), local))
        except (PermissionError, OSError, ValueError, SyntaxError):
            plan = None
    features = {"unittest_verify": list(task["verify"])[1:3] == ["-m", "unittest"],
                "failure_signature": bool(re.search(first["signature"], observed["output"], re.M)),
                "failure_count": int(observed["failures"]) == crystal.expected_failures,
                "python_target": str(task["target"]).endswith(".py"),
                "resolver_plan": bool(plan)}
    return {"crystal_id": crystal.crystal_id, "similarity": round(sum(WEIGHTS[k] for k, v in features.items() if v), 4),
            "features": features, "matcher": "beast.family_applicability.v1 (local, deterministic, nominates only)"}


def discover(registry: FamilyRegistry, root: Path, task: Mapping[str, Any], observed: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Rank every promoted crystal (singles and composites) for a task; nobody hands the router a crystal id.

    Order: similarity desc, then more specific failure contracts (composites cover more failures), then id.
    """
    ranked = []
    for crystal in registry.promoted():
        row = applicability(crystal, root, task, observed)
        row.update(task_family=crystal.task_family, composite=bool(crystal.component_ids),
                   children=list(crystal.component_ids), expected_failures=crystal.expected_failures)
        ranked.append(row)
    ranked.sort(key=lambda r: (-r["similarity"], -r["expected_failures"], r["crystal_id"]))
    return ranked


# -- registry ----------------------------------------------------------------------------------------------------------
class FamilyRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as c:
            c.executescript(
                "CREATE TABLE IF NOT EXISTS family_crystals (crystal_id TEXT PRIMARY KEY, task_family TEXT NOT NULL,"
                " status TEXT NOT NULL, payload TEXT NOT NULL, record_digest TEXT NOT NULL, updated_at REAL NOT NULL);"
                "CREATE TABLE IF NOT EXISTS family_negatives (id INTEGER PRIMARY KEY AUTOINCREMENT, task_family TEXT,"
                " crystal_id TEXT, kind TEXT, evidence_digest TEXT, created_at REAL);")

    def _connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def _write(self, record: dict[str, Any]) -> dict[str, Any]:
        record = dict(record, record_digest="")
        record["record_digest"] = _digest(record)
        with self._connect() as c:
            c.execute("INSERT INTO family_crystals VALUES(?,?,?,?,?,?) ON CONFLICT(crystal_id) DO UPDATE SET "
                      "status=excluded.status,payload=excluded.payload,record_digest=excluded.record_digest,"
                      "updated_at=excluded.updated_at",
                      (record["crystal_id"], record["task_family"], record["status"], json.dumps(record, sort_keys=True),
                       record["record_digest"], time.time()))
        return record

    def add_candidate(self, crystal: FamilyCrystal, *, provenance: Mapping[str, Any] | None = None) -> dict[str, Any]:
        crystal.validate()
        for child in crystal.component_ids:
            if self.get(child)["status"] != "promoted":
                raise PermissionError("composite children must be promoted first")
        try:
            return self.get(crystal.crystal_id)
        except LookupError:
            return self._write({"crystal_id": crystal.crystal_id, "task_family": crystal.task_family,
                                "status": "candidate", "crystal": crystal.to_dict(), "promotion": None,
                                "reuse_count": 0, "reuses": [], "provenance": dict(provenance or {})})

    def get(self, crystal_id: str) -> dict[str, Any]:
        with self._connect() as c:
            row = c.execute("SELECT * FROM family_crystals WHERE crystal_id=?", (crystal_id,)).fetchone()
        if row is None:
            raise LookupError(crystal_id)
        record = json.loads(row["payload"])
        if record.get("record_digest") != _digest(dict(record, record_digest="")) or row["record_digest"] != record["record_digest"]:
            raise ValueError("family crystal record digest mismatch")
        record["crystal_object"] = FamilyCrystal.from_dict(record["crystal"])
        return record

    def _mutate(self, crystal_id: str, **changes: Any) -> dict[str, Any]:
        record = self.get(crystal_id)
        record.pop("crystal_object")
        record.update(changes)
        return self._write(record)

    def promote(self, crystal_id: str, receipt: Any, *, approved_by: str) -> dict[str, Any]:
        if not approved_by:
            raise PermissionError("promotion is an explicit operator act (approved_by required)")
        if not getattr(receipt, "promoted", False) or getattr(receipt, "candidate_id", "") != crystal_id:
            raise PermissionError("promotion requires a passing held-out receipt for this crystal")
        if int(getattr(receipt, "successes", 0)) < 3:
            raise PermissionError("promotion requires at least three held-out successes")
        with self._lock:
            return self._mutate(crystal_id, status="promoted", promotion={
                "approved_by": approved_by, "promoted_at": time.time(), "heldout_receipt": asdict(receipt)})

    def record_reuse(self, crystal_id: str, *, run_id: str, outcome: str) -> dict[str, Any]:
        with self._lock:
            record = self.get(crystal_id)
            reuses = list(record.get("reuses") or [])[-49:] + [{"run_id": run_id, "outcome": outcome, "at": time.time()}]
            return self._mutate(crystal_id, reuse_count=int(record.get("reuse_count") or 0) + 1, reuses=reuses)

    def record_negative(self, family: str, *, kind: str, crystal_id: str = "", evidence_digest: str = "") -> None:
        with self._connect() as c:
            c.execute("INSERT INTO family_negatives(task_family,crystal_id,kind,evidence_digest,created_at) VALUES(?,?,?,?,?)",
                      (family, crystal_id, kind, evidence_digest, time.time()))

    def promoted(self) -> list[FamilyCrystal]:
        with self._connect() as c:
            ids = [r["crystal_id"] for r in c.execute("SELECT crystal_id FROM family_crystals WHERE status='promoted' ORDER BY updated_at")]
        out = []
        for crystal_id in ids:
            try:
                out.append(self.get(crystal_id)["crystal_object"])
            except (LookupError, ValueError):
                continue  # fail closed
        return out


def route(registry: FamilyRegistry, crystal: FamilyCrystal | None, similarity: float,
          specialist: Mapping[str, Any] | None, *, envelope_ok: bool = True) -> Any:
    """D9 AdaptiveRouter over a family crystal; fingerprints = catalog digest + tamper-checked record digest."""
    from app.kernel.compute.adaptive_router import AdaptiveRouter

    router = AdaptiveRouter()
    if crystal is None:
        return router.route(similarity=similarity, specialist=specialist, reasons=("no promoted family crystal",))
    try:
        record_digest = registry.get(crystal.crystal_id)["record_digest"]
    except (LookupError, ValueError):
        record_digest = "tampered"
    crystal_fp = {"opcode_catalog_digest": crystal.catalog_digest, "crystal_digest": record_digest,
                  "source_envelope_digest": crystal.source_envelope_digest}
    request_fp = {"opcode_catalog_digest": catalog_digest(), "crystal_digest": record_digest if record_digest != "tampered" else "",
                  "source_envelope_digest": crystal.source_envelope_digest if envelope_ok else ""}
    return router.route(similarity=similarity, crystal_id=crystal.crystal_id, crystal_fingerprints=crystal_fp,
                        request_fingerprints=request_fp, specialist=specialist,
                        envelope_digest=crystal.source_envelope_digest)


__all__ = ["CATALOG_VERSION", "FAMILIES", "FAMILY_ENV", "FamilyCrystal", "FamilyRegistry", "RESOLVERS", "applicability",
           "apply_plan", "catalog_digest", "compose", "discover", "replay_stage", "stage_steps", "recipe_authority", "extract_family", "failure_count", "family_crystals_enabled",
           "family_opcode_registry", "recipe", "replay_family", "route", "run_verify", "tree_digest"]
