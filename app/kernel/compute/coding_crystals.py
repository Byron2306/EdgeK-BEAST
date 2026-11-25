"""Reviewed coding crystals: learn, replay, promote and reuse verified coding recipes.

A coding crystal is a tiny recipe over a *separate* reviewed opcode catalog. It
never carries code: every actuation maps onto an existing AgentRun tool whose
arguments, approvals and verified-handoff binding stay enforced by the planner
runtime. Anything outside ``CODING_OPCODE_TOOLS`` is refused at compile time,
at session time and again by the runtime before execution.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import sqlite3
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from app.kernel.compute.typed_crystal_ir import OpcodeRegistry, OpcodeSpec

CODING_CATALOG_VERSION = "beast.coding_opcodes.v1"
CODING_OPCODE_TOOLS: dict[str, str] = {
    "worktree.inspect": "workspace.read_range",
    "worktree.bind": "worktree.bind",
    "worktree.verify": "worktree.verify",
    "worktree.replace_exact": "worktree.replace_exact",
}
REVIEWED_TOOLS = frozenset(CODING_OPCODE_TOOLS.values())


def _spec(opcode: str, phase: str, authority: str, handler: str, *, parameters: tuple[str, ...] = (),
          rollback: str = "", descriptors: tuple[str, ...] = ("workspace",)) -> OpcodeSpec:
    return OpcodeSpec(
        opcode=opcode, version=1, phase=phase, authority=authority, handler_key=handler,
        input_schema=dict.fromkeys(parameters, "string"), output_schema={"observation": "digest"},
        allowed_parameters=parameters, required_descriptors=descriptors,
        resource_limits={"timeout_s": 120.0, "max_bytes": 262144.0}, verifier_key="agent_runtime.observation_status",
        rollback_key=rollback,
    )


def coding_opcode_registry() -> OpcodeRegistry:
    """Reviewed catalog for coding recipes; deliberately not merged into the physical catalog."""
    return OpcodeRegistry([
        _spec("worktree.inspect", "observation", "context_only", "agent_runtime.tool:workspace.read_range",
              parameters=("implementation_target",)),
        _spec("worktree.bind", "actuation", "bounded_execute", "agent_runtime.tool:worktree.bind",
              rollback="worktree.discard"),
        _spec("worktree.verify", "verification", "verify_only", "agent_runtime.tool:worktree.verify",
              parameters=("verify_command",)),
        _spec("repair.resolve_constant", "decision", "proposal_only", "coding_crystals.resolve_constant",
              parameters=("implementation_target",), descriptors=()),
        _spec("worktree.replace_exact", "actuation", "bounded_execute", "agent_runtime.tool:worktree.replace_exact",
              parameters=("implementation_target",), rollback="worktree.discard"),
        _spec("crystal.complete", "verification", "verify_only", "agent_runtime.decision:complete", descriptors=()),
    ])


_UNITTEST_FAILURE = re.compile(r"^AssertionError: (.+?) != (.+?)\s*$", re.MULTILINE)
_PYTEST_FAILURE = re.compile(r"^E\s+assert (.+?) == (.+?)\s*$", re.MULTILINE)
# unittest.assertTrue/assertFalse: "AssertionError: False is not true"
_UNITTEST_BOOL_FAILURE = re.compile(r"^AssertionError: (True|False) is not (true|false)\s*$",
                                    re.MULTILINE | re.IGNORECASE)
_CONSTANT = re.compile(r"^([A-Z_][A-Z0-9_]*)\s*=\s*(.+?)\s*$")
_SCALARS = (bool, int, float, str)


def _literal(text: str) -> Any:
    try:
        value = ast.literal_eval(text.strip())
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return None
    return value if isinstance(value, _SCALARS) else None


def same_assignment_line(left: str, right: str) -> bool:
    """True when two assignment lines are text-equal or name+literal equivalent."""
    if str(left or "") == str(right or ""):
        return True
    parsed = []
    for line in (left, right):
        found = _CONSTANT.match(str(line or "").rstrip())
        if not found:
            return False
        parsed.append((found.group(1), _literal(found.group(2))))
    (name_a, value_a), (name_b, value_b) = parsed
    return name_a == name_b and value_a is not None and type(value_a) is type(value_b) and value_a == value_b


def resolve_constant(verify_output: str, target_content: str) -> dict[str, str] | None:
    """Resolve exactly one root literal edit from direct and downstream failures."""
    output = str(verify_output or "")
    matches = _UNITTEST_FAILURE.findall(output) + _PYTEST_FAILURE.findall(output)
    matches.extend((actual, expected.title()) for actual, expected in _UNITTEST_BOOL_FAILURE.findall(output))
    if not matches:
        return None
    parsed = [(_literal(actual_text), _literal(expected_text)) for actual_text, expected_text in matches]
    proposals: dict[tuple[str, str], dict[str, str]] = {}
    for actual, expected in parsed:
        if actual is None or expected is None or type(actual) is not type(expected) or actual == expected:
            continue
        for line in str(target_content or "").splitlines():
            found = _CONSTANT.match(line)
            if not found:
                continue
            value = _literal(found.group(2))
            old_text = line.rstrip()
            if (value is not None and type(value) is type(actual) and value == actual
                    and str(target_content).count(old_text) == 1):
                name = found.group(1)
                proposal = {"old_text": old_text, "new_text": f"{name} = {expected!r}", "name": name}
                proposals[(proposal["old_text"], proposal["new_text"])] = proposal
    if len(proposals) != 1:
        return None
    return next(iter(proposals.values()))


# --- Recipes, extraction and the registry ---------------------------------------------------------

RECIPE_FIX_FAILING_ASSERTION: tuple[Mapping[str, str], ...] = (
    {"opcode": "worktree.inspect", "tool_id": "workspace.read_range", "expect": ""},
    {"opcode": "worktree.bind", "tool_id": "worktree.bind", "expect": ""},
    {"opcode": "worktree.verify", "tool_id": "worktree.verify", "expect": "fail"},
    {"opcode": "repair.resolve_constant", "tool_id": "", "expect": ""},
    {"opcode": "worktree.replace_exact", "tool_id": "worktree.replace_exact", "expect": ""},
    {"opcode": "worktree.verify", "tool_id": "worktree.verify", "expect": "pass"},
    {"opcode": "crystal.complete", "tool_id": "", "expect": ""},
)
EXPLORATION_TOOLS = frozenset({
    "workspace.list", "workspace.search_text", "workspace.read_range", "workspace.index",
    # Worktree-scoped read aliases used by some provider dialects.
    "worktree.read", "worktree.read_file", "worktree.read_range",
})
RUNTIME_CLOSURE_TOOLS = frozenset({"worktree.sourceplan_draft"})
VERIFICATION_TOOLS = frozenset({"worktree.verify", "worktree.run"})


def _command_tokens(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).lower() for item in value]
    if isinstance(value, str):
        return value.lower().split()
    return []


def is_verification_step(step: Mapping[str, Any], observation: Mapping[str, Any] | None = None) -> bool:
    """worktree.verify always counts; worktree.run counts when it is a test runner."""
    tool = str(step.get("tool_id") or "")
    if tool == "worktree.verify":
        return True
    if tool != "worktree.run":
        return False
    sources = [step.get("safe_arguments") or {}, (observation or {}).get("arguments") or {},
               ((observation or {}).get("result") or {}) if isinstance((observation or {}).get("result"), Mapping) else {}]
    tokens: list[str] = []
    for source in sources:
        if isinstance(source, Mapping):
            tokens.extend(_command_tokens(source.get("command") or source.get("resolved_command")))
    blob = " ".join(tokens)
    return any(token in blob for token in ("unittest", "pytest", "py.test"))
STEP_KEYS = frozenset({"opcode", "tool_id", "expect"})
CRYSTAL_PARAMETERS = ("implementation_target", "verify_command")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def coding_catalog_digest() -> str:
    return str(coding_opcode_registry().catalog()["catalog_digest"])


@dataclass(frozen=True)
class CodingCrystalCandidate:
    crystal_id: str
    task_family: str
    steps: tuple[Mapping[str, str], ...]
    parameters: tuple[str, ...]
    opcode_catalog_digest: str
    source_run_id: str
    source_envelope_digest: str
    learned_budget: Mapping[str, float] = field(default_factory=dict)
    digest: str = ""
    # Lattice spine (composites): ordered children, A_L = intersection of A_Ci, and the composite verifier contract.
    # Empty values are excluded from the digest, so every pre-existing crystal keeps its identity.
    component_ids: tuple[str, ...] = ()
    authority: tuple[str, ...] = ()
    composite_verification: Mapping[str, Any] = field(default_factory=dict)

    def _body(self) -> dict[str, Any]:
        body = asdict(self)
        body.pop("digest", None)
        body.pop("crystal_id", None)
        for key in ("component_ids", "authority", "composite_verification"):
            if not body.get(key):
                body.pop(key, None)
        return body

    def sealed(self) -> CodingCrystalCandidate:
        digest = _digest(self._body())
        return replace(self, digest=digest, crystal_id="coding-crystal:" + digest.split(":", 1)[1][:24])

    def validate(self) -> None:
        if not self.digest or self.digest != _digest(self._body()):
            raise ValueError("coding crystal digest mismatch")
        if self.crystal_id != "coding-crystal:" + self.digest.split(":", 1)[1][:24]:
            raise ValueError("coding crystal identity is not bound to its digest")
        if self.opcode_catalog_digest != coding_catalog_digest():
            raise ValueError("coding crystal was compiled against an unreviewed opcode catalog")
        if tuple(self.parameters) != CRYSTAL_PARAMETERS:
            raise ValueError("coding crystal parameters are not reviewed")
        registry = coding_opcode_registry()
        last_actuation = last_pass = -1
        for index, step in enumerate(self.steps):
            if set(step) != STEP_KEYS:
                raise ValueError("coding crystal step has unreviewed fields")
            spec = registry.resolve(str(step["opcode"]))  # raises ValueError for unreviewed opcodes
            expected_tool = CODING_OPCODE_TOOLS.get(spec.opcode, "")
            if str(step["tool_id"]) != expected_tool:
                raise ValueError(f"coding crystal step {index} maps to an unreviewed tool")
            if step["expect"] not in {"", "fail", "pass"} or (step["expect"] and spec.opcode != "worktree.verify"):
                raise ValueError("coding crystal expectation is invalid")
            if spec.phase == "actuation" and spec.opcode == "worktree.replace_exact":
                last_actuation = index
            if spec.opcode == "worktree.verify" and step["expect"] == "pass":
                last_pass = index
        if not self.steps or self.steps[-1]["opcode"] != "crystal.complete":
            raise ValueError("coding crystal must end in a completion step")
        if last_actuation < 0 or last_pass < last_actuation:
            raise ValueError("coding crystal mutation lacks a passing verification postcondition")
        if self.component_ids or self.authority or self.composite_verification:
            self._validate_composite()

    def _validate_composite(self) -> None:
        if len(set(self.component_ids)) < 2 or len(set(self.component_ids)) != len(self.component_ids):
            raise ValueError("a composite needs at least two distinct children")
        if self.crystal_id in self.component_ids:
            raise ValueError("a composite cannot contain itself")
        authority = set(self.authority)
        if not authority or not authority <= REVIEWED_TOOLS or list(self.authority) != sorted(authority):
            raise ValueError("composite authority must be a sorted subset of the reviewed tools")
        used = {str(step["tool_id"]) for step in self.steps if step["tool_id"]}
        if not used <= authority:
            raise ValueError("composite steps exceed the intersected authority A_L")
        verification = dict(self.composite_verification or {})
        if verification.get("requires_children_verified") is not True or int(verification.get("heldout_min") or 0) < 3:
            raise ValueError("composite verification contract is missing")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [dict(step) for step in self.steps]
        data["parameters"] = list(self.parameters)
        return data

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CodingCrystalCandidate:
        data = dict(value)
        data["steps"] = tuple(dict(step) for step in data.get("steps") or ())
        data["parameters"] = tuple(data.get("parameters") or ())
        data["learned_budget"] = dict(data.get("learned_budget") or {})
        data["component_ids"] = tuple(data.get("component_ids") or ())
        data["authority"] = tuple(data.get("authority") or ())
        data["composite_verification"] = dict(data.get("composite_verification") or {})
        candidate = cls(**data)
        candidate.validate()
        return candidate


def verify_output(observation: Mapping[str, Any]) -> str:
    result = observation.get("result") if isinstance(observation.get("result"), Mapping) else {}
    text = "\n".join(str(result.get(key) or "") for key in ("stdout", "stderr")).strip()
    return text or str(observation.get("error") or "")


def _same_observed_edit(content: str, proposal: Mapping[str, str], observation: Mapping[str, Any]) -> bool:
    """Require exact file equivalence when the tool used a different replacement span."""
    arguments = observation.get("arguments") or {}
    old_text, new_text = arguments.get("old_text"), arguments.get("new_text")
    if not isinstance(old_text, str) or not old_text or not isinstance(new_text, str):
        return False
    if (old_text, new_text) == (proposal["old_text"], proposal["new_text"]):
        return True

    result = observation.get("result") or {}
    if (observation.get("status") != "completed" or observation.get("truncated")
            or result.get("path") != arguments.get("path") or result.get("replacements") != 1):
        return False

    def sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    # read_range joins lines without the final LF. Accept a reconstruction only
    # if the exact-edit receipt confirms it is the full pre-edit file.
    before = next((text for text in (content, content + "\n")
                   if sha256(text) == result.get("before_sha256")), None)
    canonical_old = proposal["old_text"]
    if before is None or before.count(canonical_old) != 1 or before.count(old_text) != 1:
        return False
    canonical = before.replace(canonical_old, proposal["new_text"], 1)
    actual = before.replace(old_text, new_text, 1)
    return actual == canonical and sha256(actual) == result.get("after_sha256")


class CodingCrystalExtractor:
    """Compress a verified Episode Envelope into the reviewed fix-failing-assertion recipe, or refuse."""

    def extract(self, envelope: Any, observations: Sequence[Mapping[str, Any]], *, registry: Any = None) -> CodingCrystalCandidate | None:
        try:
            envelope.validate()
        except ValueError:
            return self._refuse(registry, envelope, "tampered_envelope")
        if not envelope.verification.get("passed"):
            return self._refuse(registry, envelope, "unverified_episode")
        target = envelope.implementation_target
        if not target or envelope.task_family in {"", "unclassified"}:
            return self._refuse(registry, envelope, "unbound_task_family_or_target")
        by_digest = {str(item.get("evidence_digest") or ""): item for item in observations if isinstance(item, Mapping)}
        target_read = failing_verify = replace_step = passing_verify = None
        for step in envelope.steps:
            tool = step["tool_id"]
            observation = by_digest.get(str(step.get("result_digest") or ""))
            if tool == "worktree.replace_exact":
                if replace_step is not None or step["safe_arguments"].get("path") != target or failing_verify is None:
                    return self._refuse(registry, envelope, "unsupported_mutation_shape")
                replace_step = step
            elif is_verification_step(step, observation):
                if step.get("returncode") not in (0, None):
                    if replace_step is None:
                        failing_verify = step
                elif replace_step is not None:
                    passing_verify = step
            elif tool == "workspace.read_range":
                if step["safe_arguments"].get("path") == target and target_read is None:
                    target_read = step
            elif tool in EXPLORATION_TOOLS or tool in RUNTIME_CLOSURE_TOOLS or tool == "worktree.bind":
                continue
            else:
                return self._refuse(registry, envelope, "unreviewed_tool_in_episode")
        if failing_verify is None and int(envelope.verification.get("failures_before_pass") or 0) < 1:
            return self._refuse(registry, envelope, "no_failing_verification_to_parameterize")
        if target_read is None:
            return self._refuse(registry, envelope, "target_not_inspected")
        if replace_step is None or passing_verify is None:
            return self._refuse(registry, envelope, "no_verified_mutation")
        read_obs = by_digest.get(target_read["result_digest"])
        verify_obs = by_digest.get(failing_verify["result_digest"])
        replace_obs = by_digest.get(replace_step["result_digest"])
        if not (read_obs and verify_obs and replace_obs):
            return self._refuse(registry, envelope, "evidence_not_bound")
        content = str((read_obs.get("result") or {}).get("content") or "")
        proposal = resolve_constant(verify_output(verify_obs), content)
        arguments = replace_obs.get("arguments") or {}
        if not proposal or not (
            _same_observed_edit(content, proposal, replace_obs)
            or (
                same_assignment_line(proposal["old_text"], arguments.get("old_text"))
                and same_assignment_line(proposal["new_text"], arguments.get("new_text"))
            )
        ):
            return self._refuse(registry, envelope, "edit_not_reproducible")
        candidate = CodingCrystalCandidate(
            crystal_id="", task_family=envelope.task_family, steps=RECIPE_FIX_FAILING_ASSERTION,
            parameters=CRYSTAL_PARAMETERS, opcode_catalog_digest=coding_catalog_digest(),
            source_run_id=envelope.run_id, source_envelope_digest=envelope.envelope_digest,
            learned_budget={key: float(value) for key, value in dict(envelope.budget).items()},
        ).sealed()
        candidate.validate()
        return candidate

    @staticmethod
    def _refuse(registry: Any, envelope: Any, kind: str) -> None:
        if registry is not None:
            registry.record_negative(getattr(envelope, "task_family", "") or "unclassified", kind=kind,
                                     evidence_digest=getattr(envelope, "envelope_digest", ""))
        return None


class CodingCrystalRegistry:
    """Durable, digest-checked lifecycle store: candidate → promoted → demoted, plus negative evidence."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as connection:
            connection.executescript(
                "CREATE TABLE IF NOT EXISTS coding_crystals (crystal_id TEXT PRIMARY KEY, task_family TEXT NOT NULL, "
                "status TEXT NOT NULL, payload TEXT NOT NULL, record_digest TEXT NOT NULL, updated_at REAL NOT NULL);"
                "CREATE TABLE IF NOT EXISTS coding_crystal_negatives (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "task_family TEXT NOT NULL, crystal_id TEXT NOT NULL, kind TEXT NOT NULL, evidence_digest TEXT NOT NULL, "
                "created_at REAL NOT NULL);"
                "CREATE TABLE IF NOT EXISTS coding_crystal_scoped_refusals (crystal_id TEXT NOT NULL, "
                "scope_digest TEXT NOT NULL, run_id TEXT NOT NULL, receipt_digest TEXT NOT NULL, "
                "PRIMARY KEY(crystal_id,scope_digest));"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _record_digest(record: Mapping[str, Any]) -> str:
        return _digest(record)

    def _write(self, record: dict[str, Any]) -> dict[str, Any]:
        record["record_digest"] = ""
        record["record_digest"] = self._record_digest(record)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO coding_crystals(crystal_id,task_family,status,payload,record_digest,updated_at) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(crystal_id) DO UPDATE SET status=excluded.status,payload=excluded.payload,"
                "record_digest=excluded.record_digest,updated_at=excluded.updated_at",
                (record["crystal_id"], record["task_family"], record["status"], json.dumps(record, sort_keys=True),
                 record["record_digest"], time.time()),
            )
        return record

    def add_candidate(self, candidate: CodingCrystalCandidate) -> dict[str, Any]:
        candidate.validate()
        with self._lock:
            try:
                existing = self.get(candidate.crystal_id)
            except LookupError:
                existing = None
            if existing is not None:
                return existing
            return self._write({"crystal_id": candidate.crystal_id, "task_family": candidate.task_family,
                                "status": "candidate", "candidate": candidate.to_dict(), "receipt": None,
                                "reuse_count": 0, "reuses": [], "demotion": None})

    def add_quarantined(self, candidate: CodingCrystalCandidate, *, provenance: Mapping[str, Any]) -> dict[str, Any]:
        """Remote crystals enter as hypotheses: never served until local held-out reproduction promotes them."""
        candidate.validate()
        with self._lock:
            try:
                existing = self.get(candidate.crystal_id)
            except LookupError:
                existing = None
            if existing is not None:
                return existing
            return self._write({"crystal_id": candidate.crystal_id, "task_family": candidate.task_family,
                                "status": "quarantined", "candidate": candidate.to_dict(), "receipt": None,
                                "reuse_count": 0, "reuses": [], "demotion": None, "provenance": dict(provenance)})

    def get(self, crystal_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM coding_crystals WHERE crystal_id=?", (crystal_id,)).fetchone()
        if row is None:
            raise LookupError(f"unknown coding crystal: {crystal_id}")
        record = json.loads(row["payload"])
        claimed = record.get("record_digest")
        check = dict(record, record_digest="")
        if (claimed != self._record_digest(check) or claimed != row["record_digest"] or row["status"] != record.get("status")
                or row["task_family"] != record.get("task_family") or row["crystal_id"] != record.get("crystal_id")):
            raise ValueError("coding crystal record digest mismatch")
        record["candidate_object"] = CodingCrystalCandidate.from_dict(record["candidate"])
        if record["candidate_object"].crystal_id != crystal_id:
            raise ValueError("coding crystal record identity mismatch")
        return record

    def _mutate(self, crystal_id: str, **changes: Any) -> dict[str, Any]:
        record = self.get(crystal_id)
        record.pop("candidate_object", None)
        record.update(changes)
        return self._write(record)

    def promote(self, crystal_id: str, receipt: Any) -> dict[str, Any]:
        if not getattr(receipt, "promoted", False) or getattr(receipt, "candidate_id", "") != crystal_id:
            raise PermissionError("promotion requires a passing held-out replay receipt for this crystal")
        if int(getattr(receipt, "successes", 0)) < 3:
            raise PermissionError("promotion requires at least three held-out replay successes")
        with self._lock:
            record = self.get(crystal_id)
            if record["status"] == "demoted":
                raise PermissionError("demoted coding crystals cannot be re-promoted without a new candidate")
            return self._mutate(crystal_id, status="promoted", receipt=asdict(receipt))

    def demote(self, crystal_id: str, *, reason: str, evidence_digest: str = "") -> dict[str, Any]:
        with self._lock:
            record = self._mutate(crystal_id, status="demoted", demotion={"reason": reason, "evidence_digest": evidence_digest})
        self.record_negative(record["task_family"], kind=reason, evidence_digest=evidence_digest, crystal_id=crystal_id)
        return record

    def record_reuse(self, crystal_id: str, *, run_id: str, outcome: str) -> dict[str, Any]:
        with self._lock:
            record = self.get(crystal_id)
            reuses = list(record.get("reuses") or [])[-49:] + [{"run_id": run_id, "outcome": outcome, "at": time.time()}]
            return self._mutate(crystal_id, reuse_count=int(record.get("reuse_count") or 0) + 1, reuses=reuses)

    def record_negative(self, task_family: str, *, kind: str, evidence_digest: str = "", crystal_id: str = "") -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO coding_crystal_negatives(task_family,crystal_id,kind,evidence_digest,created_at) VALUES(?,?,?,?,?)",
                (task_family, crystal_id, kind, evidence_digest, time.time()),
            )

    def negatives(self, task_family: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT task_family,crystal_id,kind,evidence_digest,created_at FROM coding_crystal_negatives "
                "WHERE task_family=? ORDER BY id", (task_family,)).fetchall()
        return [dict(row) for row in rows]

    def scoped_refusal(self, crystal_id: str, scope: str) -> dict[str, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT run_id, receipt_digest FROM coding_crystal_scoped_refusals "
                "WHERE crystal_id=? AND scope_digest=?", (crystal_id, scope)).fetchone()
        if row is None:
            return None
        body = {"crystal_id": crystal_id, "scope_digest": scope, "run_id": row["run_id"],
                "reason": "resolver_refused_before_mutation"}
        if _digest(body) != row["receipt_digest"]:
            raise ValueError("scoped crystal negative receipt integrity mismatch")
        return {**body, "receipt_digest": row["receipt_digest"]}

    def record_scoped_refusal(self, crystal_id: str, scope: str, run_id: str) -> dict[str, str]:
        receipt = _digest({"crystal_id": crystal_id, "scope_digest": scope, "run_id": run_id,
                           "reason": "resolver_refused_before_mutation"})
        with self._connect() as connection:
            connection.execute("INSERT OR IGNORE INTO coding_crystal_scoped_refusals VALUES(?,?,?,?)",
                               (crystal_id, scope, run_id, receipt))
        saved = self.scoped_refusal(crystal_id, scope)
        assert saved is not None
        return saved

    def active_for_family(self, task_family: str) -> CodingCrystalCandidate | None:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT crystal_id FROM coding_crystals WHERE task_family=? ORDER BY updated_at DESC", (task_family,)).fetchall()
        for row in rows:
            try:
                record = self.get(row["crystal_id"])
            except (LookupError, ValueError):
                continue  # fail closed: tampered records are never served
            if record["status"] == "promoted":
                return record["candidate_object"]
        return None


