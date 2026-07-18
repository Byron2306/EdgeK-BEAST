"""Independent, sealed evaluation laboratory for frontier-quality crystals.

The Crucible records evidence; it never authorizes a crystal or changes a
production route. Hidden verifier material remains outside public exports.
"""
from __future__ import annotations
import hashlib, json, math, random, statistics, time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping
from app.kernel.sensorium.contracts_hash import content_hash

Tier = Literal["C0", "C1", "C2", "C3", "C4", "C5", "C6"]
Lane = Literal["frontier_native", "frontier_governed", "local_baseline", "crystal_only", "crystal_hybrid", "placebo_crystal"]
LANES: tuple[Lane, ...] = ("frontier_native", "frontier_governed", "local_baseline", "crystal_only", "crystal_hybrid", "placebo_crystal")
ELIGIBLE_TIERS = {"C1", "C2", "C3"}

@dataclass(frozen=True)
class CrucibleHypotheses:
    noninferiority_margin: float = .05
    safe_false_execution_max: float = .02
    confidence_levels: tuple[float, float] = (.95, .99)
    frozen_at: float = field(default_factory=time.time)

@dataclass(frozen=True)
class SealedTask:
    task_id: str; family: str; tier: Tier; repository_digest: str; specification_digest: str
    hidden_verifier_digest: str; expected_eligible: bool; language: str = "python"
    def commitment(self) -> str: return content_hash(asdict(self))

@dataclass(frozen=True)
class ApplicabilityDecision:
    eligible: bool; confidence: float; matched_preconditions: tuple[str, ...] = ()
    unmatched_preconditions: tuple[str, ...] = (); disqualifiers: tuple[str, ...] = ()
    def __post_init__(self):
        if not 0 <= self.confidence <= 1: raise ValueError("confidence must be 0..1")

@dataclass(frozen=True)
class LaneDirective:
    lane: Lane; action: Literal["frontier", "crystal", "fallback", "abstain", "placebo"]
    reason: str; counted_as_crystal_execution: bool

class AgentLaneController:
    """Routes a sealed task without granting authority from similarity alone."""
    def direct(self, lane: Lane, decision: ApplicabilityDecision, *, crystal_verified: bool, placebo: bool = False) -> LaneDirective:
        if lane in {"frontier_native", "frontier_governed", "local_baseline"}:
            return LaneDirective(lane,"frontier","baseline lane",False)
        if lane == "placebo_crystal":
            return LaneDirective(lane,"placebo","deliberately stale/shuffled crystal must be verified independently",True)
        if decision.eligible and crystal_verified:
            return LaneDirective(lane,"crystal","eligible contract and verifier proof",True)
        if lane == "crystal_hybrid":
            return LaneDirective(lane,"fallback","ineligible or unverified crystal",False)
        return LaneDirective(lane,"abstain","crystal-only safe refusal",False)

@dataclass(frozen=True)
class CrucibleRun:
    task_id: str; lane: Lane; run_id: str; verified_completion: bool; patch_digest: str
    applicability: ApplicabilityDecision; cloud_calls: int; cloud_tokens: int; cost_usd: float
    latency_ms: float; hard_gates: Mapping[str, bool]; runner_image_digest: str
    model_identity: str; tool_schema_digest: str; policy_generation: str
    crystal_ir_digest: str = ""; lattice_checkpoint: str = ""; attestation_digest: str = ""
    sensorium_episode_digest: str = ""; rollback_verified: bool = False
    def valid(self) -> bool:
        common=bool(self.task_id and self.run_id and self.patch_digest and self.runner_image_digest and self.model_identity and self.tool_schema_digest and self.policy_generation and self.sensorium_episode_digest and self.attestation_digest and all(self.hard_gates.values()))
        crystal_required = self.lane in {"crystal_only","crystal_hybrid","placebo_crystal"}
        return common and (not crystal_required or bool(self.crystal_ir_digest and self.lattice_checkpoint))

class SensoriumRunRecorder:
    """Accept only complete proof-carrying records; no partial telemetry rows."""
    def record(self, root: Path, run: CrucibleRun) -> str:
        if not run.valid(): raise ValueError("incomplete Crucible proof-carrying run")
        path=root/"runs"/f"{run.run_id}.json"; path.parent.mkdir(parents=True,exist_ok=True)
        payload=asdict(run); payload["run_digest"]=content_hash(payload); path.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        return payload["run_digest"]

class SealedTaskFoundry:
    def __init__(self, hypotheses: CrucibleHypotheses): self.hypotheses = hypotheses
    def manifest(self, tasks: Iterable[SealedTask], *, branch_digest: str, lattice_digest: str, policy_digest: str) -> dict[str, Any]:
        items=sorted(tasks,key=lambda t:t.task_id)
        if len({t.task_id for t in items}) != len(items): raise ValueError("task ids must be unique")
        payload={"beast_object_type":"crystal_frontier_crucible_manifest","version":"1.0","hypotheses":asdict(self.hypotheses),"branch_digest":branch_digest,"lattice_digest":lattice_digest,"policy_digest":policy_digest,"tasks":[asdict(t) for t in items],"task_commitments":[t.commitment() for t in items]}
        payload["manifest_digest"]=content_hash(payload); return payload

