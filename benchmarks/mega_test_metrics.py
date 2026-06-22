"""Metrics for the BEAST definitive mega-test."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple


LANE_B = "beast_no_compute_governor"
LANE_C = "full_beast_compute_governor"


def _key(row: Dict[str, Any]) -> Tuple[str, str, int]:
    return (str(row.get("family")), str(row.get("provider")), int(row.get("occurrence") or 0))


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def compute_qpccd(observations: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute quality-preserving cloud-call displacement from lane records."""

    grouped: Dict[Tuple[str, str, int], Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for row in observations:
        lane = str(row.get("lane") or "")
        if lane:
            grouped[_key(row)][lane] = row

    cases: List[Dict[str, Any]] = []
    denominator = 0
    numerator = 0
    skipped = 0
    for key, lanes in sorted(grouped.items()):
        lane_b = lanes.get(LANE_B)
        lane_c = lanes.get(LANE_C)
        if not lane_b or not lane_c:
            skipped += 1
            continue
        b_calls = int(lane_b.get("cloud_calls") or 0)
        if b_calls <= 0:
            continue
        denominator += 1
        b_completed = _bool_or_none(lane_b.get("completed"))
        c_completed = _bool_or_none(lane_c.get("completed"))
        b_hidden = _bool_or_none(lane_b.get("hidden_passed"))
        c_hidden = _bool_or_none(lane_c.get("hidden_passed"))
        c_calls = int(lane_c.get("cloud_calls") or 0)
        evaluable = None not in {b_completed, c_completed, b_hidden, c_hidden}
        passed = bool(
            evaluable
            and int(bool(c_completed)) >= int(bool(b_completed))
            and int(bool(c_hidden)) >= int(bool(b_hidden))
            and c_calls < b_calls
        )
        numerator += int(passed)
        family, provider, occurrence = key
        cases.append({
            "family": family,
            "provider": provider,
            "occurrence": occurrence,
            "passed": passed,
            "evaluable": evaluable,
            "lane_b_cloud_calls": b_calls,
            "lane_c_cloud_calls": c_calls,
            "lane_b_completed": b_completed,
            "lane_c_completed": c_completed,
            "lane_b_hidden_passed": b_hidden,
            "lane_c_hidden_passed": c_hidden,
        })

    return {
        "metric": "qpc_cloud_call_displacement",
        "numerator": numerator,
        "denominator": denominator,
        "rate": round(numerator / denominator, 6) if denominator else None,
        "skipped_incomplete_pairs": skipped,
        "cases": cases,
    }


def summarize_plan(observations: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(observations)
    by_lane: Dict[str, int] = defaultdict(int)
    by_provider: Dict[str, int] = defaultdict(int)
    by_family: Dict[str, int] = defaultdict(int)
    for row in rows:
        by_lane[str(row.get("lane") or "unknown")] += 1
        by_provider[str(row.get("provider") or "unknown")] += 1
        by_family[str(row.get("family") or "unknown")] += 1
    return {
        "observations": len(rows),
        "by_lane": dict(sorted(by_lane.items())),
        "by_provider": dict(sorted(by_provider.items())),
        "by_family": dict(sorted(by_family.items())),
    }