# --- Held-out replay, authority and planning-time reuse --------------------------------------------

def replay_candidate(registry: CodingCrystalRegistry, candidate: CodingCrystalCandidate, variants: Sequence[Any],
                     run_variant: Any, *, minimum_successes: int = 3, promote: bool = True,
                     reproduction: Mapping[str, Any] | None = None) -> Any:
    """Promote only when every held-out variant replays verified (and there are at least three).

    ``promote=False`` records the passing receipt without promoting (PGEC 2.4 Promotion Sovereignty: production
    callers promote only on an explicit operator act)."""
    from app.kernel.compute.heldout_replay import HeldOutReplayGate

    candidate.validate()
    minimum = max(3, int(minimum_successes))
    record = {"mode": "learn", "candidate_digest": candidate.digest, "minimum_successes": minimum,
              **dict(reproduction or {})}
    receipt = HeldOutReplayGate().evaluate(candidate.crystal_id, variants, run_variant, minimum_successes=minimum,
                                           envelope_digest=candidate.source_envelope_digest, reproduction=record)
    if receipt.promoted:
        if promote:
            registry.promote(candidate.crystal_id, receipt)
    else:
        registry.record_negative(candidate.task_family, kind="heldout_replay_failed",
                                 evidence_digest=_digest(asdict(receipt)), crystal_id=candidate.crystal_id)
    return receipt


