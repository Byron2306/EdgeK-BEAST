"""Registry-bound operator language interpretation for BEAST.

This is the first production slice of the text synthesis architecture: normal
operator phrases are normalized, matched to bounded service-registry intents,
bound to the local BEAST world model, adjudicated, and realized without any
provider call.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping

from app.kernel.compute.operator_language import (
    AnswerFrame,
    CandidateMeaning,
    EvidenceBinding,
    MeaningResolutionState,
    OperatorMeaningDomain,
    compile_bounded_meaning,
    realize_answer_frame,
)
from app.kernel.compute.residual_contracts import sha256_digest, utc_now_iso
from app.kernel.networking.service_registry import Service, ServiceRegistry
from app.kernel.registry.commons_space_registry import CommonsSpaceRegistry
from app.kernel.registry.provider_registry import ProviderRecord, ProviderRegistry


_TOKEN_RE = re.compile(r"[a-z0-9_.:/-]+")
_FILE_TOKEN_RE = re.compile(r"^[a-z0-9_./-]+\.[a-z0-9]{1,12}$")
_PATH_TOKEN_RE = re.compile(r"^[a-z0-9_.-]+(?:/[a-z0-9_.-]+)+$")
_ORIGINAL_PATH_RE = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+|[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,12}")
_UNSAFE_ACTIONS = frozenset({
    "apply", "create", "delete", "deploy", "disable", "enable", "kill",
    "modify", "publish", "reconcile", "remove", "restart", "run", "start", "stop",
})
_REGISTRY_TERMS = frozenset({"registry", "service", "services", "endpoint", "endpoints", "port", "ports"})
_ENDPOINT_TERMS = frozenset({"endpoint", "endpoints", "url", "upstream", "port", "ports", "bound", "listen", "listening"})
_HEALTH_TERMS = frozenset({"health", "healthy", "status", "alive", "ready"})
_LIST_TERMS = frozenset({"all", "list", "show", "summarize", "registry", "services"})
_FILE_TERMS = frozenset({"file", "files", "path", "paths", "exists", "exist", "present"})
_REPOSITORY_TERMS = frozenset({"repo", "repository", "workspace", "git", "branch", "commit", "worktree"})
_MODEL_TERMS = frozenset({"model", "models", "provider", "providers", "adapter", "adapters", "backend", "lane"})
_SPACE_TERMS = frozenset({
    "space", "spaces", "commons", "package", "packages", "hypothesis", "hypotheses",
    "reproduction", "reproductions", "replay", "replays", "trust",
})
_CONTAINER_TERMS = frozenset({"container", "containers", "docker", "podman", "image", "images"})
_LOG_TERMS = frozenset({"log", "logs", "receipt", "receipts", "evidence", "guardian"})
_COMMON_SYNONYMS = {
    "common": "commons",
    "commons": "commons",
    "beast": "beast",
    "arda": "arda",
    "seraph": "seraph_ui",
    "ui": "seraph_ui",
    "api": "seraph_api",
}
_PROVIDER_SYNONYMS = {
    "hf": "huggingface",
    "hugging-face": "huggingface",
    "nvidia": "nvidia_nim",
    "nim": "nvidia_nim",
    "local-nim": "local_nim",
    "local_nim": "local_nim",
    "llamacpp": "llama_cpp",
    "llama-cpp": "llama_cpp",
    "open-router": "openrouter",
}


@dataclass(frozen=True, slots=True)
class OperatorLanguageRequest:
    utterance: str
    tone: str = "concise"
    workspace_id: str = "operator"
    privacy_domain: str = "operator"
    discourse_digest: str = ""
    policy_digest: str = ""


@dataclass(frozen=True, slots=True)
class OperatorLanguageReceipt:
    utterance_digest: str
    normalized_utterance: str
    domain: OperatorMeaningDomain
    state: MeaningResolutionState
    intent: str
    bound_names: tuple[str, ...]
    service_names: tuple[str, ...]
    registry_digest: str
    evidence_digests: tuple[str, ...]
    provider_called: bool
    action_taken: bool
    reason: str
    created_at: str

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class OperatorLanguageResponse:
    output: str
    receipt: OperatorLanguageReceipt
    candidates: tuple[CandidateMeaning, ...]
    answer_frame: AnswerFrame | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "beast_object_type": "operator_language_response",
            "version": "1.0",
            "output": self.output,
            "receipt": {**asdict(self.receipt), "receipt_digest": self.receipt.receipt_digest},
            "answer_frame": asdict(self.answer_frame) if self.answer_frame is not None else None,
            "candidates": [asdict(candidate) for candidate in self.candidates],
        }


class OperatorPhraseNormalizer:
    def normalize(self, utterance: str) -> tuple[str, tuple[str, ...]]:
        normalized = " ".join(_TOKEN_RE.findall(str(utterance or "").casefold()))
        tokens = tuple(dict.fromkeys(normalized.split()))
        return normalized, tokens


class OperatorPhraseLattice:
    def classify(self, tokens: tuple[str, ...]) -> tuple[OperatorMeaningDomain, str, tuple[str, ...]]:
        unsafe = tuple(token for token in tokens if token in _UNSAFE_ACTIONS)
        if unsafe:
            return OperatorMeaningDomain.SERVICE, "unsupported_action", unsafe
        token_set = set(tokens)
        if token_set & _CONTAINER_TERMS:
            return OperatorMeaningDomain.CONTAINER, "read_container_state", ()
        if token_set & _LOG_TERMS:
            return OperatorMeaningDomain.LOG, "read_evidence_log", ()
        if token_set & _MODEL_TERMS:
            return OperatorMeaningDomain.MODEL, "read_model_provider", ()
        if token_set & _REPOSITORY_TERMS:
            return OperatorMeaningDomain.REPOSITORY, "read_repository_state", ()
        if token_set & _FILE_TERMS or any(_FILE_TOKEN_RE.fullmatch(token) or _PATH_TOKEN_RE.fullmatch(token) for token in tokens):
            return OperatorMeaningDomain.FILE, "read_file_state", ()
        if token_set & _SPACE_TERMS and not token_set & _HEALTH_TERMS:
            return OperatorMeaningDomain.SPACE, "read_commons_space", ()
        if token_set & _HEALTH_TERMS:
            return OperatorMeaningDomain.SERVICE, "read_service_health", ()
        if token_set & _ENDPOINT_TERMS:
            return OperatorMeaningDomain.SERVICE, "read_service_endpoint", ()
        if token_set & _LIST_TERMS and token_set & _REGISTRY_TERMS:
            return OperatorMeaningDomain.SERVICE, "summarize_service_registry", ()
        if token_set & _REGISTRY_TERMS:
            return OperatorMeaningDomain.SERVICE, "read_service_endpoint", ()
        return OperatorMeaningDomain.SERVICE, "unsupported_query", ()


class ServiceRegistryWorldBinder:
    def __init__(self, registry_path: str | Path):
        self.registry_path = Path(registry_path)

    def registry(self) -> ServiceRegistry:
        return ServiceRegistry.from_file(self.registry_path)

    def bind_services(self, registry: ServiceRegistry, tokens: tuple[str, ...]) -> tuple[Service, ...]:
        service_by_name = registry.services
        resolved: list[Service] = []
        for token in tokens:
            direct = _COMMON_SYNONYMS.get(token, token)
            if direct in service_by_name and service_by_name[direct] not in resolved:
                resolved.append(service_by_name[direct])
                continue
            for name, service in service_by_name.items():
                hostname_stem = service.hostname.split(".", 1)[0]
                if token in {name, hostname_stem, service.hostname} and service not in resolved:
                    resolved.append(service)
        return tuple(resolved)


class ProviderRegistryWorldBinder:
    def __init__(self, provider_registry: ProviderRegistry | None = None):
        self.provider_registry = provider_registry or ProviderRegistry()

    def bind_providers(self, tokens: tuple[str, ...]) -> tuple[ProviderRecord, ...]:
        records = {record.provider_id: record for record in self.provider_registry.records(include_disabled=True)}
        resolved: list[ProviderRecord] = []
        for token in tokens:
            name = _PROVIDER_SYNONYMS.get(token, token.replace("-", "_"))
            if name in records and records[name] not in resolved:
                resolved.append(records[name])
        return tuple(resolved)

    def default_records(self, *, limit: int = 8) -> tuple[ProviderRecord, ...]:
        records_by_id = {record.provider_id: record for record in self.provider_registry.records(include_disabled=True)}
        preferred = [
            records_by_id[name]
            for name in ("ollama", "codex", "openai", "huggingface", "nvidia_nim")
            if name in records_by_id
        ]
        records = tuple(records_by_id[name] for name in sorted(records_by_id))
        return tuple((preferred or records)[:limit])

    def digest(self) -> str:
        return sha256_digest(self.provider_registry.inventory())


class WorkspaceWorldBinder:
    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()

    def repository_state(self) -> dict[str, Any]:
        branch = self._git("rev-parse", "--abbrev-ref", "HEAD")
        commit = self._git("rev-parse", "HEAD")
        porcelain = self._git("status", "--porcelain=v1", "--untracked-files=all")
        dirty_paths = [line[3:] for line in porcelain.splitlines() if len(line) > 3]
        return {
            "path": str(self.workspace_root),
            "branch": branch or "unknown",
            "commit": commit,
            "dirty_count": len(dirty_paths),
            "dirty_paths_preview": dirty_paths[:12],
            "git_available": bool(branch or commit),
        }

    def file_state(self, tokens: tuple[str, ...], *, utterance: str = "") -> tuple[dict[str, Any] | None, str]:
        original_paths = [
            item
            for item in _ORIGINAL_PATH_RE.findall(utterance)
            if "/" in item or "." in item
        ]
        file_tokens = original_paths or [
            token for token in tokens if _FILE_TOKEN_RE.fullmatch(token) or _PATH_TOKEN_RE.fullmatch(token)
        ]
        if not file_tokens:
            return None, "Name a concrete relative file path."
        rel = file_tokens[0].lstrip("/")
        candidate = (self.workspace_root / rel).resolve()
        if self.workspace_root != candidate and self.workspace_root not in candidate.parents:
            return None, "File path escapes the workspace."
        if ".git" in candidate.relative_to(self.workspace_root).parts:
            return None, "File path targets git metadata."
        state = "present" if candidate.is_file() else ("directory" if candidate.is_dir() else "missing")
        size = candidate.stat().st_size if candidate.is_file() else 0
        return {
            "path": str(candidate.relative_to(self.workspace_root)),
            "state": state,
            "size_bytes": size,
            "workspace_root": str(self.workspace_root),
            "digest": self._file_digest(candidate) if candidate.is_file() else "",
        }, "file path bound"

    def digest(self) -> str:
        state = self.repository_state()
        return sha256_digest({key: value for key, value in state.items() if key != "dirty_paths_preview"})

    def _git(self, *args: str) -> str:
        try:
            proc = subprocess.run(
                ["git", "-C", str(self.workspace_root), *args],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=0.7,
                check=False,
            )
            if proc.returncode == 0:
                return proc.stdout.strip()
        except Exception:
            pass
        return ""

    def _file_digest(self, path: Path) -> str:
        try:
            return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return ""


class CommonsSpaceWorldBinder:
    def __init__(self, commons_registry: CommonsSpaceRegistry | None = None):
        self.commons_registry = commons_registry or CommonsSpaceRegistry()

    def summary(self) -> dict[str, Any]:
        return self.commons_registry.list_spaces()

    def bind_space(self, tokens: tuple[str, ...]) -> tuple[dict[str, Any] | None, str]:
        registry = self.summary()
        spaces = {str(item.get("space_id") or ""): item for item in registry.get("spaces") or []}
        for token in tokens:
            normalized = token.replace("-", "_")
            if token in spaces:
                return spaces[token], "space_id bound"
            if normalized in spaces:
                return spaces[normalized], "space_id bound"
        return None, "Name one Commons space: " + ", ".join(sorted(spaces)) if spaces else "No local Commons Spaces are registered."

    def detail(self, space_id: str) -> dict[str, Any]:
        return self.commons_registry.get(space_id)

    def digest(self) -> str:
        return sha256_digest(self.summary())


class ContainerWorldBinder:
    def __init__(self, snapshot_provider: Callable[[], tuple[Mapping[str, Any], ...]] | None = None):
        self.snapshot_provider = snapshot_provider

    def snapshot(self) -> tuple[Mapping[str, Any], ...]:
        if self.snapshot_provider is not None:
            return tuple(self.snapshot_provider())
        for executable in ("docker", "podman"):
            rows = self._container_cli(executable)
            if rows:
                return rows
        return ()

    def bind_container(self, tokens: tuple[str, ...]) -> tuple[Mapping[str, Any], ...]:
        rows = self.snapshot()
        resolved: list[Mapping[str, Any]] = []
        token_set = set(tokens)
        for row in rows:
            names = {
                str(row.get("name") or "").casefold(),
                str(row.get("Name") or "").casefold(),
                str(row.get("Names") or "").casefold(),
                str(row.get("image") or "").casefold(),
                str(row.get("Image") or "").casefold(),
            }
            names.update(part for name in tuple(names) for part in re.split(r"[^a-z0-9_.:/-]+", name) if part)
            if token_set & names and row not in resolved:
                resolved.append(row)
        return tuple(resolved)

    def digest(self) -> str:
        return sha256_digest(tuple(dict(row) for row in self.snapshot()))

    def _container_cli(self, executable: str) -> tuple[Mapping[str, Any], ...]:
        try:
            proc = subprocess.run(
                [executable, "ps", "--format", "{{json .}}"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=0.8,
                check=False,
            )
        except Exception:
            return ()
        if proc.returncode != 0:
            return ()
        rows = []
        for line in proc.stdout.splitlines():
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, Mapping):
                rows.append(parsed)
        return tuple(rows)


class EvidenceLogWorldBinder:
    def __init__(self, evidence_root: str | Path):
        self.evidence_root = Path(evidence_root)

    def bind_log(self, tokens: tuple[str, ...]) -> tuple[Mapping[str, Any] | None, str]:
        files = tuple(sorted(self.evidence_root.glob("*.json"), key=lambda item: item.stat().st_mtime_ns if item.exists() else 0, reverse=True))
        if not files:
            return None, "No local JSON evidence receipts are present."
        token_set = set(tokens)
        selected = None
        for path in files:
            parts = set(re.split(r"[^a-z0-9]+", path.stem.casefold()))
            if token_set & parts:
                selected = path
                break
        selected = selected or files[0]
        try:
            payload = json.loads(selected.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return None, f"Evidence receipt could not be read: {exc}"
        if not isinstance(payload, Mapping):
            return None, "Evidence receipt is not an object."
        summary = self._summary(selected, payload)
        return {
            "source": selected.name,
            "summary": summary,
            "path": str(selected),
            "receipt_digest": sha256_digest(payload),
            "keys": tuple(sorted(str(key) for key in payload)[:12]),
        }, "evidence receipt bound"

    def digest(self) -> str:
        files = [path.name for path in sorted(self.evidence_root.glob("*.json"))]
        return sha256_digest({"evidence_root": str(self.evidence_root), "files": files})

    def _summary(self, path: Path, payload: Mapping[str, Any]) -> str:
        status = payload.get("status") or payload.get("final_status") or payload.get("passed")
        services = payload.get("services") or payload.get("health") or {}
        fragments = [f"{path.name}"]
        if status != "":
            fragments.append(f"status={status}")
        if isinstance(services, Mapping) and services:
            fragments.append("services=" + ",".join(sorted(str(key) for key in services)[:6]))
        return "; ".join(fragments)


class OperatorMeaningAdjudicator:
    def adjudicate(
        self, *, intent: str, registry: ServiceRegistry, services: tuple[Service, ...], unsafe_terms: tuple[str, ...],
    ) -> tuple[MeaningResolutionState, str, tuple[Service, ...]]:
        if intent == "unsupported_action":
            return (
                MeaningResolutionState.UNSUPPORTED,
                "I can interpret registry facts here, but I will not perform actions from this read-only language path: "
                + ", ".join(unsafe_terms),
                services,
            )
        if intent == "unsupported_query":
            return (
                MeaningResolutionState.UNSUPPORTED,
                "I could not bind that request to the service-registry language slice.",
                (),
            )
        if intent == "summarize_service_registry":
            return MeaningResolutionState.RESOLVED, "registry summary requested", tuple(registry.services.values())
        if len(services) == 1:
            return MeaningResolutionState.RESOLVED, "single service bound from registry", services
        if not services:
            return (
                MeaningResolutionState.AMBIGUOUS,
                "Name one service: " + ", ".join(sorted(registry.services)),
                services,
            )
        return (
            MeaningResolutionState.AMBIGUOUS,
            "More than one service matched: " + ", ".join(service.name for service in services),
            services,
        )


class OperatorLanguagePlane:
    """Read-only service-registry language plane owned by ComputePlane."""

    def __init__(
        self, *, registry_path: str | Path, workspace_root: str | Path | None = None,
        provider_registry: ProviderRegistry | None = None, commons_registry: CommonsSpaceRegistry | None = None,
        container_snapshot_provider: Callable[[], tuple[Mapping[str, Any], ...]] | None = None,
        evidence_root: str | Path | None = None,
    ):
        self.registry_path = Path(registry_path)
        self.workspace_root = Path(workspace_root or Path(__file__).resolve().parents[3]).expanduser().resolve()
        self.normalizer = OperatorPhraseNormalizer()
        self.lattice = OperatorPhraseLattice()
        self.world_binder = ServiceRegistryWorldBinder(self.registry_path)
        self.provider_binder = ProviderRegistryWorldBinder(provider_registry)
        self.workspace_binder = WorkspaceWorldBinder(self.workspace_root)
        self.commons_binder = CommonsSpaceWorldBinder(commons_registry)
        self.container_binder = ContainerWorldBinder(container_snapshot_provider)
        self.evidence_binder = EvidenceLogWorldBinder(evidence_root or self.workspace_root / "evidence")
        self.adjudicator = OperatorMeaningAdjudicator()

    def answer(self, request: OperatorLanguageRequest | Mapping[str, Any] | str) -> OperatorLanguageResponse:
        request = self._coerce_request(request)
        normalized, tokens = self.normalizer.normalize(request.utterance)
        domain, intent, unsafe_terms = self.lattice.classify(tokens)
        if domain is OperatorMeaningDomain.CONTAINER:
            return self._answer_container(request=request, normalized=normalized, tokens=tokens, intent=intent)
        if domain is OperatorMeaningDomain.LOG:
            return self._answer_log(request=request, normalized=normalized, tokens=tokens, intent=intent)
        if domain is OperatorMeaningDomain.MODEL:
            return self._answer_model(request=request, normalized=normalized, tokens=tokens, intent=intent)
        if domain is OperatorMeaningDomain.REPOSITORY:
            return self._answer_repository(request=request, normalized=normalized, intent=intent)
        if domain is OperatorMeaningDomain.FILE:
            return self._answer_file(request=request, normalized=normalized, tokens=tokens, intent=intent)
        if domain is OperatorMeaningDomain.SPACE:
            return self._answer_space(request=request, normalized=normalized, tokens=tokens, intent=intent)
        registry = self.world_binder.registry()
        services = self.world_binder.bind_services(registry, tokens)
        state, reason, adjudicated_services = self.adjudicator.adjudicate(
            intent=intent, registry=registry, services=services, unsafe_terms=unsafe_terms,
        )
        evidence = self._evidence(registry=registry, request=request)
        candidates = tuple(
            self._candidate_for(service, intent=intent, state=state, evidence=evidence)
            for service in adjudicated_services
        )
        frame: AnswerFrame | None = None
        output: str
        if state is MeaningResolutionState.RESOLVED:
            meaning, frame = self._meaning_frame_for(intent=intent, registry=registry, services=adjudicated_services, evidence=evidence)
            candidates = (meaning,)
            output = realize_answer_frame(frame, tone=request.tone)
        else:
            output = self._unresolved_output(state=state, reason=reason, registry=registry, services=adjudicated_services)
        receipt = OperatorLanguageReceipt(
            utterance_digest=sha256_digest(request.utterance),
            normalized_utterance=normalized,
            domain=OperatorMeaningDomain.SERVICE,
            state=state,
            intent=intent,
            bound_names=tuple(service.name for service in adjudicated_services),
            service_names=tuple(service.name for service in adjudicated_services),
            registry_digest=registry.digest(),
            evidence_digests=tuple(item.evidence_digest for item in evidence),
            provider_called=False,
            action_taken=False,
            reason=reason,
            created_at=utc_now_iso(),
        )
        return OperatorLanguageResponse(output=output, receipt=receipt, candidates=candidates, answer_frame=frame)

    def _answer_model(
        self, *, request: OperatorLanguageRequest, normalized: str, tokens: tuple[str, ...], intent: str,
    ) -> OperatorLanguageResponse:
        providers = self.provider_binder.bind_providers(tokens)
        registry_digest = self.provider_binder.digest()
        evidence = self._generic_evidence(
            evidence_digest=registry_digest, world_digest=registry_digest, source="ProviderRegistry",
            request=request, policy="operator-language.provider-registry.read-only.v1",
        )
        if not providers:
            providers = self.provider_binder.default_records()
            output = (
                "Ambiguous provider/model request. Name one provider. Available examples: "
                + ", ".join(record.provider_id for record in providers)
                + "."
            )
            receipt = self._receipt(
                request=request, normalized=normalized, state=MeaningResolutionState.AMBIGUOUS,
                intent=intent, names=tuple(record.provider_id for record in providers),
                registry_digest=registry_digest, evidence=evidence, reason="provider not specified",
            )
            candidates = tuple(self._model_candidate(record, state=MeaningResolutionState.AMBIGUOUS, evidence=()) for record in providers)
            return OperatorLanguageResponse(output=output, receipt=receipt, candidates=candidates)
        if len(providers) > 1:
            output = "Ambiguous provider/model request. More than one provider matched: " + ", ".join(record.provider_id for record in providers) + "."
            receipt = self._receipt(
                request=request, normalized=normalized, state=MeaningResolutionState.AMBIGUOUS,
                intent=intent, names=tuple(record.provider_id for record in providers),
                registry_digest=registry_digest, evidence=evidence, reason="multiple providers matched",
            )
            candidates = tuple(self._model_candidate(record, state=MeaningResolutionState.AMBIGUOUS, evidence=()) for record in providers)
            return OperatorLanguageResponse(output=output, receipt=receipt, candidates=candidates)
        record = providers[0]
        meaning, frame = compile_bounded_meaning(
            meaning_id=f"meaning:provider-registry:{record.provider_id}",
            domain=OperatorMeaningDomain.MODEL,
            intent=intent,
            slots={
                "name": str(record.default_model or record.provider_id),
                "provider": record.provider_id,
                "title": f"{record.provider_id} provider model",
                "body": (
                    f"{record.provider_id} uses backend {record.backend}; default model "
                    f"{record.default_model or record.provider_id}; risk {record.risk_level}; "
                    f"approval required {record.requires_approval}."
                ),
                "backend": record.backend,
                "enabled": record.enabled,
                "base_url": record.base_url or "",
                "proxy_path": record.proxy_path,
                "risk_level": record.risk_level,
                "requires_approval": record.requires_approval,
            },
            evidence=evidence,
            template_id="provider_registry.model.v1",
        )
        receipt = self._receipt(
            request=request, normalized=normalized, state=MeaningResolutionState.RESOLVED,
            intent=intent, names=(record.provider_id,), registry_digest=registry_digest,
            evidence=evidence, reason="single provider bound from registry",
        )
        return OperatorLanguageResponse(
            output=realize_answer_frame(frame, tone=request.tone), receipt=receipt, candidates=(meaning,), answer_frame=frame,
        )

    def _answer_container(
        self, *, request: OperatorLanguageRequest, normalized: str, tokens: tuple[str, ...], intent: str,
    ) -> OperatorLanguageResponse:
        rows = self.container_binder.snapshot()
        matches = self.container_binder.bind_container(tokens)
        world_digest = self.container_binder.digest()
        evidence = self._generic_evidence(
            evidence_digest=world_digest, world_digest=world_digest, source="container-runtime:docker-or-podman",
            request=request, policy="operator-language.container-state.read-only.v1",
        )
        if not rows:
            receipt = self._receipt(
                request=request, normalized=normalized, state=MeaningResolutionState.UNSUPPORTED,
                intent=intent, names=(), registry_digest=world_digest, evidence=evidence,
                reason="no local container runtime inventory available",
            )
            return OperatorLanguageResponse(
                output="Unsupported container request. No local container runtime inventory is available.",
                receipt=receipt, candidates=(),
            )
        if not matches:
            receipt = self._receipt(
                request=request, normalized=normalized, state=MeaningResolutionState.AMBIGUOUS,
                intent=intent, names=tuple(self._container_name(row) for row in rows[:8]),
                registry_digest=world_digest, evidence=evidence, reason="container not specified",
            )
            return OperatorLanguageResponse(
                output="Ambiguous container request. Name one container: " + ", ".join(self._container_name(row) for row in rows[:8]) + ".",
                receipt=receipt, candidates=tuple(self._container_candidate(row, state=MeaningResolutionState.AMBIGUOUS, evidence=()) for row in rows[:8]),
            )
        if len(matches) > 1:
            names = tuple(self._container_name(row) for row in matches)
            receipt = self._receipt(
                request=request, normalized=normalized, state=MeaningResolutionState.AMBIGUOUS,
                intent=intent, names=names, registry_digest=world_digest, evidence=evidence,
                reason="multiple containers matched",
            )
            return OperatorLanguageResponse(
                output="Ambiguous container request. More than one container matched: " + ", ".join(names) + ".",
                receipt=receipt, candidates=tuple(self._container_candidate(row, state=MeaningResolutionState.AMBIGUOUS, evidence=()) for row in matches),
            )
        row = matches[0]
        name = self._container_name(row)
        image = str(row.get("image") or row.get("Image") or "unknown")
        status = str(row.get("status") or row.get("Status") or row.get("State") or "unknown")
        meaning, frame = compile_bounded_meaning(
            meaning_id=f"meaning:container-state:{name}",
            domain=OperatorMeaningDomain.CONTAINER,
            intent=intent,
            slots={
                "name": name,
                "image": image,
                "title": f"Container: {name}",
                "body": f"{name} is using image {image}; status {status}.",
                "status": status,
                "container_id": str(row.get("id") or row.get("ID") or ""),
            },
            evidence=evidence,
            template_id="container.state.v1",
        )
        receipt = self._receipt(
            request=request, normalized=normalized, state=MeaningResolutionState.RESOLVED,
            intent=intent, names=(name,), registry_digest=world_digest, evidence=evidence,
            reason="single container bound from runtime inventory",
        )
        return OperatorLanguageResponse(
            output=realize_answer_frame(frame, tone=request.tone), receipt=receipt, candidates=(meaning,), answer_frame=frame,
        )

    def _answer_log(
        self, *, request: OperatorLanguageRequest, normalized: str, tokens: tuple[str, ...], intent: str,
    ) -> OperatorLanguageResponse:
        state, reason = self.evidence_binder.bind_log(tokens)
        world_digest = self.evidence_binder.digest()
        evidence = self._generic_evidence(
            evidence_digest=sha256_digest(state or {"reason": reason, "evidence_root": str(self.evidence_binder.evidence_root)}),
            world_digest=world_digest, source=str(self.evidence_binder.evidence_root),
            request=request, policy="operator-language.evidence-log.read-only.v1",
        )
        if state is None:
            receipt = self._receipt(
                request=request, normalized=normalized, state=MeaningResolutionState.UNSUPPORTED,
                intent=intent, names=(), registry_digest=world_digest, evidence=evidence, reason=reason,
            )
            return OperatorLanguageResponse(output=f"Unsupported log request. {reason}", receipt=receipt, candidates=())
        meaning, frame = compile_bounded_meaning(
            meaning_id="meaning:evidence-log:" + sha256_digest(state["source"]).removeprefix("sha256:")[:24],
            domain=OperatorMeaningDomain.LOG,
            intent=intent,
            slots={
                "source": state["source"],
                "summary": state["summary"],
                "title": f"Evidence log: {state['source']}",
                "body": state["summary"],
                "path": state["path"],
                "receipt_digest": state["receipt_digest"],
                "keys": state["keys"],
            },
            evidence=evidence,
            template_id="evidence.log.v1",
        )
        receipt = self._receipt(
            request=request, normalized=normalized, state=MeaningResolutionState.RESOLVED,
            intent=intent, names=(state["source"],), registry_digest=world_digest,
            evidence=evidence, reason=reason,
        )
        return OperatorLanguageResponse(
            output=realize_answer_frame(frame, tone=request.tone), receipt=receipt, candidates=(meaning,), answer_frame=frame,
        )

    def _answer_repository(self, *, request: OperatorLanguageRequest, normalized: str, intent: str) -> OperatorLanguageResponse:
        state = self.workspace_binder.repository_state()
        world_digest = self.workspace_binder.digest()
        evidence = self._generic_evidence(
            evidence_digest=world_digest, world_digest=world_digest, source=str(self.workspace_root),
            request=request, policy="operator-language.workspace.read-only.v1",
        )
        meaning, frame = compile_bounded_meaning(
            meaning_id="meaning:workspace-repository:active",
            domain=OperatorMeaningDomain.REPOSITORY,
            intent=intent,
            slots={
                "path": state["path"],
                "branch": state["branch"],
                "title": "Active BEAST repository",
                "body": (
                    f"Repository {state['path']} is on branch {state['branch']} "
                    f"at commit {state['commit'] or 'unknown'} with {state['dirty_count']} changed paths."
                ),
                "commit": state["commit"],
                "dirty_count": state["dirty_count"],
                "dirty_paths_preview": state["dirty_paths_preview"],
                "git_available": state["git_available"],
            },
            evidence=evidence,
            template_id="workspace.repository.v1",
        )
        receipt = self._receipt(
            request=request, normalized=normalized, state=MeaningResolutionState.RESOLVED,
            intent=intent, names=("active-repository",), registry_digest=world_digest,
            evidence=evidence, reason="active workspace repository bound",
        )
        return OperatorLanguageResponse(
            output=realize_answer_frame(frame, tone=request.tone), receipt=receipt, candidates=(meaning,), answer_frame=frame,
        )

    def _answer_file(
        self, *, request: OperatorLanguageRequest, normalized: str, tokens: tuple[str, ...], intent: str,
    ) -> OperatorLanguageResponse:
        state, reason = self.workspace_binder.file_state(tokens, utterance=request.utterance)
        world_digest = self.workspace_binder.digest()
        evidence = self._generic_evidence(
            evidence_digest=sha256_digest(state or {"reason": reason, "workspace": str(self.workspace_root)}),
            world_digest=world_digest, source=str(self.workspace_root),
            request=request, policy="operator-language.file-state.read-only.v1",
        )
        if state is None:
            receipt = self._receipt(
                request=request, normalized=normalized, state=MeaningResolutionState.AMBIGUOUS,
                intent=intent, names=(), registry_digest=world_digest, evidence=evidence, reason=reason,
            )
            return OperatorLanguageResponse(
                output=f"Ambiguous file request. {reason}", receipt=receipt, candidates=(),
            )
        meaning, frame = compile_bounded_meaning(
            meaning_id="meaning:file-state:" + sha256_digest(state["path"]).removeprefix("sha256:")[:24],
            domain=OperatorMeaningDomain.FILE,
            intent=intent,
            slots={
                "path": state["path"],
                "state": state["state"],
                "title": f"File state: {state['path']}",
                "body": f"{state['path']} is {state['state']} in {state['workspace_root']} ({state['size_bytes']} bytes).",
                "size_bytes": state["size_bytes"],
                "file_digest": state["digest"],
                "workspace_root": state["workspace_root"],
            },
            evidence=evidence,
            template_id="workspace.file_state.v1",
        )
        receipt = self._receipt(
            request=request, normalized=normalized, state=MeaningResolutionState.RESOLVED,
            intent=intent, names=(state["path"],), registry_digest=world_digest, evidence=evidence, reason=reason,
        )
        return OperatorLanguageResponse(
            output=realize_answer_frame(frame, tone=request.tone), receipt=receipt, candidates=(meaning,), answer_frame=frame,
        )

    def _answer_space(
        self, *, request: OperatorLanguageRequest, normalized: str, tokens: tuple[str, ...], intent: str,
    ) -> OperatorLanguageResponse:
        space, reason = self.commons_binder.bind_space(tokens)
        registry = self.commons_binder.summary()
        world_digest = self.commons_binder.digest()
        evidence = self._generic_evidence(
            evidence_digest=world_digest, world_digest=world_digest, source=str(self.commons_binder.commons_registry.root),
            request=request, policy="operator-language.commons-spaces.read-only.v1",
        )
        if space is None:
            state = MeaningResolutionState.AMBIGUOUS if registry.get("count") else MeaningResolutionState.UNSUPPORTED
            receipt = self._receipt(
                request=request, normalized=normalized, state=state, intent=intent, names=(),
                registry_digest=world_digest, evidence=evidence, reason=reason,
            )
            prefix = "Ambiguous" if state is MeaningResolutionState.AMBIGUOUS else "Unsupported"
            return OperatorLanguageResponse(output=f"{prefix} Commons Space request. {reason}", receipt=receipt, candidates=())
        detail = self.commons_binder.detail(str(space.get("space_id") or ""))
        manifest = detail.get("manifest") or {}
        receipt_payload = detail.get("reduction_receipt") or {}
        reproductions = tuple(dict(item) for item in (detail.get("reproductions") or ()))
        best_reproduction = max(
            reproductions,
            key=lambda item: float(item.get("trust_score") or 0.0),
            default={},
        )
        displacement = receipt_payload.get("displacement") or {}
        verifier = receipt_payload.get("verifier") or {}
        detail_digest = sha256_digest({
            "manifest_hash": manifest.get("manifest_hash"),
            "receipt_id": receipt_payload.get("receipt_id"),
            "reproduction_ids": [item.get("reproduction_id") for item in reproductions],
        })
        evidence = self._generic_evidence(
            evidence_digest=detail_digest,
            world_digest=world_digest,
            source=str(self.commons_binder.commons_registry.root / str(space.get("space_id") or "")),
            request=request,
            policy="operator-language.commons-space-detail.read-only.v1",
        )
        reproduction_phrase = (
            f"{len(reproductions)} reproduction receipt(s); best trust "
            f"{best_reproduction.get('trust_score', 0.0)} "
            f"({best_reproduction.get('trust_class') or 'unreproduced'})."
        )
        body = (
            f"Commons Space {space.get('space_id')} is {space.get('adoption_state') or 'unknown'}; "
            f"promotion state {space.get('promotion_state') or 'unknown'}; "
            f"valid {bool(space.get('valid'))}; artifacts {space.get('artifact_count')}; "
            f"provider calls avoided {displacement.get('provider_calls_avoided')}; "
            f"verifier passed {verifier.get('passed')}; {reproduction_phrase} "
            "Remote or imported Spaces remain hypotheses until reproduced and explicitly promoted locally."
        )
        meaning, frame = compile_bounded_meaning(
            meaning_id=f"meaning:commons-space:{space['space_id']}",
            domain=OperatorMeaningDomain.SPACE,
            intent=intent,
            slots={
                "space_id": str(space.get("space_id") or ""),
                "runtime": str(space.get("runtime") or space.get("task_class") or "unknown"),
                "title": f"Commons Space: {space.get('space_id')}",
                "body": body,
                "valid": bool(space.get("valid")),
                "manifest_hash": str(manifest.get("manifest_hash") or ""),
                "receipt_id": str(receipt_payload.get("receipt_id") or ""),
                "adoption_state": str(space.get("adoption_state") or ""),
                "promotion_state": str(space.get("promotion_state") or ""),
                "artifact_types": tuple(str(item) for item in (space.get("artifact_types") or ())),
                "artifact_count": int(space.get("artifact_count") or 0),
                "provider_calls_avoided": int(displacement.get("provider_calls_avoided") or 0),
                "verifier_passed": bool(verifier.get("passed")),
                "reproduction_count": len(reproductions),
                "best_reproduction_trust_score": float(best_reproduction.get("trust_score") or 0.0),
                "best_reproduction_trust_class": str(best_reproduction.get("trust_class") or "unreproduced"),
            },
            evidence=evidence,
            template_id="commons.space.v1",
        )
        receipt = self._receipt(
            request=request, normalized=normalized, state=MeaningResolutionState.RESOLVED,
            intent=intent, names=(str(space.get("space_id") or ""),), registry_digest=world_digest,
            evidence=evidence, reason=reason,
        )
        return OperatorLanguageResponse(
            output=realize_answer_frame(frame, tone=request.tone), receipt=receipt, candidates=(meaning,), answer_frame=frame,
        )

    def _coerce_request(self, value: OperatorLanguageRequest | Mapping[str, Any] | str) -> OperatorLanguageRequest:
        if isinstance(value, OperatorLanguageRequest):
            return value
        if isinstance(value, str):
            return OperatorLanguageRequest(utterance=value)
        return OperatorLanguageRequest(
            utterance=str(value.get("utterance") or value.get("prompt") or ""),
            tone=str(value.get("tone") or "concise"),
            workspace_id=str(value.get("workspace_id") or "operator"),
            privacy_domain=str(value.get("privacy_domain") or "operator"),
            discourse_digest=str(value.get("discourse_digest") or ""),
            policy_digest=str(value.get("policy_digest") or ""),
        )

    def _evidence(self, *, registry: ServiceRegistry, request: OperatorLanguageRequest) -> tuple[EvidenceBinding, ...]:
        world_digest = registry.digest()
        policy_digest = request.policy_digest or sha256_digest({
            "policy": "operator-language.service-registry.read-only.v1",
            "privacy_domain": request.privacy_domain,
        })
        temporal_scope_digest = self._temporal_scope_digest(str(self.registry_path), world_digest=world_digest)
        return (
            EvidenceBinding(
                evidence_digest=world_digest,
                source=str(self.registry_path),
                world_digest=world_digest,
                policy_digest=policy_digest,
                temporal_scope_digest=temporal_scope_digest,
            ),
        )

    def _generic_evidence(
        self, *, evidence_digest: str, world_digest: str, source: str, request: OperatorLanguageRequest, policy: str,
    ) -> tuple[EvidenceBinding, ...]:
        return (
            EvidenceBinding(
                evidence_digest=evidence_digest,
                source=source,
                world_digest=world_digest,
                policy_digest=request.policy_digest or sha256_digest({
                    "policy": policy, "privacy_domain": request.privacy_domain,
                }),
                temporal_scope_digest=self._temporal_scope_digest(source, world_digest=world_digest),
            ),
        )

    def _temporal_scope_digest(self, source: str, *, world_digest: str) -> str:
        path = Path(source)
        if path.exists():
            stat = path.stat()
            return sha256_digest({
                "source": str(path.resolve()),
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
                "world_digest": world_digest,
            })
        return sha256_digest({
            "source": source,
            "world_digest": world_digest,
        })

    def _receipt(
        self, *, request: OperatorLanguageRequest, normalized: str, state: MeaningResolutionState, intent: str,
        names: tuple[str, ...], registry_digest: str, evidence: tuple[EvidenceBinding, ...], reason: str,
    ) -> OperatorLanguageReceipt:
        return OperatorLanguageReceipt(
            utterance_digest=sha256_digest(request.utterance),
            normalized_utterance=normalized,
            domain=self._domain_for_intent(intent),
            state=state,
            intent=intent,
            bound_names=names,
            service_names=names,
            registry_digest=registry_digest,
            evidence_digests=tuple(item.evidence_digest for item in evidence),
            provider_called=False,
            action_taken=False,
            reason=reason,
            created_at=utc_now_iso(),
        )

    def _domain_for_intent(self, intent: str) -> OperatorMeaningDomain:
        if intent == "read_model_provider":
            return OperatorMeaningDomain.MODEL
        if intent == "read_container_state":
            return OperatorMeaningDomain.CONTAINER
        if intent == "read_evidence_log":
            return OperatorMeaningDomain.LOG
        if intent == "read_repository_state":
            return OperatorMeaningDomain.REPOSITORY
        if intent == "read_file_state":
            return OperatorMeaningDomain.FILE
        if intent == "read_commons_space":
            return OperatorMeaningDomain.SPACE
        return OperatorMeaningDomain.SERVICE

    def _container_candidate(
        self, row: Mapping[str, Any], *, state: MeaningResolutionState, evidence: tuple[EvidenceBinding, ...],
    ) -> CandidateMeaning:
        name = self._container_name(row)
        return CandidateMeaning(
            meaning_id=f"meaning:container-state:{name}",
            domain=OperatorMeaningDomain.CONTAINER,
            intent="read_container_state",
            slots={
                "name": name,
                "image": str(row.get("image") or row.get("Image") or "unknown"),
                "status": str(row.get("status") or row.get("Status") or row.get("State") or "unknown"),
            },
            evidence=evidence,
            resolution_state=state,
            confidence=1.0 if state is MeaningResolutionState.RESOLVED else 0.0,
            negative_conditions=("container runtime inventory drift",),
        )

    def _container_name(self, row: Mapping[str, Any]) -> str:
        return str(row.get("name") or row.get("Name") or row.get("Names") or row.get("id") or row.get("ID") or "unknown")

    def _model_candidate(
        self, record: ProviderRecord, *, state: MeaningResolutionState, evidence: tuple[EvidenceBinding, ...],
    ) -> CandidateMeaning:
        return CandidateMeaning(
            meaning_id=f"meaning:provider-registry:{record.provider_id}",
            domain=OperatorMeaningDomain.MODEL,
            intent="read_model_provider",
            slots={
                "name": str(record.default_model or record.provider_id),
                "provider": record.provider_id,
                "backend": record.backend,
                "enabled": record.enabled,
            },
            evidence=evidence,
            resolution_state=state,
            confidence=1.0 if state is MeaningResolutionState.RESOLVED else 0.0,
            negative_conditions=("provider registry policy drift",),
        )

    def _candidate_for(
        self, service: Service, *, intent: str, state: MeaningResolutionState, evidence: tuple[EvidenceBinding, ...],
    ) -> CandidateMeaning:
        return CandidateMeaning(
            meaning_id=f"meaning:service-registry:{intent}:{service.name}",
            domain=OperatorMeaningDomain.SERVICE,
            intent=intent,
            slots=self._service_slots(service),
            evidence=evidence if state is MeaningResolutionState.RESOLVED else (),
            resolution_state=state,
            confidence=1.0 if state is MeaningResolutionState.RESOLVED else 0.0,
            negative_conditions=("registry digest drift", "service disabled") if service.enabled else ("service disabled",),
        )

    def _meaning_frame_for(
        self, *, intent: str, registry: ServiceRegistry, services: tuple[Service, ...], evidence: tuple[EvidenceBinding, ...],
    ) -> tuple[CandidateMeaning, AnswerFrame]:
        if intent == "summarize_service_registry":
            slots = {
                "name": "service-registry",
                "status": "registered",
                "title": "BEAST service registry",
                "body": "; ".join(self._endpoint_sentence(service) for service in services),
                "registry_digest": registry.digest(),
                "service_count": len(services),
            }
            meaning_id = "meaning:service-registry:summarize"
            template_id = "service_registry.summary.v1"
        else:
            service = services[0]
            slots = {
                **self._service_slots(service),
                "title": f"{service.name} service endpoint",
                "body": self._health_sentence(service) if intent == "read_service_health" else self._endpoint_sentence(service),
                "registry_digest": registry.digest(),
            }
            meaning_id = f"meaning:service-registry:{intent}:{service.name}"
            template_id = "service_registry.service.v1"
        meaning, frame = compile_bounded_meaning(
            meaning_id=meaning_id,
            domain=OperatorMeaningDomain.SERVICE,
            intent=intent,
            slots=slots,
            evidence=evidence,
            template_id=template_id,
        )
        return meaning, frame

    def _service_slots(self, service: Service) -> dict[str, Any]:
        return {
            "name": service.name,
            "status": "enabled" if service.enabled else "disabled",
            "hostname": service.hostname,
            "upstream": service.upstream,
            "port": service.port,
            "health_path": service.health_path,
            "health_url": f"http://{service.upstream}{service.health_path}",
            "trust_domain": service.trust_domain,
        }

    def _endpoint_sentence(self, service: Service) -> str:
        return (
            f"{service.name} is registered at http://{service.upstream} "
            f"with health check http://{service.upstream}{service.health_path} "
            f"and trust domain {service.trust_domain}."
        )

    def _health_sentence(self, service: Service) -> str:
        enabled = "enabled" if service.enabled else "disabled"
        return (
            f"{service.name} is {enabled} in the registry; probe "
            f"http://{service.upstream}{service.health_path} for live health."
        )

    def _unresolved_output(
        self, *, state: MeaningResolutionState, reason: str, registry: ServiceRegistry, services: tuple[Service, ...],
    ) -> str:
        if state is MeaningResolutionState.AMBIGUOUS:
            matched = ", ".join(service.name for service in services) if services else ", ".join(sorted(registry.services))
            return f"Ambiguous service-registry request. {reason}. Available services: {matched}."
        return f"Unsupported service-registry request. {reason} No provider was called and no action was taken."
