"""Fail-closed paired quality evaluation for crystallized coding routes."""
from __future__ import annotations
import hashlib, json, random
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping
from app.kernel.sensorium.contracts_hash import content_hash

HARD_GATES = ("tests_passed", "security_scan_passed", "no_secret_leak", "no_unrelated_changes")
RUBRIC = ("correctness", "maintainability", "minimality", "compatibility", "operational_safety", "diagnostic_usefulness")

@dataclass(frozen=True)
class QualityAttempt:
    task_id: str; lane: str; patch: str; tests_passed: bool; security_scan_passed: bool
    no_secret_leak: bool; no_unrelated_changes: bool; provider_calls: int; elapsed_ms: float
    origin_amortized_ms: float = 0.0; verifier_ms: float = 0.0
    def hard_gate_passed(self) -> bool: return all(bool(getattr(self, key)) for key in HARD_GATES)
    def total_ms(self) -> float: return self.elapsed_ms + self.origin_amortized_ms + self.verifier_ms
    @property
    def patch_digest(self) -> str: return content_hash({"task_id": self.task_id, "patch": self.patch})

class QualityEquivalenceHarness:
    def __init__(self, *, seed: int = 0, noninferiority_margin: float = 0.25):
        if noninferiority_margin < 0: raise ValueError("noninferiority margin must be nonnegative")
        self.seed, self.noninferiority_margin = seed, noninferiority_margin
    def blind_packet(self, attempts: list[QualityAttempt]) -> tuple[list[dict[str, Any]], dict[str, str]]:
        packet=[]; key={}
        for index, a in enumerate(attempts):
            blind_id=hashlib.sha256(f"{self.seed}:{a.task_id}:{a.lane}:{index}".encode()).hexdigest()[:16]
            packet.append({"blind_id": blind_id,"task_id":a.task_id,"patch":a.patch,"hard_gates":{"passed":a.hard_gate_passed()}})
            key[blind_id]=a.lane
        random.Random(self.seed).shuffle(packet)
        return packet,key
    def score(self, attempt: QualityAttempt, review: Mapping[str, float]) -> dict[str, Any]:
        unknown=set(review)-set(RUBRIC)
        if unknown: raise ValueError(f"unknown rubric dimensions: {sorted(unknown)}")
        values={name:float(review.get(name,0.0)) for name in RUBRIC}
        if any(not 1.0 <= value <= 5.0 for value in values.values()): raise ValueError("review values must be 1..5")
        return {"task_id":attempt.task_id,"lane":attempt.lane,"hard_gate_passed":attempt.hard_gate_passed(),"rubric":values,"mean_score":round(sum(values.values())/len(values),4) if attempt.hard_gate_passed() else 0.0,"total_ms":attempt.total_ms(),"provider_calls":attempt.provider_calls,"patch_digest":attempt.patch_digest}
    def _bootstrap_ci(self, deltas: list[float], samples: int = 4000) -> tuple[float, float]:
        if not deltas: raise ValueError("paired deltas required")
        rng=random.Random(self.seed); means=[]
        for _ in range(samples): means.append(sum(rng.choice(deltas) for _ in deltas)/len(deltas))
        means.sort(); return round(means[int(.025*(samples-1))],4),round(means[int(.975*(samples-1))],4)
    def receipt(self, attempts: list[QualityAttempt], reviews: Mapping[str, Mapping[str, float]], *, preregistration: Mapping[str, Any]) -> dict[str, Any]:
        by={(a.task_id,a.lane):a for a in attempts}; tasks=sorted({a.task_id for a in attempts})
        if any((task,"ephemeral") not in by or (task,"crystallized") not in by for task in tasks): raise ValueError("every task requires ephemeral and crystallized attempts")
        scores=[]; deltas=[]
        for task in tasks:
            e,c=by[task,"ephemeral"],by[task,"crystallized"]
            es=self.score(e,reviews[e.patch_digest]); cs=self.score(c,reviews[c.patch_digest]); scores += [es,cs]
            deltas.append(round(cs["mean_score"]-es["mean_score"],4))
        safe=all(s["hard_gate_passed"] for s in scores); ci=self._bootstrap_ci(deltas)
        receipt={"beast_object_type":"crystallized_compute_quality_equivalence_receipt","version":"1.1","seed":self.seed,"preregistration":dict(preregistration),"preregistration_digest":content_hash(preregistration),"rubric":RUBRIC,"hard_gates":HARD_GATES,"scores":scores,"paired_quality_deltas":deltas,"mean_quality_delta":round(sum(deltas)/len(deltas),4),"bootstrap_95_ci":ci,"noninferiority_margin":self.noninferiority_margin,"all_hard_gates_passed":safe,"quality_noninferior":bool(safe and ci[0] >= -self.noninferiority_margin),"quality_superior":bool(safe and ci[0] > 0),"claim_boundary":"paired local quality result only; blinded independent reviewers and held-out real repositories are required for promotion"}
        receipt["receipt_digest"]=content_hash(receipt); return receipt
    def write(self, receipt: Mapping[str, Any], path: Path) -> None: path.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8")