class CodingCrystalAuthority:
    """Signs one-use activation capabilities binding crystal, run and parameters (Ed25519)."""

    AUTHORITY = "beast.coding_crystal"

    def __init__(self, signing_key: Any, *, key_id: str, audience: str = "beast.agent_planner_runtime",
                 policy_generation: str = "coding-crystal-v1", ttl_seconds: float = 600.0):
        if signing_key is None or not key_id:
            raise ValueError("coding crystal authority requires a signing key and key id")
        self._signing_key = signing_key
        self.key_id = key_id
        self.audience = audience
        self.policy_generation = policy_generation
        self.ttl_seconds = max(1.0, min(float(ttl_seconds), 3600.0))

    def verifier(self) -> Any:
        return self._signing_key.public_key()

    def sign(self, data: bytes) -> bytes:
        """Sign publication digests; the private key never leaves this object."""
        return self._signing_key.sign(bytes(data))

    @staticmethod
    def request_digest(candidate: CodingCrystalCandidate, run_id: str, parameters: Mapping[str, Any]) -> str:
        return _digest({"crystal": candidate.digest, "run_id": run_id, "parameters": _digest(dict(parameters))})

    def issue(self, candidate: CodingCrystalCandidate, *, run_id: str, parameters: Mapping[str, Any],
              appraisal_ref: str) -> dict[str, Any]:
        import base64
        import secrets
        import uuid

        from app.kernel.integration.one_use_capability import OneUseCapability

        item = OneUseCapability(
            capability_id=f"ccap-{uuid.uuid4().hex}", request_digest=self.request_digest(candidate, run_id, parameters),
            authority=self.AUTHORITY, expires_at=time.time() + self.ttl_seconds, nonce=secrets.token_hex(16),
            signature="", audience=self.audience, policy_generation=self.policy_generation,
            appraisal_ref=appraisal_ref, key_id=self.key_id,
        )
        signature = base64.b64encode(self._signing_key.sign(item.body())).decode("ascii")
        return {**asdict(item), "signature": signature}


