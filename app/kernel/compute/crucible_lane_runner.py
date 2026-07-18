"""Isolated command adapter for the six Crystal Frontier Crucible lanes."""
from __future__ import annotations
import json, subprocess, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from app.kernel.compute.crystal_frontier_crucible import AgentLaneController, ApplicabilityDecision, CrucibleRun, Lane, SealedTask
from app.kernel.sensorium.contracts_hash import content_hash

@dataclass(frozen=True)
class LaneCommand:
    lane: Lane; command: tuple[str,...]; worktree: Path; model_identity: str
    runner_image_digest: str; tool_schema_digest: str; policy_generation: str
    crystal_ir_digest: str=""; lattice_checkpoint: str=""; attestation_digest: str=""; sensorium_episode_digest: str=""

class CrucibleLaneRunner:
    def __init__(self, *, timeout_seconds: int=300): self.timeout_seconds=timeout_seconds; self.controller=AgentLaneController()
    def run(self, task: SealedTask, spec: LaneCommand, decision: ApplicabilityDecision, *, crystal_verified: bool, placebo: bool=False) -> CrucibleRun:
        directive=self.controller.direct(spec.lane,decision,crystal_verified=crystal_verified,placebo=placebo)
        started=time.perf_counter()
        if directive.action=="abstain": return self._record(task,spec,decision,False,"abstain",0,0,0.,0.,{"abstention":True},False)
        if directive.action=="placebo" and not placebo: raise ValueError("placebo lane requires explicit placebo material")
        completed=subprocess.run(spec.command,cwd=spec.worktree,text=True,capture_output=True,timeout=self.timeout_seconds,check=False)
        elapsed=round((time.perf_counter()-started)*1000,3)
        try: body=json.loads(completed.stdout); assert isinstance(body,dict)
        except Exception: body={"verified_completion":False,"hard_gates":{"runner_protocol":False}}
        gates={str(k):bool(v) for k,v in dict(body.get("hard_gates") or {}).items()}; gates["runner_returncode"] = completed.returncode==0
        return self._record(task,spec,decision,bool(body.get("verified_completion")) and all(gates.values()),content_hash({"stdout":completed.stdout,"stderr":completed.stderr,"command":spec.command}),int(body.get("cloud_calls") or 0),int(body.get("cloud_tokens") or 0),float(body.get("cost_usd") or 0.),elapsed,gates,bool(body.get("rollback_verified")))
    def _record(self,task,spec,decision,ok,patch,calls,tokens,cost,elapsed,gates,rollback):
        return CrucibleRun(task.task_id,spec.lane,content_hash({"task":task.task_id,"lane":spec.lane,"patch":patch,"time":time.time()}),ok,patch,decision,calls,tokens,cost,elapsed,gates,spec.runner_image_digest,spec.model_identity,spec.tool_schema_digest,spec.policy_generation,spec.crystal_ir_digest,spec.lattice_checkpoint,spec.attestation_digest,spec.sensorium_episode_digest,rollback)
