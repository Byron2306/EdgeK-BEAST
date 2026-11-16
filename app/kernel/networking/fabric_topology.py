"""One fail-closed topology contract for Guardian bindings and the Commons lab.

The contract is read-only. It reconciles the Guardian service registry, the
Commons lab provisioning manifest, the Compose publication (base plus optional
override) and, optionally, live registry endpoints. Drift is reported and
blocks Guardian binding; it is never resolved silently.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from app.kernel.networking.service_registry import ServiceRegistry


class TopologyDriftError(RuntimeError):
    def __init__(self, findings: list[dict[str, Any]]):
        self.findings = findings
        super().__init__(
            "fabric topology drift: "
            + "; ".join(f"{item['kind']}:{item['subject']}" for item in findings)
        )


class _ComposeLoader(yaml.SafeLoader):
    pass


def _override_sequence(loader: yaml.SafeLoader, node: yaml.Node) -> Any:
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    return loader.construct_scalar(node)


_ComposeLoader.add_constructor("!override", _override_sequence)
_ComposeLoader.add_constructor("!reset", _override_sequence)


def _published_port(entry: Any) -> int | None:
    if isinstance(entry, Mapping):
        value = entry.get("published")
        return int(value) if value not in (None, "") else None
    parts = str(entry).split("/", 1)[0].split(":")
    if len(parts) == 3:
        return int(parts[1])
    if len(parts) == 2:
        return int(parts[0])
    return None


def _compose_ports(path: Path | None) -> dict[str, list[int]]:
    if path is None:
        return {}
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader) or {}
    services = payload.get("services") or {}
    ports: dict[str, list[int]] = {}
    for name, item in services.items():
        if isinstance(item, Mapping) and "ports" in item:
            ports[str(name)] = sorted(
                port for port in (_published_port(entry) for entry in item.get("ports") or []) if port
            )
    return ports


def _endpoint_port(endpoint: str) -> int | None:
    try:
        return urlsplit(str(endpoint)).port
    except ValueError:
        return None


@dataclass(frozen=True)
class FabricTopology:
    guardian_services: Mapping[str, Mapping[str, Any]]
    registry_digest: str
    commons_nodes: Mapping[str, int]
    compose_ports: Mapping[str, list[int]]
    sources: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def load(
        cls, *, services_path: str | Path, lab_manifest_path: str | Path,
        compose_base_path: str | Path, compose_override_path: str | Path | None = None,
    ) -> FabricTopology:
        services_file = Path(services_path)
        registry = ServiceRegistry.from_file(services_file)
        raw = (yaml.safe_load(services_file.read_text(encoding="utf-8")) or {}).get("services") or {}
        guardian = {
            name: {
                "upstream": service.upstream,
                "port": int(service.port),
                "trust_domain": service.trust_domain,
                "protocol": "TCP",
            }
            for name, service in registry.services.items()
            if service.enabled and isinstance(raw.get(name), Mapping) and raw[name].get("socket_guardian") is True
        }
        manifest = json.loads(Path(lab_manifest_path).read_text(encoding="utf-8"))
        nodes = {str(item["node_id"]): int(item["port"]) for item in manifest.get("nodes") or []}
        ports = _compose_ports(Path(compose_base_path))
        override = Path(compose_override_path) if compose_override_path else None
        ports.update(_compose_ports(override))
        return cls(
            guardian_services=guardian,
            registry_digest=registry.digest(),
            commons_nodes=nodes,
            compose_ports=ports,
            sources={
                "services": str(services_file),
                "lab_manifest": str(lab_manifest_path),
                "compose_base": str(compose_base_path),
                "compose_override": str(override or ""),
            },
        )

    @property
    def topology_digest(self) -> str:
        body = {
            "guardian_services": {k: dict(v) for k, v in sorted(self.guardian_services.items())},
            "commons_nodes": dict(sorted(self.commons_nodes.items())),
            "compose_ports": {k: list(v) for k, v in sorted(self.compose_ports.items())},
        }
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def drift(self, registry_endpoints: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for node_id, port in sorted(self.commons_nodes.items()):
            published = list(self.compose_ports.get(node_id) or [])
            if published != [port]:
                findings.append({"kind": "compose_port_mismatch", "subject": node_id,
                                 "expected": port, "observed": published})
        for name in sorted(set(self.compose_ports) - set(self.commons_nodes)):
            findings.append({"kind": "compose_unknown_service", "subject": name,
                             "expected": None, "observed": list(self.compose_ports[name])})
        owners: dict[int, list[str]] = {}
        for name, item in self.guardian_services.items():
            owners.setdefault(int(item["port"]), []).append(f"guardian:{name}")
        for node_id, port in self.commons_nodes.items():
            owners.setdefault(int(port), []).append(f"commons:{node_id}")
        for port, names in sorted(owners.items()):
            if len(names) > 1:
                findings.append({"kind": "port_collision", "subject": ",".join(sorted(names)),
                                 "expected": "unique", "observed": port})
        for node_id, endpoint in sorted((registry_endpoints or {}).items()):
            if node_id not in self.commons_nodes:
                findings.append({"kind": "registry_unknown_node", "subject": node_id,
                                 "expected": None, "observed": _endpoint_port(endpoint)})
            elif _endpoint_port(endpoint) != self.commons_nodes[node_id]:
                findings.append({"kind": "registry_endpoint_mismatch", "subject": node_id,
                                 "expected": self.commons_nodes[node_id], "observed": _endpoint_port(endpoint)})
        return findings

    def require_consistent(self, registry_endpoints: Mapping[str, str] | None = None) -> None:
        findings = self.drift(registry_endpoints)
        if findings:
            raise TopologyDriftError(findings)

    def guardian_bindings(self) -> dict[str, Any]:
        self.require_consistent()
        return {
            "beast_object_type": "fabric_guardian_bindings",
            "version": "1.0",
            "topology_digest": self.topology_digest,
            "registry_digest": self.registry_digest,
            "services": {name: dict(item) for name, item in sorted(self.guardian_services.items())},
        }

    def report(self, registry_endpoints: Mapping[str, str] | None = None) -> dict[str, Any]:
        findings = self.drift(registry_endpoints)
        return {
            "beast_object_type": "fabric_topology_report",
            "version": "1.0",
            "consistent": not findings,
            "topology_digest": self.topology_digest,
            "registry_digest": self.registry_digest,
            "guardian_services": sorted(self.guardian_services),
            "commons_nodes": dict(sorted(self.commons_nodes.items())),
            "compose_ports": {k: list(v) for k, v in sorted(self.compose_ports.items())},
            "registry_checked": registry_endpoints is not None,
            "findings": findings,
            "sources": dict(self.sources),
        }
