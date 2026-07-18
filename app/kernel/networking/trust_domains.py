"""Compile narrow Linux namespace/VRF/nftables trust domains.

Planning is pure and suitable for review. Applying a plan needs an explicit
operator approval and is intentionally unavailable to ordinary API reads.
"""
from __future__ import annotations

import ipaddress
import subprocess
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable


@dataclass(frozen=True)
class TrustDomain:
    name: str
    namespace: str
    vrf: str
    table: int
    cidr: str
    allowed_tcp_ports: tuple[int, ...] = ()

    def validate(self) -> None:
        if not self.name.replace("-", "").isalnum() or not self.namespace or not self.vrf:
            raise ValueError("trust-domain name, namespace, and VRF are required")
        if not 1 <= self.table <= 2**31 - 1:
            raise ValueError("routing table is out of range")
        ipaddress.ip_network(self.cidr, strict=True)
        if any(port < 1 or port > 65535 for port in self.allowed_tcp_ports):
            raise ValueError("allowed TCP port is out of range")


class TrustDomainController:
    def plan(self, domain: TrustDomain) -> dict[str, Any]:
        domain.validate()
        ports = ", ".join(str(port) for port in sorted(set(domain.allowed_tcp_ports))) or ""
        nft = (
            f"table inet beast_{domain.name} {{\n"
            f" chain input {{ type filter hook input priority 0; policy drop; iifname \"lo\" accept; ct state established,related accept;"
            + (f" tcp dport {{ {ports} }} accept;" if ports else "")
            + " }\n}\n"
        )
        commands = [
            ["ip", "netns", "add", domain.namespace],
            ["ip", "-n", domain.namespace, "link", "add", domain.vrf, "type", "vrf", "table", str(domain.table)],
            ["ip", "-n", domain.namespace, "link", "set", domain.vrf, "up"],
            ["nft", "-f", "<reviewed-rule-file>"],
        ]
        return {"beast_object_type": "network_trust_domain_plan", "domain": asdict(domain), "commands": commands,
                "nftables": nft, "requires": ["approved=true", "CAP_NET_ADMIN", "nftables", "iproute2"], "dry_run": True}

    def apply(self, domain: TrustDomain, *, approved: bool, runner: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
        plan = self.plan(domain)
        if not approved:
            return {**plan, "status": "approval_required", "executed": False}
        results = []
        for command in plan["commands"][:-1]:
            completed = runner(command, capture_output=True, text=True, timeout=15, check=False)
            results.append({"command": " ".join(command), "returncode": completed.returncode, "stderr": completed.stderr[-500:]})
            if completed.returncode:
                return {**plan, "status": "failed", "executed": True, "results": results}
        # nft receives the exact reviewed text through stdin, never a shell.
        completed = runner(["nft", "-f", "-"], input=plan["nftables"], capture_output=True, text=True, timeout=15, check=False)
        results.append({"command": "nft -f -", "returncode": completed.returncode, "stderr": completed.stderr[-500:]})
        return {**plan, "status": "applied" if completed.returncode == 0 else "failed", "executed": True, "results": results}

    def reconcile(self, domains: Iterable[TrustDomain]) -> dict[str, Any]:
        """Compile the complete desired network state for a controller loop."""
        plans = [self.plan(domain) for domain in domains]
        return {
            "beast_object_type": "network_trust_domain_reconciliation",
            "version": "1.0", "plans": plans, "domain_count": len(plans),
            "apply_boundary": "plans require individual explicit operator approval before host mutation",
        }