class CodingCrystalPlanner:
    """Select a promoted crystal for a run, gate applicability, consume a one-use capability, open a session."""

    def __init__(self, registry: CodingCrystalRegistry, authority: CodingCrystalAuthority, ledger: Any, *,
                 replay_candidate_id: str = "", economy: Any = None, lattice: Any = None,
                 scoped_negatives: bool = False):
        self.registry = registry
        self.authority = authority
        self.ledger = ledger
        self.replay_candidate_id = replay_candidate_id
        self.scoped_negatives = scoped_negatives
        self.economy = economy  # optional CrystalReuseEconomy: shadow-accounted reduction receipts (D7)
        self.lattice = lattice  # optional CrystalLattice: demotion propagates to every containing composite

    def _select(self, task_family: str, nominated: str = "") -> tuple[CodingCrystalCandidate | None, str]:
        if nominated and not self.replay_candidate_id:  # D9/lattice nomination: still must be promoted, same family
            try:
                record = self.registry.get(nominated)
            except (LookupError, ValueError):
                return None, ""
            candidate = record["candidate_object"]
            if record["status"] != "promoted" or candidate.task_family != task_family:
                return None, ""
            return candidate, record["record_digest"]
        if self.replay_candidate_id:
            record = self.registry.get(self.replay_candidate_id)
            candidate = record["candidate_object"]
            if record["status"] == "demoted" or candidate.task_family != task_family:
                return None, ""
            return candidate, record["record_digest"]
        candidate = self.registry.active_for_family(task_family)
        if candidate is None:
            return None, ""
        return candidate, self.registry.get(candidate.crystal_id)["record_digest"]

    @staticmethod
    def _applicability(run: Mapping[str, Any], root: Path) -> tuple[str, dict[str, Any]]:
        from app.kernel.agents.verification_planner import verified_handoff_command

        request = run.get("request") if isinstance(run.get("request"), Mapping) else {}
        if request.get("post_session_closure") != "verified_handoff":
            return "verified_handoff_required", {}
        target = str(request.get("implementation_target") or "").strip()
        if not target:
            return "implementation_target_missing", {}
        relative = Path(target)
        if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".py":
            return "implementation_target_unsafe", {}
        resolved = (root / relative).resolve()
        if root not in resolved.parents or not resolved.is_file():
            return "implementation_target_absent", {}
        tests = request.get("required_test_files")
        if not isinstance(tests, list) or not tests or not all((root / str(item)).is_file() for item in tests):
            return "required_tests_absent", {}
        try:
            command = verified_handoff_command(dict(run))
        except ValueError:
            return "verify_command_refused", {}
        if not command:
            return "verify_command_missing", {}
        return "", {"implementation_target": target, "verify_command": list(command)}

    def activate(self, run: Mapping[str, Any], run_id: str, *, engine: Any, capability: Mapping[str, Any] | None = None,
                 nominated_crystal_id: str = ""):
        request = run.get("request") if isinstance(run.get("request"), Mapping) else {}
        family = str(request.get("task_family") or "")
        if not family:
            return None
        candidate, record_digest = self._select(family, nominated_crystal_id)
        if candidate is None:
            return None
        root = Path(str(getattr(engine, "workspace_root", "") or run.get("root_path") or ".")).resolve()

        def refuse(reason: str) -> None:
            engine.emit(run_id, "agent.crystal.refused", {"crystal_id": candidate.crystal_id, "reason": reason})
            self.registry.record_negative(family, kind=f"refused:{reason.split(':', 1)[0]}",
                                          evidence_digest=_digest({"run_id": run_id}), crystal_id=candidate.crystal_id)
            return None

        try:
            candidate.validate()
        except ValueError:
            return refuse("crystal_invalid")
        reason, parameters = self._applicability(run, root)
        if reason:
            return refuse(reason)
        scope = ""
        if self.scoped_negatives and not self.replay_candidate_id:
            from app.kernel.compute.coder_crystal_feedback import scope_digest

            scope = scope_digest(root, run)
            negative = self.registry.scoped_refusal(candidate.crystal_id, scope) if scope else None
            if negative:
                engine.emit(run_id, "agent.crystal.negative_applied", {
                    **negative, "source_run_id": negative["run_id"], "run_id": run_id,
                })
                return None  # Provider fallback, before issuing or consuming a capability.
        request_digest = self.authority.request_digest(candidate, run_id, parameters)
        capability = dict(capability) if capability is not None else self.authority.issue(
            candidate, run_id=run_id, parameters=parameters, appraisal_ref=record_digest)
        try:
            self.ledger.consume(capability, request_digest=request_digest, authority=self.authority.AUTHORITY,
                                expected_audience=self.authority.audience,
                                expected_policy_generation=self.authority.policy_generation,
                                expected_appraisal_ref=record_digest)
        except (PermissionError, RuntimeError) as exc:
            return refuse(f"capability_refused: {exc}")
        engine.emit(run_id, "agent.crystal.activated", {
            "crystal_id": candidate.crystal_id, "capability_id": capability.get("capability_id", ""),
            "request_digest": request_digest, "mode": "replay" if self.replay_candidate_id else "reuse",
            "parameters_digest": _digest(parameters),
            **({"component_ids": list(candidate.component_ids), "authority": list(candidate.authority)}
               if candidate.component_ids else {}),
        })
        return CodingCrystalSession(candidate, parameters, planner=self, engine=engine, run_id=run_id,
                                    capability=capability, negative_scope=scope)

    # Session callbacks -------------------------------------------------------------------------
    def on_resolver_refused(self, session: CodingCrystalSession, run: Mapping[str, Any]) -> None:
        if not session.negative_scope:
            return
        from app.kernel.compute.coder_crystal_feedback import scope_digest

        # A resolver refusal after an earlier composite mutation is not a pre-mutation negative.
        if any(step["opcode"] == "worktree.replace_exact" for step in session.candidate.steps[:session.cursor]):
            return
        root = Path(session.engine.workspace_root)
        if scope_digest(root, run) != session.negative_scope:
            return
        receipt = self.registry.record_scoped_refusal(
            session.candidate.crystal_id, session.negative_scope, session.run_id)
        if self.lattice is not None:
            witness = self.lattice.witness_scoped_refusal(receipt)
            receipt = {**receipt, **witness}
        session.engine.emit(session.run_id, "agent.crystal.negative_recorded", receipt)

    def on_success(self, session: CodingCrystalSession) -> None:
        if not self.replay_candidate_id:
            self.registry.record_reuse(session.candidate.crystal_id, run_id=session.run_id, outcome="verified")

    def on_postcondition_failed(self, session: CodingCrystalSession, evidence_digest: str) -> None:
        if self.replay_candidate_id:
            self.registry.record_negative(session.candidate.task_family, kind="replay_postcondition_failed",
                                          evidence_digest=evidence_digest, crystal_id=session.candidate.crystal_id)
        else:
            record = self.registry.demote(session.candidate.crystal_id, reason="postcondition_failed", evidence_digest=evidence_digest)
            if self.economy is not None:  # false reuse -> demotion claws back every credit (v0.9 7.13.1)
                binding = self.economy.ledger.space_binding(session.candidate.crystal_id) or {}
                provenance = dict(record.get("provenance") or {})
                self.economy.ledger.record_false_reuse(
                    session.candidate.crystal_id, publisher_id=str(binding.get("publisher_id") or provenance.get("signer_key_id") or ""),
                    space_id=str(binding.get("space_id") or ""), evidence_digest=evidence_digest)
                self.economy.ledger.clawback(session.candidate.crystal_id, reason="demoted:postcondition_failed",
                                             evidence_digest=evidence_digest)
            if self.lattice is not None:  # lattice spine: demote upward and claw back every parent's premium
                try:
                    cascade = self.lattice.demote(session.candidate.crystal_id, reason="postcondition_failed",
                                                  evidence_digest=evidence_digest)
                except LookupError:
                    cascade = {"demoted": []}
                for ancestor in cascade["demoted"][1:]:
                    if self.economy is not None:
                        self.economy.ledger.clawback(ancestor, reason=f"component_demoted:{session.candidate.crystal_id}",
                                                     evidence_digest=evidence_digest)

    def on_reuse_sealed(self, session: CodingCrystalSession, envelope: Any) -> dict[str, Any] | None:
        """Called by the runtime after a crystal run's Episode Envelope is sealed (measured budget available)."""
        if self.economy is None or not session.succeeded:
            return None
        record = self.registry.get(session.candidate.crystal_id)
        return self.economy.on_reuse_sealed(record=record, candidate=session.candidate, envelope=envelope,
                                            replay=bool(self.replay_candidate_id))