class HiddenVerifierVault:
    """Private verifier storage with public commitments only."""
    def commit(self, root: Path, task_id: str, verifier: bytes) -> str:
        private=root/"hidden-verifiers"/f"{task_id}.bin"; private.parent.mkdir(parents=True,exist_ok=True); private.write_bytes(verifier)
        return "sha256:"+hashlib.sha256(verifier).hexdigest()
    def verify(self, root: Path, task_id: str, expected_digest: str) -> bool:
        path=root/"hidden-verifiers"/f"{task_id}.bin"
        return path.is_file() and "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()==expected_digest

class StatisticalEvidenceEngine:
    def __init__(self, *, seed: int = 0): self.seed=seed
    def paired_ci(self, deltas: list[float], level: float, samples: int = 10000) -> tuple[float,float]:
        if not deltas: raise ValueError("paired outcomes required")
        rng=random.Random(self.seed); values=sorted(sum(rng.choice(deltas) for _ in deltas)/len(deltas) for _ in range(samples)); alpha=(1-level)/2
        return round(values[int(alpha*(samples-1))],4),round(values[int((1-alpha)*(samples-1))],4)
    @staticmethod
    def required_binary_pairs(*, frontier_rate: float, noninferiority_margin: float, alpha: float=.01, power: float=.9) -> int:
        """Conservative normal approximation; protocol must publish inputs before runs."""
        if not 0 < frontier_rate < 1 or not 0 < noninferiority_margin < 1: raise ValueError("rates/margin must be in (0,1)")
        z_alpha={.05:1.645,.01:2.326}.get(alpha); z_power={.8:.842,.9:1.282}.get(power)
        if z_alpha is None or z_power is None: raise ValueError("supported alpha .05/.01 and power .8/.9")
        variance=2*frontier_rate*(1-frontier_rate)
        return math.ceil(((z_alpha+z_power)**2*variance)/(noninferiority_margin**2))
    def evaluate(self, tasks: Iterable[SealedTask], runs: Iterable[CrucibleRun], hypotheses: CrucibleHypotheses) -> dict[str,Any]:
        rows=list(runs); by={(r.task_id,r.lane):r for r in rows}; task_rows=list(tasks)
        eligible=[t for t in task_rows if t.expected_eligible]
        paired=[int(by[t.task_id,"crystal_only"].verified_completion)-int(by[t.task_id,"frontier_native"].verified_completion) for t in eligible if (t.task_id,"crystal_only") in by and (t.task_id,"frontier_native") in by]
        hybrid=[int(by[t.task_id,"crystal_hybrid"].verified_completion)-int(by[t.task_id,"frontier_native"].verified_completion) for t in task_rows if (t.task_id,"crystal_hybrid") in by and (t.task_id,"frontier_native") in by]
        ineligible=[r for t in task_rows if not t.expected_eligible for r in rows if r.task_id==t.task_id and r.lane in {"crystal_only","crystal_hybrid"}]
        false_exec=sum(1 for r in ineligible if r.applicability.eligible and r.verified_completion)/len(ineligible) if ineligible else None
        ci95=self.paired_ci(paired,.95) if paired else None; ci99=self.paired_ci(paired,.99) if paired else None; hci95=self.paired_ci(hybrid,.95) if hybrid else None
        return {"beast_object_type":"crystal_frontier_crucible_statistics","eligible_pair_count":len(paired),"hybrid_pair_count":len(hybrid),"eligible_quality_delta":round(statistics.mean(paired),4) if paired else None,"eligible_ci95":ci95,"eligible_ci99":ci99,"hybrid_completion_delta":round(statistics.mean(hybrid),4) if hybrid else None,"hybrid_ci95":hci95,"false_crystal_execution_rate":false_exec,"h1_quality_parity":bool(ci95 and ci99 and ci95[0]>=-hypotheses.noninferiority_margin and ci99[0]>=-hypotheses.noninferiority_margin),"h2_hybrid_superiority":bool(hci95 and hci95[0]>0),"h3_safe_abstention":bool(false_exec is not None and false_exec<hypotheses.safe_false_execution_max),"claim_boundary":"pilot statistics; requires pre-registered sample size, independent verifier/reviewer, and sealed held-out corpus"}

