"""
EdgeK BEAST Task Envelopes and local provider diagnostics.

This is the first concrete spine for the meta-optimization plane:
standardize a task, run cheap local checks, produce a verified summary,
and optionally write a durable Chronicle record.
"""

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .quality_cascade import PROVIDER_ENV_VARS, QualityCascade


@dataclass
class ContextBudget:
    max_tokens: int = 8000
    max_files: int = 8
    allow_full_files: bool = False


@dataclass
class TaskEnvelope:
    beast_object_type: str
    version: str
    task_id: str
    intent: str
    task_class: str
    project: str
    risk_level: str
    privacy_class: str
    inputs: Dict[str, Any]
    context_budget: ContextBudget
    allowed_actions: List[str]
    approval_required_for: List[str]
    success_criteria: List[str]
    dry_run: bool = True
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["context_budget"] = asdict(self.context_budget)
        return payload


@dataclass
class RouteCard:
    beast_object_type: str
    version: str
    route_id: str
    name: str
    task_class: str
    provider: str
    context: str
    preferred_order: List[str]
    avoid: List[str]
    cache_policy: Dict[str, str]
    safety: Dict[str, Any]
    promotion_status: str
    route_quality_score: float
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TaskEnvelopeBuilder:
    """Build canonical task envelopes and run narrow local diagnostics."""

    def __init__(
        self,
        policies: Optional[Dict[str, Any]] = None,
        runtime_governor: Any = None,
        data_dir: Optional[str] = None,
    ):
        self.policies = policies or {}
        self.runtime_governor = runtime_governor
        if data_dir is None:
            data_dir = Path(__file__).resolve().parents[2] / "data"
        self.data_dir = Path(data_dir)
        self.chronicle_dir = self.data_dir / "chronicles"
        self.route_card_dir = self.data_dir / "route_cards"
        self.quality_cascade = QualityCascade(self.policies, runtime_governor=runtime_governor)

    def build(self, payload: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
        user_request = self._request_text(payload)
        task_class = payload.get("task_class") or self._classify(user_request)
        provider = self._detect_provider(payload, user_request)
        risk_level = payload.get("risk_level") or self._risk_for(task_class)
        privacy_class = payload.get("privacy_class") or "internal"

        envelope = TaskEnvelope(
            beast_object_type="task_envelope",
            version="1.0",
            task_id=payload.get("task_id") or self._task_id(user_request, task_class),
            intent=self._intent(user_request, task_class),
            task_class=task_class,
            project=payload.get("project") or "edgek-beast",
            risk_level=risk_level,
            privacy_class=privacy_class,
            inputs={
                "user_request": user_request,
                "provider": provider,
                "active_service": payload.get("active_service", "edgek-beast-gateway"),
                "recent_logs": payload.get("recent_logs", "local_log_tail"),
            },
            context_budget=ContextBudget(
                max_tokens=int(payload.get("max_tokens", self._meta_rule("max_input_tokens_per_request", 8000))),
                max_files=int(payload.get("max_files", 8)),
                allow_full_files=bool(payload.get("allow_full_files", False)),
            ),
            allowed_actions=self._allowed_actions(task_class),
            approval_required_for=[
                "external_write",
                "database_write",
                "git_push",
                "production_config_change",
                "provider_account_change",
            ],
            success_criteria=self._success_criteria(task_class),
            dry_run=dry_run,
            created_at=self._utc_now(),
        )
        return envelope.to_dict()

    def diagnose_provider(
        self,
        payload: Dict[str, Any],
        workspace_root: str,
        write_chronicle: bool = True,
    ) -> Dict[str, Any]:
        envelope = self.build({**payload, "task_class": "provider_debugging"}, dry_run=False)
        provider = envelope["inputs"].get("provider") or "unknown"
        workspace = Path(workspace_root)
        route_card = self.provider_diagnostic_route_card(provider, envelope)

        quality_report = self.quality_cascade.run(envelope, route_card, str(workspace))
        checks = quality_report["checks"]
        category = self._failure_category(checks)
        recommendations = self._recommendations(provider, category, checks)
        confidence = self._confidence(checks, category)

        result = {
            "beast_object_type": "provider_diagnostic",
            "version": "1.0",
            "task_id": envelope["task_id"],
            "provider": provider,
            "failure_category": category,
            "confidence": confidence,
            "envelope": envelope,
            "route_card": route_card,
            "route_execution": quality_report.get("route_execution"),
            "quality_report": quality_report,
            "checks": checks,
            "recommendations": recommendations,
            "local_only": True,
            "cloud_escalation_needed": confidence < 0.72,
            "chronicle": None,
        }
        if write_chronicle:
            result["chronicle"] = self._write_chronicle(result)
        return result

    def run_quality_cascade(self, payload: Dict[str, Any], workspace_root: str) -> Dict[str, Any]:
        """Build an envelope, select a route card, and run local quality checks."""
        envelope = self.build(payload, dry_run=False)
        task_class = envelope.get("task_class")
        provider = envelope.get("inputs", {}).get("provider") or payload.get("provider") or "unknown"
        if task_class == "provider_debugging":
            route_card = self.provider_diagnostic_route_card(str(provider), envelope)
        else:
            route_card = self.generic_quality_route_card(task_class, envelope)
        return self.quality_cascade.run(envelope, route_card, workspace_root)

    def provider_diagnostic_route_card(
        self,
        provider: str,
        envelope: Optional[Dict[str, Any]] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        envelope = envelope or {}
        route = RouteCard(
            beast_object_type="route_card",
            version="1.0",
            route_id=f"route_provider_diagnostic_{provider}",
            name="Provider diagnostic route",
            task_class="provider_debugging",
            provider=provider,
            context=(
                "Diagnose provider call failures using local policy, credential, "
                "runtime, attempt, and log evidence before model escalation."
            ),
            preferred_order=[
                "provider_policy",
                "credentials",
                "runtime_circuit",
                "recent_attempts",
                "log_scan",
                "failure_category",
                "recommendations",
                "chronicle",
            ],
            avoid=[
                "full_repo_upload",
                "blind_provider_retries",
                "secret_value_capture",
                "cloud_reasoning_before_local_evidence",
                "production_provider_account_change",
            ],
            cache_policy={
                "provider_policy": "until policy file changes",
                "credentials": "do not cache secret values; cache presence only",
                "runtime_circuit": "live",
                "recent_attempts": "30 seconds",
                "log_scan": "per diagnostic run",
            },
            safety={
                "redact_secrets": True,
                "local_only": True,
                "external_write_requires_approval": True,
                "provider_account_change_requires_approval": True,
                "max_log_tail_bytes": 12000,
                "task_id": envelope.get("task_id"),
            },
            promotion_status="candidate",
            route_quality_score=0.78,
            created_at=self._utc_now(),
        ).to_dict()
        if persist:
            self._write_route_card(route)
        return route

    def generic_quality_route_card(
        self,
        task_class: str,
        envelope: Optional[Dict[str, Any]] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        envelope = envelope or {}
        route = RouteCard(
            beast_object_type="route_card",
            version="1.0",
            route_id=f"route_quality_{task_class}",
            name="Generic quality cascade route",
            task_class=task_class,
            provider=envelope.get("inputs", {}).get("provider", "unknown"),
            context="Run available local checks for a task before model escalation.",
            preferred_order=["log_scan"],
            avoid=[
                "cloud_reasoning_before_local_evidence",
                "full_repo_upload",
                "destructive_action_without_approval",
            ],
            cache_policy={"log_scan": "per cascade run"},
            safety={
                "redact_secrets": True,
                "local_only": True,
                "external_write_requires_approval": True,
                "task_id": envelope.get("task_id"),
            },
            promotion_status="draft",
            route_quality_score=0.5,
            created_at=self._utc_now(),
        ).to_dict()
        if persist:
            self._write_route_card(route)
        return route

    def list_route_cards(
        self,
        task_class: Optional[str] = None,
        provider: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        self.route_card_dir.mkdir(parents=True, exist_ok=True)
        cards = []
        for path in self.route_card_dir.glob("*.json"):
            try:
                card = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if task_class and card.get("task_class") != task_class:
                continue
            if provider and card.get("provider") != provider:
                continue
            cards.append(card)
        cards.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        bounded = cards[: max(1, min(int(limit), 100))]
        return {
            "route_cards": bounded,
            "count": len(bounded),
            "total_matches": len(cards),
            "route_card_dir": str(self.route_card_dir),
        }

    def get_route_card(self, route_id: str) -> Dict[str, Any]:
        self.route_card_dir.mkdir(parents=True, exist_ok=True)
        path = self.route_card_dir / f"{route_id}.json"
        if not path.exists():
            raise ValueError(f"Route card not found: {route_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_route_card(self, route_card: Dict[str, Any]) -> Dict[str, Any]:
        self.route_card_dir.mkdir(parents=True, exist_ok=True)
        path = self.route_card_dir / f"{route_card['route_id']}.json"
        path.write_text(json.dumps(route_card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"written": True, "path": str(path)}

    def _write_chronicle(self, result: Dict[str, Any]) -> Dict[str, Any]:
        self.chronicle_dir.mkdir(parents=True, exist_ok=True)
        task_id = result["task_id"]
        provider = result["provider"]
        stem = f"{task_id}_{provider}_diagnostic"
        path = self.chronicle_dir / f"{stem}.md"
        json_path = self.chronicle_dir / f"{stem}.json"
        record = self._chronicle_record(result)
        lines = [
            f"# Provider Diagnostic: {provider}",
            "",
            f"- Task: `{task_id}`",
            f"- Category: `{result['failure_category']}`",
            f"- Confidence: `{result['confidence']}`",
            f"- Cloud escalation needed: `{result['cloud_escalation_needed']}`",
            "",
            "## Checks",
            "",
        ]
        for check in result["checks"]:
            lines.append(f"- `{check['name']}`: **{check['status']}** - {check['summary']}")
        lines.extend(["", "## Recommendations", ""])
        for recommendation in result["recommendations"]:
            lines.append(f"- {recommendation}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        json_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {
            "written": True,
            "path": str(path),
            "json_path": str(json_path),
            "format": "markdown+json",
            "record": self._chronicle_summary(record),
        }

    def list_chronicles(
        self,
        task_class: Optional[str] = None,
        provider: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        self.chronicle_dir.mkdir(parents=True, exist_ok=True)
        records = []
        for path in self.chronicle_dir.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if task_class and record.get("task_class") != task_class:
                continue
            if provider and record.get("provider") != provider:
                continue
            if category and record.get("category") != category:
                continue
            records.append(record)
        records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        bounded = records[: max(1, min(int(limit), 100))]
        return {
            "chronicles": [self._chronicle_summary(record) for record in bounded],
            "count": len(bounded),
            "total_matches": len(records),
            "chronicle_dir": str(self.chronicle_dir),
        }

    def get_chronicle(self, task_id: str) -> Dict[str, Any]:
        self.chronicle_dir.mkdir(parents=True, exist_ok=True)
        matches = sorted(self.chronicle_dir.glob(f"{task_id}_*.json"))
        if not matches:
            raise ValueError(f"Chronicle not found for task_id: {task_id}")
        record = json.loads(matches[0].read_text(encoding="utf-8"))
        markdown_path = record.get("artifacts", {}).get("markdown_path")
        markdown = ""
        if markdown_path and Path(markdown_path).exists():
            markdown = Path(markdown_path).read_text(encoding="utf-8")
        return {
            "record": record,
            "markdown": markdown,
        }

    def _chronicle_record(self, result: Dict[str, Any]) -> Dict[str, Any]:
        envelope = result.get("envelope", {})
        checks = result.get("checks", [])
        failed_checks = [check["name"] for check in checks if check.get("status") == "failed"]
        category = result.get("failure_category", "unknown")
        provider = result.get("provider", "unknown")
        root_cause = self._root_cause_sentence(provider, category, failed_checks)
        return {
            "chronicle_type": "provider_diagnostic_summary",
            "version": "1.0",
            "task_id": result["task_id"],
            "task_class": envelope.get("task_class", "provider_debugging"),
            "provider": provider,
            "category": category,
            "summary": f"Provider diagnostic completed for {provider}: {category}.",
            "root_cause": root_cause,
            "confidence": result.get("confidence"),
            "cloud_escalation_needed": result.get("cloud_escalation_needed"),
            "local_only": result.get("local_only", True),
            "created_at": self._utc_now(),
            "actions_taken": [
                "built canonical task envelope",
                "checked provider policy",
                "checked credential environment presence",
                "checked runtime circuit state",
                "reviewed recent runtime attempts",
                "scanned local log tails",
            ],
            "verification": {
                "local_checks_completed": True,
                "failed_checks": failed_checks,
                "check_count": len(checks),
            },
            "recommendations": result.get("recommendations", []),
            "checks": [
                {
                    "name": check.get("name"),
                    "status": check.get("status"),
                    "summary": self._redact(str(check.get("summary", ""))),
                }
                for check in checks
            ],
            "route_card": result.get("route_card"),
            "envelope": envelope,
            "memory_candidate": category in ("quota_or_rate_limit", "auth_or_credentials", "runtime_circuit_open"),
            "artifacts": {
                "markdown_path": str(self.chronicle_dir / f"{result['task_id']}_{provider}_diagnostic.md"),
                "json_path": str(self.chronicle_dir / f"{result['task_id']}_{provider}_diagnostic.json"),
            },
        }

    def _chronicle_summary(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task_id": record.get("task_id"),
            "chronicle_type": record.get("chronicle_type"),
            "task_class": record.get("task_class"),
            "provider": record.get("provider"),
            "category": record.get("category"),
            "summary": record.get("summary"),
            "root_cause": record.get("root_cause"),
            "confidence": record.get("confidence"),
            "memory_candidate": record.get("memory_candidate"),
            "created_at": record.get("created_at"),
            "artifacts": record.get("artifacts", {}),
        }

    def _root_cause_sentence(self, provider: str, category: str, failed_checks: List[str]) -> str:
        if category == "auth_or_credentials":
            return f"{provider} diagnostic indicates missing or invalid credential readiness."
        if category == "quota_or_rate_limit":
            return f"{provider} diagnostic indicates upstream quota or rate-limit pressure."
        if category == "runtime_circuit_open":
            return f"{provider} runtime circuit is open and should block further retries."
        if category == "network_or_timeout":
            return f"{provider} diagnostic indicates network, timeout, or sidecar reachability risk."
        if category == "upstream_server_error":
            return f"{provider} diagnostic indicates upstream service instability."
        if failed_checks:
            return f"Local checks failed: {', '.join(failed_checks)}."
        return "Local evidence is insufficient for a confident root cause."

    def _redact(self, text: str) -> str:
        text = re.sub(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]+", r"\1=[REDACTED]", text)
        text = re.sub(r"sk-[A-Za-z0-9_-]{12,}", "sk-[REDACTED]", text)
        text = re.sub(r"hf_[A-Za-z0-9]{12,}", "hf_[REDACTED]", text)
        return text

    def _failure_category(self, checks: List[Dict[str, Any]]) -> str:
        evidence = " ".join(
            [
                str(check.get("summary", "")) + " " + str(check.get("evidence", {}))
                for check in checks
            ]
        ).lower()
        if "circuit is open" in evidence or "circuit breaker" in evidence:
            return "runtime_circuit_open"
        if "quota" in evidence or "429" in evidence or "rate limit" in evidence:
            return "quota_or_rate_limit"
        if "401" in evidence or "403" in evidence or "unauthorized" in evidence or "credential" in evidence:
            return "auth_or_credentials"
        if "timeout" in evidence or "connection" in evidence or "dns" in evidence:
            return "network_or_timeout"
        if "500" in evidence or "502" in evidence or "503" in evidence:
            return "upstream_server_error"
        return "insufficient_local_evidence"

    def _recommendations(self, provider: str, category: str, checks: List[Dict[str, Any]]) -> List[str]:
        if category == "auth_or_credentials":
            env_vars = PROVIDER_ENV_VARS.get(provider) or PROVIDER_ENV_VARS.get(self._provider_alias(provider), [])
            return [
                f"Set or verify one of: {', '.join(env_vars) or 'provider credential env vars'}.",
                "Avoid retrying provider calls until credential state changes.",
                "Run the diagnostic again after updating the environment.",
            ]
        if category == "quota_or_rate_limit":
            return [
                "Pause retries for this provider and use a configured fallback route.",
                "Surface quota/rate-limit guidance instead of repeating the failing call.",
                "Record this signature as a promotion candidate for provider quota diagnostics.",
            ]
        if category == "runtime_circuit_open":
            return [
                "Respect the open circuit and wait for the retry window or reset it intentionally.",
                "Inspect recent failed attempts before allowing more provider traffic.",
            ]
        if category == "network_or_timeout":
            return [
                "Check base URL, local sidecar process, port binding, and outbound network reachability.",
                "Use a short health probe before sending a full model request.",
            ]
        if category == "upstream_server_error":
            return [
                "Treat this as upstream instability first; prefer fallback routing over code changes.",
                "Add provider error normalization if the user-facing message is unclear.",
            ]
        failed = [check.get("name") for check in checks if check.get("status") == "failed"]
        if failed:
            return [f"Resolve failed local checks first: {', '.join(failed)}."]
        return [
            "Local evidence is inconclusive; collect a fresh runtime attempt or provider health response.",
            "Escalate to cloud reasoning only if a patch is needed after local evidence is captured.",
        ]

    def _confidence(self, checks: List[Dict[str, Any]], category: str) -> float:
        if category != "insufficient_local_evidence":
            return 0.82
        if any(check.get("status") == "failed" for check in checks):
            return 0.68
        return 0.55

    def _request_text(self, payload: Dict[str, Any]) -> str:
        return str(payload.get("user_request") or payload.get("task") or payload.get("goal") or "").strip()

    def _classify(self, text: str) -> str:
        lower = text.lower()
        if any(term in lower for term in ("provider", "route", "quota", "429", "api key", "huggingface", "openai", "gemini")):
            return "provider_debugging"
        if any(term in lower for term in ("test", "pytest", "failing")):
            return "test_failure"
        if any(term in lower for term in ("widget", "dashboard", "frontend")):
            return "dashboard_widget_build"
        return "general_software_task"

    def _detect_provider(self, payload: Dict[str, Any], text: str) -> str:
        explicit = payload.get("provider")
        if explicit:
            return self._provider_alias(str(explicit).lower())
        lower = text.lower()
        candidates = {
            "huggingface": ["huggingface", "hugging face", "hf"],
            "google": ["gemini", "google", "ai studio"],
            "openai": ["openai", "gpt"],
            "anthropic": ["anthropic", "claude"],
            "openrouter": ["openrouter"],
            "nvidia_nim": ["nvidia", "nim"],
            "cerebras": ["cerebras"],
            "cohere": ["cohere"],
            "groq": ["groq"],
            "mistral": ["mistral"],
            "together": ["together"],
            "perplexity": ["perplexity", "pplx"],
            "fireworks": ["fireworks"],
            "deepseek": ["deepseek"],
            "xai": ["xai", "grok"],
            "replicate": ["replicate"],
            "fal": ["fal"],
            "hyperbolic": ["hyperbolic"],
            "novita": ["novita"],
            "nscale": ["nscale"],
            "ovhcloud": ["ovhcloud", "ovh cloud", "ovh"],
            "deepinfra": ["deepinfra", "deep infra"],
            "featherless": ["featherless"],
            "litellm": ["litellm"],
            "tgi": ["tgi", "llamacpp", "llama.cpp"],
        }
        for provider, aliases in candidates.items():
            if any(alias in lower for alias in aliases):
                return provider
        return "unknown"

    def _provider_alias(self, provider: str) -> str:
        aliases = {
            "hf": "huggingface",
            "gemini": "google",
            "google_ai_studio": "google",
            "pplx": "perplexity",
            "grok": "xai",
            "ovh": "ovhcloud",
            "ovh_cloud": "ovhcloud",
            "deep infra": "deepinfra",
        }
        return aliases.get(provider, provider)

    def _risk_for(self, task_class: str) -> str:
        return "medium" if task_class in ("provider_debugging", "test_failure") else "low"

    def _allowed_actions(self, task_class: str) -> List[str]:
        base = ["read_files", "read_logs", "summarize"]
        if task_class == "provider_debugging":
            return base + ["inspect_runtime_state", "inspect_provider_policy", "draft_patch"]
        if task_class == "test_failure":
            return base + ["run_lint", "run_tests", "draft_patch"]
        return base + ["draft_patch"]

    def _success_criteria(self, task_class: str) -> List[str]:
        if task_class == "provider_debugging":
            return [
                "root cause category identified",
                "local diagnostics run before cloud escalation",
                "fallback or fix recommendation attached",
                "chronicle summary generated",
            ]
        return [
            "task scope bounded",
            "required evidence identified",
            "verification plan attached",
            "chronicle summary generated",
        ]

    def _intent(self, text: str, task_class: str) -> str:
        if text:
            return text[:180]
        return task_class.replace("_", " ")

    def _task_id(self, text: str, task_class: str) -> str:
        source = f"{task_class}:{text}:{self._utc_now()}"
        return "tsk_" + uuid.uuid5(uuid.NAMESPACE_URL, source).hex[:12]

    def _meta_rule(self, key: str, default: Any) -> Any:
        return self.policies.get("meta_rules", {}).get(key, default)


    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