class CodingCrystalSession:
    """Supplies recipe decisions to the planner runtime, syncing on the runtime's own observations."""

    MAX_ISSUES_PER_STEP = 2

    def __init__(self, candidate: CodingCrystalCandidate, parameters: Mapping[str, Any], *, planner: Any, engine: Any,
                 run_id: str, capability: Mapping[str, Any], negative_scope: str = ""):
        self.candidate = candidate
        self.parameters = dict(parameters)
        self.planner = planner
        self.engine = engine
        self.run_id = run_id
        self.capability = dict(capability)
        self.negative_scope = negative_scope
        self.cursor = 0
        self.aborted = ""
        self.succeeded = False
        self._seen: set[str] | None = None
        self._bound = False
        self._issues = 0
        self._target_content = ""
        self._verify_output = ""
        self._proposal: dict[str, str] | None = None

    @property
    def step(self) -> Mapping[str, str] | None:
        return self.candidate.steps[self.cursor] if self.cursor < len(self.candidate.steps) else None

    def abort(self, reason: str) -> None:
        if self.aborted or self.succeeded:
            return
        self.aborted = reason
        self.engine.emit(self.run_id, "agent.crystal.aborted", {
            "crystal_id": self.candidate.crystal_id, "reason": reason, "step": self.cursor,
        })

    def _advance(self) -> None:
        self.cursor += 1
        self._issues = 0

    def _observe(self, observation: Mapping[str, Any]) -> None:
        tool = str(observation.get("tool_id") or "")
        step = self.step
        expected_tool = str(step["tool_id"]) if step else ""
        status = str(observation.get("status") or "")
        result = observation.get("result") if isinstance(observation.get("result"), Mapping) else {}
        if tool == "worktree.bind":
            self._bound = status == "completed" or self._bound
            if expected_tool == "worktree.bind":
                self._advance()
            return
        if step is not None and tool == expected_tool:
            if tool == "workspace.read_range":
                if status != "completed" or str(result.get("path") or observation.get("arguments", {}).get("path")) != self.parameters["implementation_target"]:
                    return self.abort("inspect_failed")
                self._target_content = str(result.get("content") or "")
            elif tool == "worktree.verify":
                returncode = result.get("returncode")
                passed = status == "completed" and returncode == 0
                if step["expect"] == "fail":
                    if passed:
                        return self.abort("precondition_not_failing")
                    self._verify_output = verify_output(observation)
                elif step["expect"] == "pass":
                    if not passed:
                        self.abort("postcondition_failed")
                        self.planner.on_postcondition_failed(self, str(observation.get("evidence_digest") or ""))
                        return None
                    self._advance()
                    self.succeeded = True
                    self.engine.emit(self.run_id, "agent.crystal.completed", {
                        "crystal_id": self.candidate.crystal_id, "capability_id": self.capability.get("capability_id", ""),
                    })
                    self.planner.on_success(self)
                    return None
            elif tool == "worktree.replace_exact" and status != "completed":
                return self.abort("actuation_failed")
            self._advance()
            return None
        if tool in EXPLORATION_TOOLS or tool in RUNTIME_CLOSURE_TOOLS:
            return None  # read-only or runtime closure steps never change the recipe position
        if tool == "worktree.verify" and self.cursor < 2:
            return None
        return self.abort("foreign_step:" + tool)

    def sync(self, state: Any) -> None:
        """Fold new runtime observations into the recipe position (also used at run end)."""
        observations = [item for item in getattr(state, "observations", []) if isinstance(item, Mapping)]
        if self._seen is None:
            self._seen = {str(item.get("observation_id") or id(item)) for item in observations}
            self._bound = any(item.get("tool_id") == "worktree.bind" and item.get("status") == "completed" for item in observations)
        for item in observations:
            key = str(item.get("observation_id") or id(item))
            if key in self._seen:
                continue
            self._seen.add(key)
            if self.aborted:
                break
            self._observe(item)

    def next_decision(self, run: Mapping[str, Any], state: Any):
        from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType

        self.sync(state)
        if self.aborted:
            return None
        while self.step is not None:
            step = self.step
            opcode = str(step["opcode"])
            if opcode == "worktree.bind" and self._bound:
                self._advance()
                continue
            if opcode == "repair.resolve_constant":
                self._proposal = resolve_constant(self._verify_output, self._target_content)
                if not self._proposal:
                    self.abort("resolver_refused")
                    if self.negative_scope:
                        self.planner.on_resolver_refused(self, run)
                    return None
                self._advance()
                continue
            if opcode == "crystal.complete":
                if not self.succeeded:
                    self.abort("postcondition_missing")
                    return None
                return PlannerDecision(decision_type=PlannerDecisionType.COMPLETE,
                                       summary=f"Coding crystal {self.candidate.crystal_id} repaired "
                                               f"{self.parameters['implementation_target']} and verification passed.",
                                       rationale="crystal.complete")
            tool = str(step["tool_id"])
            if CODING_OPCODE_TOOLS.get(opcode) != tool or tool not in REVIEWED_TOOLS:
                self.abort("unreviewed_tool")
                return None
            if self._issues >= self.MAX_ISSUES_PER_STEP:
                self.abort("step_not_executed")
                return None
            self._issues += 1
            target = self.parameters["implementation_target"]
            if opcode == "worktree.inspect":
                arguments: dict[str, Any] = {"path": target, "start_line": 1, "line_count": 400}
            elif opcode == "worktree.bind":
                arguments = {"objective": f"coding crystal {self.candidate.crystal_id}"}
            elif opcode == "worktree.verify":
                arguments = {"command": list(self.parameters["verify_command"])}
            else:
                if self._proposal is None:
                    self.abort("resolver_refused")
                    return None
                arguments = {"path": target, "old_text": self._proposal["old_text"], "new_text": self._proposal["new_text"]}
            return PlannerDecision(decision_type=PlannerDecisionType.TOOL, tool_id=tool, arguments=arguments,
                                   rationale=f"crystal:{self.candidate.crystal_id}:{opcode}")
        return None
