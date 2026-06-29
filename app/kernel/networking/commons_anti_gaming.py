"""Deterministic large-scale anti-gaming analysis for Commons testnet events."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, Iterable


class CommonsAntiGaming:
    def analyze(
        self,
        *,
        signup_events: Iterable[Dict[str, Any]],
        swaps: Iterable[Dict[str, Any]],
        claims: Iterable[Dict[str, Any]],
        ledger_balanced: bool = True,
    ) -> Dict[str, Any]:
        sources: Dict[str, set[str]] = defaultdict(set)
        for event in signup_events:
            sources[str(event.get("source_hash") or "")].add(str(event.get("user_id") or ""))
        shared = {source: users for source, users in sources.items() if source and len(users) >= 3}
        user_sources = {user: source for source, users in sources.items() for user in users}
        swap_count = Counter(); volume = Counter(); directions: Dict[str, set[str]] = defaultdict(set)
        for event in swaps:
            user = str(event.get("user_id") or "")
            swap_count[user] += 1; volume[user] += int(event.get("amount_in") or 0)
            directions[user].add(str(event.get("from_asset") or ""))
        claim_count = Counter(str(event.get("user_id") or "") for event in claims)
        users = set(user_sources) | set(swap_count) | set(claim_count)
        rows = []
        for user in users:
            signals = []; score = 0
            cluster_size = len(shared.get(user_sources.get(user, ""), set()))
            if cluster_size >= 3: score += min(50, 20 + cluster_size * 5); signals.append("shared_source_sybil_cluster")
            if swap_count[user] >= 20: score += 20; signals.append("swap_velocity")
            if volume[user] >= 10_000: score += 20; signals.append("swap_volume")
            if len(directions[user]) > 1 and swap_count[user] >= 6: score += 35; signals.append("wash_swap_cycle")
            if claim_count[user] >= 10: score += 25; signals.append("credit_claim_concentration")
            score = min(100, score)
            action = "freeze" if score >= 80 else "quarantine" if score >= 60 else "throttle" if score >= 40 else "monitor" if score >= 20 else "allow"
            rows.append({"user_id":user,"risk_score":score,"action":action,"signals":signals,"source_cluster_size":cluster_size,"swaps":swap_count[user],"swap_volume":volume[user],"claims":claim_count[user]})
        rows.sort(key=lambda x:(-x["risk_score"],x["user_id"]))
        return {
            "beast_object_type":"commons_large_scale_anti_gaming_report",
            "version":"1.0",
            "identities_analyzed":len(users),
            "shared_source_clusters":len(shared),
            "risk_counts":dict(Counter(row["action"] for row in rows)),
            "flagged_accounts":[row for row in rows if row["risk_score"] >= 40],
            "ledger_balanced":ledger_balanced,
            "global_action":"halt_ledger_and_investigate" if not ledger_balanced else "continue_with_account_controls",
            "rules":["shared-source Sybil clustering","swap velocity","swap volume","bidirectional wash cycles","credit concentration","double-entry invariant"],
        }
