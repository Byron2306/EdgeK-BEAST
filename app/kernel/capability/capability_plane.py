"""Unified read facade for BEAST capability surfaces.

CapabilityPlane is intentionally advisory. It normalizes the local capability
registry, skill tree, plugin marketplace, capability exchange, and meta-tool
commons into one queryable inventory without installing, executing, or
promoting anything.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.capability.capability_registry import CapabilityRegistry
from app.kernel.capability.capability_exchange import CapabilityExchange
from app.kernel.capability.skill_tree import SkillTree
from app.kernel.deployment.plugin_marketplace import PluginMarketplace
from app.kernel.networking.meta_tool_commons import MetaToolCommons
from app.kernel.capability.tool_buckets import bucket_tools, exposure_receipt


class CapabilityPlane:
    """Read-only view across BEAST capability, skill, plugin, and commons layers."""

    def __init__(
        self,
        *,
        workspace_root: Optional[str] = None,
        registry: Optional[CapabilityRegistry] = None,
        skill_tree: Optional[SkillTree] = None,
        plugin_marketplace: Optional[PluginMarketplace] = None,
        exchange: Optional[CapabilityExchange] = None,
        commons: Optional[MetaToolCommons] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root or ".").resolve()
        state_root = self.workspace_root / ".beast"
        self.registry = registry or CapabilityRegistry()
        self.skill_tree = skill_tree or SkillTree(data_dir=str(state_root / "capability_plane_skills"))
        self.plugin_marketplace = plugin_marketplace or PluginMarketplace(str(state_root / "plugins"))
        self.exchange = exchange or CapabilityExchange(data_dir=str(state_root / "capability_exchange"))
        self.commons = commons or MetaToolCommons(
            db_path=str(state_root / "meta_tool_commons.db"),
            exchange=self.exchange,
            skill_registry=self.skill_tree.skill_registry,
        )

    def summary(self, *, limit: int = 100) -> Dict[str, Any]:
        records, sources = self._collect(limit=max(1, min(int(limit or 100), 500)))
        return {
            "beast_object_type": "capability_plane",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "capability_count": len(records),
            "local_count": sum(1 for item in records if item.get("local")),
            "verified_count": sum(1 for item in records if item.get("verified")),
            "reusable_count": sum(1 for item in records if item.get("reusable")),
            "risky_count": sum(1 for item in records if item.get("risky")),
            "sources": sources,
            "capabilities": records[: max(1, min(int(limit or 100), 500))],
            "authority": "read_only_facade_no_execution_no_install",
        }

    def query(
        self,
        *,
        text: str = "",
        kind: str = "",
        family: str = "",
        source: str = "",
        risk: str = "",
        local: Optional[bool] = None,
        reusable: Optional[bool] = None,
        verified: Optional[bool] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        records, sources = self._collect(limit=500)
        needle = str(text or "").strip().lower()
        filtered = []
        for item in records:
            if kind and item.get("kind") != kind:
                continue
            if family and item.get("family") != family:
                continue
            if source and item.get("source") != source:
                continue
            if risk and item.get("risk_level") != risk:
                continue
            if local is not None and bool(item.get("local")) != bool(local):
                continue
            if reusable is not None and bool(item.get("reusable")) != bool(reusable):
                continue
            if verified is not None and bool(item.get("verified")) != bool(verified):
                continue
            haystack = " ".join(str(item.get(key) or "") for key in ("capability_id", "name", "kind", "family", "source")).lower()
            if needle and needle not in haystack:
                continue
            filtered.append(item)
        capped = max(1, min(int(limit or 50), 500))
        return {
            "beast_object_type": "capability_plane_query",
            "version": "1.0",
            "query": {
                "text": text,
                "kind": kind,
                "family": family,
                "source": source,
                "risk": risk,
                "local": local,
                "reusable": reusable,
                "verified": verified,
                "limit": capped,
            },
            "count": len(filtered),
            "sources": sources,
            "capabilities": filtered[:capped],
            "authority": "read_only_facade_no_execution_no_install",
        }

    def expose(self, *, phase: str = "Observe", risk: str = "low", network: bool = False, mutating: bool = False, approved: bool = False, failed_tools=(), include_schemas: bool = False, limit: int = 100) -> Dict[str, Any]:
        """Return only the capability schemas justified by the active phase."""
        records,_ = self._collect(limit=max(1,min(limit,500)))
        tools=[{**item,"bucket":item.get("bucket") or "Observe"} for item in records]
        visible=bucket_tools(tools,phase=phase,risk=risk,network=network,mutating=mutating,approved=approved,failed_tools=failed_tools)
        if not include_schemas:
            visible=[{key:item.get(key) for key in ("capability_id","name","kind","family","source","risk_level","bucket","requires_approval")} for item in visible]
        return {"beast_object_type":"capability_plane_exposure","version":"1.0","workspace_root":str(self.workspace_root),"receipt":exposure_receipt(tools,phase=phase,risk=risk,network=network,mutating=mutating,approved=approved,failed_tools=tuple(failed_tools)),"capabilities":visible[:limit],"schema_mode":"full" if include_schemas else "lazy"}

    def _collect(self, *, limit: int) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        sources: Dict[str, Any] = {}
        self._add_registry(records, sources)
        self._add_skill_tree(records, sources, limit=limit)
        self._add_plugin_marketplace(records, sources)
        self._add_exchange(records, sources)
        self._add_commons(records, sources, limit=limit)
        return records, sources

    def _add_registry(self, records: List[Dict[str, Any]], sources: Dict[str, Any]) -> None:
        try:
            inventory = self.registry.list_capabilities()
            items = inventory.get("capabilities") or []
            sources["capability_registry"] = {"count": len(items), "kinds": inventory.get("kinds") or {}}
            for item in items:
                records.append(self._normalize(
                    capability_id=item.get("capability_id"),
                    name=item.get("name"),
                    kind=item.get("kind"),
                    family=item.get("family"),
                    source="capability_registry",
                    risk_level=item.get("risk_level"),
                    local=not bool(item.get("network_access")),
                    verified=str(item.get("promotion_status") or "") in {"adopted", "verified", "promoted"},
                    reusable=str(item.get("promotion_status") or "") in {"observed", "candidate", "adopted", "verified", "promoted"},
                    requires_approval=item.get("requires_approval"),
                    metadata={
                        "read_only": item.get("read_only"),
                        "writes_files": item.get("writes_files"),
                        "network_access": item.get("network_access"),
                        "promotion_status": item.get("promotion_status"),
                        "status": item.get("status"),
                    },
                ))
        except Exception as exc:
            sources["capability_registry"] = {"error": str(exc)}

    def _add_skill_tree(self, records: List[Dict[str, Any]], sources: Dict[str, Any], *, limit: int) -> None:
        try:
            state = self.skill_tree.state()
            skills = self.skill_tree.list_skills(limit=limit)
            candidates = self.skill_tree.list_candidates(limit=limit)
            sources["skill_tree"] = {
                "skills": state.get("skills") or {},
                "pattern_count": (state.get("patterns") or {}).get("detected", 0),
                "candidate_count": len(candidates),
            }
            for item in skills:
                records.append(self._normalize(
                    capability_id=item.get("skill_id") or item.get("id") or item.get("name"),
                    name=item.get("name"),
                    kind="skill",
                    family=item.get("category") or "skill_tree",
                    source="skill_tree",
                    risk_level="low",
                    local=True,
                    verified=True,
                    reusable=True,
                    metadata=item,
                ))
            for item in candidates:
                records.append(self._normalize(
                    capability_id=item.get("candidate_id") or item.get("name"),
                    name=item.get("name"),
                    kind="meta_tool_candidate",
                    family="skill_tree",
                    source="skill_tree",
                    risk_level="medium",
                    local=True,
                    verified=False,
                    reusable=True,
                    requires_approval=True,
                    metadata=item,
                ))
        except Exception as exc:
            sources["skill_tree"] = {"error": str(exc)}

    def _add_plugin_marketplace(self, records: List[Dict[str, Any]], sources: Dict[str, Any]) -> None:
        try:
            inventory = self.plugin_marketplace.list_installed()
            plugins = inventory.get("plugins") or []
            sources["plugin_marketplace"] = {"count": len(plugins)}
            for item in plugins:
                records.append(self._normalize(
                    capability_id=f"plugin:{item.get('id')}",
                    name=item.get("name") or item.get("id"),
                    kind="plugin",
                    family="plugin_marketplace",
                    source="plugin_marketplace",
                    risk_level=item.get("risk_class") or "medium",
                    local=True,
                    verified=bool(item.get("operational")),
                    reusable=True,
                    requires_approval=True,
                    metadata=item,
                ))
        except Exception as exc:
            sources["plugin_marketplace"] = {"error": str(exc)}

    def _add_exchange(self, records: List[Dict[str, Any]], sources: Dict[str, Any]) -> None:
        try:
            state = self.exchange.state()
            sources["capability_exchange"] = state
            records.append(self._normalize(
                capability_id="capability_exchange",
                name="Capability Exchange",
                kind="capability_exchange",
                family="capability_plane",
                source="capability_exchange",
                risk_level="medium" if state.get("endpoint_configured") else "low",
                local=not bool(state.get("enabled")),
                verified=bool(state.get("signed")),
                reusable=True,
                requires_approval=bool(state.get("enabled")),
                metadata=state,
            ))
        except Exception as exc:
            sources["capability_exchange"] = {"error": str(exc)}

    def _add_commons(self, records: List[Dict[str, Any]], sources: Dict[str, Any], *, limit: int) -> None:
        try:
            state = self.commons.state()
            sources["meta_tool_commons"] = state
            candidates = self.commons.candidates(limit=limit)
            for item in candidates.get("candidates") or []:
                records.append(self._normalize(
                    capability_id=item.get("candidate_id") or item.get("name"),
                    name=item.get("name"),
                    kind=item.get("kind") or "commons_candidate",
                    family=item.get("task_class") or "meta_tool_commons",
                    source="meta_tool_commons",
                    risk_level=item.get("risk_class") or "medium",
                    local=True,
                    verified=item.get("status") == "adopted",
                    reusable=True,
                    requires_approval=True,
                    metadata=item,
                ))
        except Exception as exc:
            sources["meta_tool_commons"] = {"error": str(exc)}

    def _normalize(
        self,
        *,
        capability_id: Any,
        name: Any,
        kind: Any,
        family: Any,
        source: str,
        risk_level: Any,
        local: bool,
        verified: bool,
        reusable: bool,
        requires_approval: Any = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        risk = str(risk_level or "unknown")
        return {
            "capability_id": str(capability_id or name or source),
            "name": str(name or capability_id or source),
            "kind": str(kind or "capability"),
            "family": str(family or "general"),
            "source": source,
            "risk_level": risk,
            "risky": risk in {"high", "critical"},
            "local": bool(local),
            "verified": bool(verified),
            "reusable": bool(reusable),
            "requires_approval": bool(requires_approval),
            "bucket": self._bucket_for(local=local,risk=risk,requires_approval=bool(requires_approval),metadata=metadata or {}),
            "metadata": metadata or {},
        }

    @staticmethod
    def _bucket_for(*, local: bool, risk: str, requires_approval: bool, metadata: Dict[str, Any]) -> str:
        if risk == "critical": return "Administer"
        if metadata.get("writes_files"): return "Modify"
        if metadata.get("network_access") or not local: return "Connect"
        if requires_approval or risk == "high": return "Execute"
        if metadata.get("read_only"): return "Observe"
        return "Reason"
