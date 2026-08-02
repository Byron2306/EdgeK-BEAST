from __future__ import annotations
from dataclasses import asdict
from typing import Protocol
from .x8_contracts import *

class RemoteReconstructor(Protocol):
    def reconstruct(self, candidate: RemoteResidualCandidate) -> dict: ...

def _remote_allowed(c: RemoteResidualCandidate,p:X8Policy)->bool:
    return c.eligible and c.total_cost_us <= p.maximum_remote_cost_us and c.missing_bytes <= p.maximum_missing_bytes

def decide_remote_residual(remote: RemoteResidualCandidate, local_routes:list[LocalRouteCandidate], policy:X8Policy=X8Policy()) -> tuple[str,int,list[dict]]:
    lawful=[r for r in local_routes if r.lawful and r.verified]
    if not lawful: raise X8Refusal("no lawful local baseline")
    baseline=min(lawful,key=lambda r:(r.cost_us,r.route))
    alternatives=[{"route":r.route,"cost_us":r.cost_us,"eligible":r.lawful and r.verified} for r in local_routes]
    alternatives.append({"route":"remote_residual","candidate_id":remote.candidate_id,"cost_us":remote.total_cost_us,"eligible":_remote_allowed(remote,policy),"missing_bytes":remote.missing_bytes})
    if not _remote_allowed(remote,policy): return baseline.route,baseline.cost_us,alternatives
    if policy.require_positive_savings and remote.total_cost_us >= baseline.cost_us: return baseline.route,baseline.cost_us,alternatives
    return "remote_residual",remote.total_cost_us,alternatives

def execute_x8(remote:RemoteResidualCandidate, local_routes:list[LocalRouteCandidate], reconstructor:RemoteReconstructor, policy:X8Policy=X8Policy()) -> X8DecisionReceipt:
    baseline=min((r for r in local_routes if r.lawful and r.verified),key=lambda r:(r.cost_us,r.route))
    route,cost,alts=decide_remote_residual(remote,local_routes,policy)
    reconstructed=False
    if route=="remote_residual":
        outcome=reconstructor.reconstruct(remote)
        reconstructed=bool(outcome.get("verified")) and outcome.get("object_digest")==remote.object_digest
        if not reconstructed: raise X8Refusal("remote reconstruction verification failed")
    receipt=X8DecisionReceipt(
        phase="X8", selected_route=route, selected_candidate_id=remote.candidate_id if route=="remote_residual" else "",
        selected_cost_us=cost, baseline_route=baseline.route, baseline_cost_us=baseline.cost_us,
        net_savings_us=baseline.cost_us-cost, remote_selected=route=="remote_residual", remote_eligible=_remote_allowed(remote,policy),
        missing_bytes=remote.missing_bytes, local_bytes=remote.local_bytes, object_digest=remote.object_digest,
        trust_verified=remote.trust_verified, manifest_verified=remote.manifest_verified, replay_fresh=remote.replay_fresh,
        reconstruction_verified=reconstructed, promotion_allowed=False, execution_authority_transferred=False,
        authority="route_selection_and_reconstruction_only", alternatives=alts)
    return receipt.seal()