class CrucibleDatasetGate:
    """Reject partial, duplicate, or evidence-incomplete lane datasets."""
    def validate(self, tasks: Iterable[SealedTask], runs: Iterable[CrucibleRun]) -> dict[str, Any]:
        tasks=list(tasks); runs=list(runs); expected={t.task_id for t in tasks}; by: dict[str,set[str]]={t.task_id:set() for t in tasks}; errors=[]
        seen=set()
        for run in runs:
            key=(run.task_id,run.lane,run.run_id)
            if key in seen: errors.append(f"duplicate run {key}")
            seen.add(key)
            if run.task_id not in expected: errors.append(f"unknown task {run.task_id}")
            else: by[run.task_id].add(run.lane)
            if not run.valid(): errors.append(f"incomplete evidence {run.run_id}")
        missing={task:sorted(set(LANES)-lanes) for task,lanes in by.items() if set(LANES)-lanes}
        return {"valid":not errors and not missing,"errors":errors,"missing_lanes":missing,"task_count":len(tasks),"run_count":len(runs)}

def preregistered_ablations() -> tuple[dict[str,str],...]:
    return (
        {"id":"crystals_disabled","question":"Does governance alone explain improvement?"},
        {"id":"semantic_cache_only","question":"Is value merely fuzzy retrieval?"},
        {"id":"mission_lattice_only","question":"Is structural matching sufficient?"},
        {"id":"negative_capability_removed","question":"Do failure memories prevent unsafe reuse?"},
        {"id":"sensorium_removed","question":"Do physical preconditions matter?"},
        {"id":"verifier_plan_removed","question":"Are tests doing all the work?"},
        {"id":"frontier_fallback_removed","question":"How much generality comes from escalation?"},
        {"id":"stale_crystal","question":"Does decay/revocation protect quality?"},
        {"id":"poisoned_crystal","question":"Can plausible invalid capability be rejected?"},
    )

class LongitudinalEvidenceEngine:
    """H4: coverage may grow only if quality, calibration, and safety do not decay."""
    def evaluate(self, releases: Iterable[Mapping[str, float]], *, max_quality_drop: float=.02, max_safety_drop: float=.005, max_calibration_increase: float=.02) -> dict[str, Any]:
        rows=list(releases)
        if len(rows)<2: return {"h4_durable_accumulation":False,"reason":"at least two sealed releases required"}
        required={"coverage","quality","safety","calibration_error"}
        if any(not required <= set(row) for row in rows): raise ValueError("release rows require coverage/quality/safety/calibration_error")
        first,last=rows[0],rows[-1]; coverage=float(last['coverage'])-float(first['coverage']); quality=float(last['quality'])-float(first['quality']); safety=float(last['safety'])-float(first['safety']); calibration=float(last['calibration_error'])-float(first['calibration_error'])
        return {"beast_object_type":"crystal_frontier_crucible_longitudinal_evidence","release_count":len(rows),"coverage_delta":round(coverage,4),"quality_delta":round(quality,4),"safety_delta":round(safety,4),"calibration_error_delta":round(calibration,4),"h4_durable_accumulation":bool(coverage>0 and quality>=-max_quality_drop and safety>=-max_safety_drop and calibration<=max_calibration_increase),"claim_boundary":"requires sequential independently sealed releases and post-release outcomes"}

class BlindReviewChamber:
    def packet(self, runs: Iterable[CrucibleRun], *, seed: int) -> tuple[list[dict[str,Any]],dict[str,str]]:
        packet=[]; key={}
        for i,r in enumerate(runs):
            blind=hashlib.sha256(f"{seed}:{r.task_id}:{r.lane}:{r.patch_digest}:{i}".encode()).hexdigest()[:20]
            packet.append({"blind_id":blind,"task_id":r.task_id,"patch_digest":r.patch_digest,"hard_gates":dict(r.hard_gates),"rollback_verified":r.rollback_verified})
            key[blind]=r.lane
        random.Random(seed).shuffle(packet); return packet,key

class PublicEvidenceExporter:
    SECRET_FIELDS={"hidden_verifier","reference_solution","private_key","raw_task"}
    def export(self, manifest: Mapping[str,Any], statistics_result: Mapping[str,Any], runs: Iterable[CrucibleRun]) -> dict[str,Any]:
        return {"beast_object_type":"crystal_frontier_crucible_public_evidence","manifest_digest":manifest["manifest_digest"],"statistics":dict(statistics_result),"runs":[{"task_id":r.task_id,"lane":r.lane,"verified_completion":r.verified_completion,"patch_digest":r.patch_digest,"applicability":asdict(r.applicability),"cloud_calls":r.cloud_calls,"cloud_tokens":r.cloud_tokens,"cost_usd":r.cost_usd,"latency_ms":r.latency_ms,"hard_gates":dict(r.hard_gates),"crystal_ir_digest":r.crystal_ir_digest,"lattice_checkpoint":r.lattice_checkpoint,"attestation_digest":r.attestation_digest,"sensorium_episode_digest":r.sensorium_episode_digest,"rollback_verified":r.rollback_verified} for r in runs],"claim_boundary":"public projection excludes hidden verifier/source material"}

def write_json(path: Path, value: Mapping[str,Any]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8")
