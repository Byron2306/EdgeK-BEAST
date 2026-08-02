"""Bounded verification-driven residual repair loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from app.kernel.agents.failure_analyst import analyze_failure
from app.kernel.agents.residual_critic import critique_candidate


@dataclass(frozen=True)
class RepairLoopPolicy:
    max_rounds: int = 3
    max_files: int = 1
    max_symbols: int = 1


class VerificationRepairLoop:
    """Retry only the declared semantic residual after fresh verifier failure."""

    def __init__(self, *, solver: Callable[[Dict[str, Any]], Dict[str, Any]], apply: Callable[[str], Dict[str, Any]], verify: Callable[[], Dict[str, Any]], reset: Optional[Callable[[], None]] = None, source: Optional[Callable[[], str]] = None, crystalist: Optional[Callable[[Dict[str, Any]], Any]] = None, policy: RepairLoopPolicy = RepairLoopPolicy()) -> None:
        self.solver = solver
        self.apply = apply
        self.verify = verify
        self.reset = reset
        self.source = source
        self.crystalist = crystalist
        self.policy = policy

    def run(self, *, path: str, symbol: str, old: str, failure: str, diagnostic: str = "") -> Dict[str, Any]:
        if not path or not symbol:
            return {"status": "blocked", "reason": "one target file and symbol are required", "rounds": []}
        rounds = []
        current_failure = failure
        current_diagnostic = diagnostic
        for number in range(1, max(1, self.policy.max_rounds) + 1):
            if self.reset is not None:
                self.reset()
            request = {
                "round": number,
                "path": path,
                "symbol": symbol,
                "previous_patch": old,
                "verifier_failure": current_failure,
                "diagnostic": current_diagnostic,
                "allowed_change": "replacement expression only",
                "output_schema": {"replacement_expression": "string"},
                "scope": {"max_files": self.policy.max_files, "max_symbols": self.policy.max_symbols},
            }
            analysis = analyze_failure(f"{current_failure}\n{current_diagnostic}")
            request["failure_analysis"] = analysis
            request["slot_type"] = analysis["slot_type"]
            if self.crystalist is not None:
                try:
                    scaffold = self.crystalist(request)
                except Exception:
                    scaffold = []
                request["crystal_scaffold"] = scaffold if isinstance(scaffold, (list, tuple, dict)) else [str(scaffold)]
            response = self.solver(request)
            replacement = response.get("replacement_expression") if isinstance(response, dict) else None
            if replacement is None and isinstance(response, dict):
                replacement = response.get("new") or response.get("replacement_statement") or response.get("replacement_import")
            if not isinstance(replacement, str) or not replacement.strip():
                rounds.append({"round": number, "status": "blocked", "reason": "solver did not return one bounded residual", "failure_analysis": analysis})
                return {"status": "blocked", "rounds": rounds, "scope": request["scope"]}
            source_text = self.source() if self.source is not None else old
            slot_type = str(analysis.get("slot_type") or "python_expression")
            if slot_type == "python_expression" and ("\n" in replacement or path in replacement or "import " in replacement):
                rounds.append({"round": number, "status": "blocked", "reason": "residual exceeded one-expression boundary", "failure_analysis": analysis})
                return {"status": "blocked", "rounds": rounds, "scope": request["scope"]}
            critic = critique_candidate(source=source_text, old=old, new=replacement, slot_type=slot_type)
            if critic["status"] != "accepted":
                rounds.append({"round": number, "status": "blocked", "reason": "preflight rejected residual", "critic": critic, "failure_analysis": analysis})
                return {"status": "blocked", "rounds": rounds, "scope": request["scope"]}
            applied = self.apply(replacement)
            verification = self.verify()
            row = {"round": number, "status": "passed" if verification.get("ok") else "failed", "request": request, "critic": critic, "apply": applied, "verification": verification}
            rounds.append(row)
            if verification.get("ok"):
                return {"status": "passed", "rounds": rounds, "repair_rounds": number, "scope": request["scope"]}
            current_failure = str(verification.get("failure") or verification.get("stderr") or "verification failed")
            current_diagnostic = str(verification.get("diagnostic") or "repair residual requires another bounded attempt")
        return {"status": "failed", "rounds": rounds, "repair_rounds": len(rounds), "scope": {"max_files": self.policy.max_files, "max_symbols": self.policy.max_symbols}}
