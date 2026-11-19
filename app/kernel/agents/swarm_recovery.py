"""One proposal-only swarm recovery for a failed exact-edit retry."""
from __future__ import annotations

import asyncio
import json
import stat
from pathlib import Path
from urllib.parse import urlsplit

from app.kernel.agents.swarm_specialist import (
    MODEL_ENV, OllamaSwarmRunner, SwarmSpecialistDispatch, _base_url, operational_specialist_route,
)
from app.kernel.sensorium.episode_envelope import _contains_secret

MAX_SOURCE_CHARS = 12000
MAX_FILE_BYTES = 4 * 1024 * 1024
RECOVERY_SCHEMA = {
    "type": "object",
    "properties": {key: {"type": "string"} for key in ("path", "old_text", "new_text")},
    "required": ["path", "old_text", "new_text"],
    "additionalProperties": False,
}


def _eligible_path(name, target):
    if not isinstance(name, str) or not name or (target and target != name):
        return False
    relative = Path(name)
    return (
        not relative.is_absolute() and relative.as_posix() == name and ".." not in relative.parts
        and not any(part.startswith(".") or part.lower() in {"secrets", "credentials"} for part in relative.parts)
        and relative.suffix.lower() not in {".pem", ".key", ".p12", ".pfx"}
    )


def snapshot_refresh_arguments(root, observations, target):
    """Recover one previously inspected checkout span, never refresh stale worktree evidence."""
    if _source_evidence(root, observations, target):
        return None
    seen = set()
    for item in reversed(observations):
        if item.get("status") != "completed" or item.get("tool_id") != "workspace.read_range":
            continue
        result = item.get("result") or {}
        name = result.get("path")
        if not _eligible_path(name, target) or name in seen:
            continue
        seen.add(name)
        if result.get("source_scope") != "workspace_checkout" and not (
            not result.get("source_scope") and result.get("target_execution") == "local_snapshot"
        ):
            continue
        snippet = result.get("content")
        start, end = result.get("start_line"), result.get("end_line")
        if (isinstance(snippet, str) and snippet.strip() and not _contains_secret(snippet)
                and isinstance(start, int) and isinstance(end, int) and 1 <= start <= end):
            return {"path": name, "start_line": start, "line_count": min(1000, end - start + 1)}
    return None


def _source_evidence(root, observations, target):
    evidence = {}
    remaining = MAX_SOURCE_CHARS
    for item in reversed(observations):
        if item.get("status") != "completed" or item.get("tool_id") not in {"workspace.read_range", "worktree.read_file"}:
            continue
        result = item.get("result") or {}
        if item["tool_id"] == "worktree.read_file" and result.get("worktree_root") != str(root):
            continue
        name, snippet = result.get("path"), result.get("content")
        if not _eligible_path(name, target) or not isinstance(snippet, str) or not snippet.strip() or _contains_secret(snippet):
            continue
        relative = Path(name)
        try:
            path = root / relative
            if path.resolve() != path or not stat.S_ISREG(path.stat().st_mode):
                continue
            with path.open("rb") as handle:
                raw = handle.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES:
                continue
            current = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        except (OSError, UnicodeError, ValueError):
            continue
        if snippet not in current:
            continue
        selected = snippet[:max(0, remaining - len(name) - 16)]
        if not selected.strip():
            continue
        text, spans = evidence.setdefault(name, (current, []))
        if text == current and selected not in spans:
            spans.append(selected)
            remaining -= len(selected) + len(name) + 16
        if remaining < 256:
            break
    return evidence


