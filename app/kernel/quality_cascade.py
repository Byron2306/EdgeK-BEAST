"""
EdgeK BEAST Quality Cascade.

Reusable local checks that route cards can orchestrate before model escalation.
"""

import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.evidence_envelope import EvidenceEnvelopeFactory


PROVIDER_ENV_VARS = {
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "google": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "huggingface": ["HF_TOKEN", "HUGGINGFACE_API_KEY"],
    "tgi": ["TGI_BASE_URL"],
    "litellm": ["LITELLM_API_KEY", "LITELLM_BASE_URL"],
    "nvidia_nim": ["NVIDIA_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "cerebras": ["CEREBRAS_API_KEY"],
    "cohere": ["COHERE_API_KEY"],
    "groq": ["GROQ_API_KEY"],
    "mistral": ["MISTRAL_API_KEY"],
    "together": ["TOGETHER_API_KEY"],
    "perplexity": ["PERPLEXITY_API_KEY"],
    "fireworks": ["FIREWORKS_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "xai": ["XAI_API_KEY"],
    "replicate": ["REPLICATE_API_TOKEN"],
    "fal": ["FAL_KEY"],
    "hyperbolic": ["HYPERBOLIC_API_KEY"],
    "novita": ["NOVITA_API_KEY"],
    "nscale": ["NSCALE_API_KEY"],
    "ovhcloud": ["OVHCLOUD_APP_KEY", "OVHCLOUD_APP_SECRET", "OVHCLOUD_CONSUMER_KEY"],
    "deepinfra": ["DEEPINFRA_API_KEY"],
    "featherless": ["FEATHERLESS_API_KEY"],
}


@dataclass
class CascadeCheck:
    name: str
    status: str
    summary: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class QualityCascade:
    """Run deterministic local checks for a task route."""

    def __init__(
        self,
        policies: Optional[Dict[str, Any]] = None,
        runtime_governor: Any = None,
    ):
        self.policies = policies or {}
        self.runtime_governor = runtime_governor
        self.evidence_factory = EvidenceEnvelopeFactory(self.policies)

    def run(
        self,
        envelope: Dict[str, Any],
        route_card: Dict[str, Any],
        workspace_root: str,
    ) -> Dict[str, Any]:
        provider = route_card.get("provider") or envelope.get("inputs", {}).get("provider") or "unknown"
        workspace = Path(workspace_root)
        checks = self.run_steps(
            steps=route_card.get("preferred_order", []),
            provider=provider,
            workspace=workspace,
        )
        executed = [check.name for check in checks]
        failed = [check for check in checks if check.status == "failed"]
        warnings = [check for check in checks if check.status == "warning"]
        evidence_records = [
            self._check_evidence(check, provider, envelope, route_card)
            for check in checks
        ]
        return {
            "beast_object_type": "quality_cascade_report",
            "version": "1.0",
            "task_id": envelope.get("task_id"),
            "task_class": envelope.get("task_class"),
            "route_id": route_card.get("route_id"),
            "provider": provider,
            "local_only": True,
            "status": "failed" if failed else "warning" if warnings else "passed",
            "checks": [check.to_dict() for check in checks],
            "route_execution": {
                "source": "route_card.preferred_order",
                "preferred_order": route_card.get("preferred_order", []),
                "executed_order": executed,
                "unsupported_steps": [
                    step for step in route_card.get("preferred_order", [])
                    if step not in set(executed) and step not in {"failure_category", "recommendations", "chronicle"}
                ],
                "post_check_steps": [
                    step for step in route_card.get("preferred_order", [])
                    if step in {"failure_category", "recommendations", "chronicle"}
                ],
            },
            "evidence_records": evidence_records,
            "summary": {
                "check_count": len(checks),
                "failed": len(failed),
                "warnings": len(warnings),
                "passed": len([check for check in checks if check.status == "passed"]),
                "skipped": len([check for check in checks if check.status == "skipped"]),
            },
        }

    def run_steps(self, steps: List[str], provider: str, workspace: Path) -> List[CascadeCheck]:
        check_map = {
            "provider_policy": lambda: self.check_provider_policy(provider),
            "credentials": lambda: self.check_credentials(provider),
            "runtime_circuit": lambda: self.check_runtime_circuit(provider),
            "recent_attempts": lambda: self.check_recent_attempts(provider),
            "log_scan": lambda: self.check_logs(provider, workspace),
        }
        checks = []
        for step in steps:
            if step in check_map:
                checks.append(check_map[step]())
        return checks

    def check_provider_policy(self, provider: str) -> CascadeCheck:
        providers = self.policies.get("providers", {})
        config = providers.get(provider) or providers.get(self.provider_alias(provider), {})
        if not config:
            return CascadeCheck(
                "provider_policy",
                "warning",
                f"No provider policy found for {provider}",
                {"known_providers": sorted(providers.keys())},
            )
        enabled = bool(config.get("enabled", False))
        return CascadeCheck(
            "provider_policy",
            "passed" if enabled else "failed",
            f"Provider policy is {'enabled' if enabled else 'disabled'}",
            {
                "base_url": config.get("base_url"),
                "default_model": config.get("default_model"),
                "backend": config.get("backend"),
            },
        )

    def check_credentials(self, provider: str) -> CascadeCheck:
        env_vars = PROVIDER_ENV_VARS.get(provider) or PROVIDER_ENV_VARS.get(self.provider_alias(provider), [])
        if not env_vars:
            return CascadeCheck("credentials", "warning", "No credential rule is registered", {})
        present = [name for name in env_vars if bool(os.environ.get(name))]
        return CascadeCheck(
            "credentials",
            "passed" if present else "failed",
            "Required environment credential is present" if present else "No expected credential environment variable is set",
            {"expected_env": env_vars, "present_env": present},
        )

    def check_runtime_circuit(self, provider: str) -> CascadeCheck:
        if not self.runtime_governor:
            return CascadeCheck("runtime_circuit", "skipped", "Runtime governor unavailable", {})
        state = self.runtime_governor.circuit_state(provider)
        status = "passed" if state.get("state") in ("closed", "half_open") else "failed"
        return CascadeCheck(
            "runtime_circuit",
            status,
            f"Runtime circuit is {state.get('state')}",
            state,
        )

    def check_recent_attempts(self, provider: str) -> CascadeCheck:
        if not self.runtime_governor:
            return CascadeCheck("recent_attempts", "skipped", "Runtime governor unavailable", {})
        attempts = self.runtime_governor.recent_attempts(provider=provider, limit=8)
        failures = [item for item in attempts if item.get("status") in ("failed", "rejected", "abandoned")]
        summary = "No recent attempts found"
        status = "warning"
        if attempts:
            status = "passed" if not failures else "warning"
            summary = f"{len(attempts)} recent attempts, {len(failures)} non-successful"
        return CascadeCheck(
            "recent_attempts",
            status,
            summary,
            {"attempts": attempts, "failure_count": len(failures)},
        )

    def check_logs(self, provider: str, workspace: Path) -> CascadeCheck:
        snippets = []
        for log_name in ("gateway.log", "server.log", "ollama.log"):
            path = workspace / log_name
            if not path.exists():
                continue
            text = self.tail_text(path)
            hits = self.log_hits(text, provider)
            if hits:
                snippets.append({"file": log_name, "hits": hits[:5]})

        if not snippets:
            return CascadeCheck(
                "log_scan",
                "warning",
                "No provider-specific failures found in local log tails",
                {"searched_logs": ["gateway.log", "server.log", "ollama.log"]},
            )
        return CascadeCheck(
            "log_scan",
            "warning",
            "Provider-related log evidence found",
            {"snippets": snippets},
        )

    def provider_alias(self, provider: str) -> str:
        aliases = {"hf": "huggingface", "gemini": "google", "google_ai_studio": "google"}
        return aliases.get(provider, provider)

    def tail_text(self, path: Path, max_bytes: int = 12000) -> str:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell()
            bytes_to_read = min(pos, max_bytes)
            f.seek(pos - bytes_to_read)
            data = f.read(bytes_to_read)
        return data.decode("utf-8", errors="replace")

    def log_hits(self, text: str, provider: str) -> List[str]:
        terms = [provider, self.provider_alias(provider), "429", "quota", "rate limit", "unauthorized", "timeout", "error"]
        hits = []
        for line in text.splitlines():
            lower = line.lower()
            if any(term and term.lower() in lower for term in terms):
                hits.append(re.sub(r"\s+", " ", line).strip()[:260])
        return hits

    def _check_evidence(
        self,
        check: CascadeCheck,
        provider: str,
        envelope: Dict[str, Any],
        route_card: Dict[str, Any],
    ) -> Dict[str, Any]:
        severity = {
            "failed": "high",
            "warning": "medium",
            "skipped": "low",
            "passed": "info",
        }.get(check.status, "info")
        confidence = {
            "failed": 0.85,
            "warning": 0.65,
            "skipped": 0.35,
            "passed": 0.6,
        }.get(check.status, 0.5)
        relevance = 0.85 if check.status in ("failed", "warning") else 0.45
        verification_strength = 0.75 if check.status == "failed" else 0.55 if check.status == "warning" else 0.35
        capability_id = self._check_capability_id(check.name)
        family = "diagnostics" if check.name in {"provider_policy", "credentials", "runtime_circuit", "recent_attempts", "log_scan"} else "quality"
        return self.evidence_factory.build(
            source_type="quality_verifier",
            source_uri=f"quality://{route_card.get('route_id') or provider}/{check.name}",
            scope="provider",
            artifact_type=f"quality_check:{check.name}",
            task_id=envelope.get("task_id"),
            provider=provider,
            severity=severity,
            confidence=confidence,
            relevance=relevance,
            risk=0.55 if check.status == "failed" else 0.35,
            blast_radius=0.35,
            repeat_count=1,
            verification_strength=verification_strength,
            signals=[f"quality_{check.status}", check.name],
            relationships=[
                {"type": "provider", "id": provider},
                {"type": "route", "id": route_card.get("route_id")},
                {"type": "quality_check", "id": check.name},
            ],
            recommended_actions=self._check_recommendations(check),
            recommended_capability_id=capability_id,
            capability_family=family,
            summary=check.summary,
        )

    def _check_capability_id(self, check_name: str) -> str:
        if check_name in {"provider_policy", "credentials", "runtime_circuit", "recent_attempts", "log_scan"}:
            return "workflow:provider_diagnostic"
        return "workflow:quality_cascade"

    def _check_recommendations(self, check: CascadeCheck) -> List[str]:
        if check.status == "passed":
            return ["Keep this local check as supporting evidence."]
        if check.name == "credentials":
            return ["Fix credential mapping before retrying provider calls."]
        if check.name == "runtime_circuit":
            return ["Check provider circuit before cloud handoff or retry."]
        if check.name == "log_scan":
            return ["Use local log evidence to categorize the failure before escalation."]
        return ["Resolve or explain this local quality check before cloud handoff."]
