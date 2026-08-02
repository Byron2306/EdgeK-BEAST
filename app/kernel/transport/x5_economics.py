from __future__ import annotations
from dataclasses import asdict
from .x5_contracts import LaneEconomics, SelectionPolicy, X5Refusal

def eligible(e: LaneEconomics, p: SelectionPolicy) -> bool:
    if p.require_verified and not e.verified: return False
    if p.require_lawful and not e.lawful: return False
    if e.delivery_ratio < p.minimum_delivery_ratio: return False
    if e.retries > p.maximum_retries: return False
    if e.total_cost > p.maximum_cost: return False
    return True

def choose_lane(measurements: list[LaneEconomics], policy: SelectionPolicy) -> LaneEconomics:
    candidates=[e for e in measurements if eligible(e,policy)]
    if not candidates: raise X5Refusal("no lawful verified transport lane")
    return min(candidates,key=lambda e:(e.total_cost,e.retries,-e.delivery_ratio,e.lane))

def economics_dict(e: LaneEconomics) -> dict:
    d=asdict(e); d["total_cost"]=e.total_cost; return d