def _plan(kernel_root, swarm_id, parent_id, cause, files, estimated_chars):
    from app.kernel.networking.swarm import SwarmKernel

    kernel = SwarmKernel(db_path=str(kernel_root / ".beast" / "swarm" / "coder-recovery.sqlite3"))
    return kernel.run({
        "run_id": swarm_id,
        "objective": "Propose a bounded exact edit after an agent edit failed",
        "metadata": {"agent_run_id": parent_id, "operation": "invalid_mutation_recovery"},
        "profile": "zeroclaw",
        "task_type": "code_change",
        "failure": cause,
        "execution_result": {"success": False, "error": cause},
        "files": files,
        "estimated_context_tokens": max(1, (estimated_chars + 3) // 4),
        "target_context_tokens": MAX_SOURCE_CHARS // 4,
        "success_criteria": ["Exact observed target and unique old text", "Normal edit authorization and verification"],
    })


async def recover(*, workspace, root, observations, target, objective, cause, run_id, env, timeout, circuits=None):
    """Return candidate arguments and a redacted receipt, never an approval or executed edit."""
    receipt = {"swarm_run_id": f"{run_id}:invalid-mutation", "roles": [], "effect_committed": False,
               "proposal_only": True, "execution_granted": False, "verification_accepted": False}
    endpoint = urlsplit(_base_url(env))
    if (endpoint.scheme not in {"http", "https"} or endpoint.hostname not in {"127.0.0.1", "::1", "localhost"}
            or endpoint.username or endpoint.password or endpoint.path or endpoint.query or endpoint.fragment):
        return None, "specialist_not_loopback", receipt
    if _contains_secret(objective):
        return None, "sensitive_objective", receipt

    def progress(stage: str) -> None:
        receipt["recovery_stage"] = stage

    progress("preparation")
    try:
        async with asyncio.timeout(timeout):
            evidence = await asyncio.to_thread(_source_evidence, root, observations, target)
            if not evidence:
                return None, "no_matching_bound_worktree_evidence", receipt
            report = await asyncio.to_thread(
                _plan, workspace, receipt["swarm_run_id"], run_id, cause, list(evidence),
                sum(len(name) + len(span) + 8 for name, (_, spans) in evidence.items() for span in spans),
            )
            receipt["roles"] = [
                {"role": event["role"], "decision": event["decision"]} for event in report["events"]
            ]
            details = {event["role"]: event["details"] for event in report["events"]}
            if (
                report["status"] != "needs_revision"
                or not all(gate["decision"] == "allow" for gate in report["gates"])
                or details.get("critic", {}).get("decision") != "revise_plan"
                or details.get("hermes", {}).get("route_decision", {}).get("route") != "ollama_residual"
            ):
                return None, "swarm_recovery_not_recommended", receipt

            from app.kernel.compute.perceive import EdgeKIR
            from app.kernel.data_processing.quality_cascade import QualityCascade
            from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog

            paths = [path for path in details["cartographer"]["files"] if path in evidence]
            limit = min(MAX_SOURCE_CHARS, max(0, details["compressor"]["final_tokens"] * 4))
            snippets = {}
            remaining = limit
            for name in paths:
                for span in evidence[name][1]:
                    remaining -= len(name) + 8
                    if remaining <= 0:
                        break
                    selected = span[:remaining]
                    snippets.setdefault(name, []).append(selected)
                    remaining -= len(selected)
            source = "\n\n".join(f"FILE {name}\n{span}" for name, spans in snippets.items() for span in spans)
            if not source:
                return None, "swarm_context_budget_exhausted", receipt
            quality = await asyncio.to_thread(
                QualityCascade().run,
                {"task_id": receipt["swarm_run_id"], "task_class": "exact_edit_recovery_preflight"},
                {"route_id": receipt["swarm_run_id"], "provider": "ollama", "preferred_order": ["git_status"]},
                str(root),
            )
            receipt["preflight_quality_passed"] = quality.get("verification_accepted") is True
            if not receipt["preflight_quality_passed"]:
                return None, "bound_worktree_preflight_failed", receipt

            dispatcher = SwarmSpecialistDispatch(
                runner=OllamaSwarmRunner(base_url=endpoint.geturl(), timeout=timeout, trust_env=False, local_models_only=True),
                governor=ComputeGovernorSpine(enforce=True, circuits=circuits, receipts=GovernorReceiptLog(
                    workspace / ".beast" / "governor" / "swarm-agent-coder.jsonl")),
                env=env,
            )
            ir = EdgeKIR(messages=[], model="local-specialist", max_tokens=1024, temperature=0.0, metadata={
                "objective": objective,
                "source_context": source,
                "diagnostic_context": (
                    "An exact edit was rejected. Return only path, old_text and new_text. "
                    "Use an exact target and copy a unique, non-empty old_text from that file's supplied evidence. "
                    "Return empty fields if the evidence is insufficient. Do not modify files or run commands. "
                    f"Failure: {cause}. Planned checks: {', '.join(details['verifier']['checks'])}."
                ),
                "task_family": "exact_edit_recovery",
                "response_schema": RECOVERY_SCHEMA,
                "response_format": "json_object",
                "quality_cascade": quality,
                "token_budget": MAX_SOURCE_CHARS // 4 + 1536,
            })
            model = str(env.get(MODEL_ENV) or "").strip()
            outcome = await dispatcher.dispatch(
                ir, operational_specialist_route(cause, model), run_id=run_id, progress=progress,
            )
    except TimeoutError:
        return None, "swarm_recovery_timeout", receipt
    for key in ("generated", "usage", "model", "governor_receipt", "governor_outcome"):
        if key in outcome.receipt:
            receipt[key] = outcome.receipt[key]
    if not outcome.dispatched or not outcome.response:
        return None, outcome.reason, receipt

    arguments = json.loads(outcome.response["text"])
    if (not isinstance(arguments, dict) or arguments.keys() != RECOVERY_SCHEMA["properties"].keys()
            or not all(isinstance(value, str) for value in arguments.values())):
        return None, "candidate_schema_rejected", receipt
    name, old, new = (arguments[key] for key in ("path", "old_text", "new_text"))
    if name not in snippets or not old.strip() or old == new or not any(old in span for span in snippets[name]):
        return None, "candidate_outside_exact_edit_contract", receipt
    # Recheck after inference. The usual executor still enforces exact occurrence and authorization.
    fresh = await asyncio.to_thread(_source_evidence, root, observations, name)
    current, spans = fresh.get(name, ("", []))
    if current.count(old) != 1 or not any(old in span for span in spans):
        return None, "candidate_not_grounded_in_bound_worktree", receipt
    return {**arguments, "expected_occurrences": 1}, "candidate_grounded", receipt
