"""Operational Phase-3 capability composition graph.

Step 4 is the first cross-domain thinking object.  It combines:

* a frozen Phase-2 socket-listener fossil;
* live Phase-3 lockfile and certificate domain summaries;
* topology facts;
* policy facts;
* current evidence facts;

into derived composition claims without copying individual domain logic into an
answerer.  Later Phase-3 steps add relevance pruning, residual law, and
deterministic text/visual expression over this canonical graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping

from app.kernel.compute.deterministic_intelligence import (
    canonical_json,
    require_digest,
    sha256_bytes,
    sha256_digest,
)


PHASE3_COMPOSITION_VERSION = "2026-08-04.phase3.composition.v1"
SUPPORTED_RELEVANCE_RELATIONS = frozenset({"supports", "contributes_topology", "constrains", "requires_refusal"})
PHASE3_EXPECTED_FOSSIL_RECEIPT_DIGEST = "sha256:7f0d90bda84f1130198738a0ec29d009bb53edbb21588579b50799f751b692cc"
PHASE3_EXPECTED_FOSSIL_SUMMARY_DIGEST = "sha256:33f5ecc2762faa364ca7c8b8c86288d72ca36a5373aefc13a65147d5fd9f7c44"
PHASE3_EXPECTED_FOSSIL_DIGEST = "sha256:a438e0ad8e2f3bae72c24c51fea2b648e4ea5c9eb2a8fa612f233ef97d26a58e"


class Phase3FactStatus(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    STALE = "stale"
    RESIDUAL_REQUIRED = "residual_required"


class Phase3FactSource(str, Enum):
    FOSSIL = "fossil"
    LIVE_RECEIPT = "live_receipt"
    TOPOLOGY = "topology"
    POLICY = "policy"
    CURRENT_EVIDENCE = "current_evidence"
    DERIVED = "derived"


class Phase3CompositionError(ValueError):
    """Raised when a Phase-3 composition graph cannot be built or trusted."""


@dataclass(frozen=True, slots=True)
class Phase3CompositionFact:
    fact_id: str
    source: Phase3FactSource
    subject: str
    predicate: str
    object: str = ""
    value: Any = None
    status: Phase3FactStatus = Phase3FactStatus.SUPPORTED
    evidence_digest: str = ""
    domain: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fact_id.strip() or not self.subject.strip() or not self.predicate.strip():
            raise ValueError("composition facts require id, subject and predicate")
        if not isinstance(self.source, Phase3FactSource):
            object.__setattr__(self, "source", Phase3FactSource(self.source))
        if not isinstance(self.status, Phase3FactStatus):
            object.__setattr__(self, "status", Phase3FactStatus(self.status))
        if self.evidence_digest:
            require_digest(self.evidence_digest, field_name="evidence_digest")
        if self.status is Phase3FactStatus.SUPPORTED and self.source not in {Phase3FactSource.TOPOLOGY, Phase3FactSource.POLICY, Phase3FactSource.DERIVED}:
            require_digest(self.evidence_digest, field_name=f"{self.fact_id}.evidence_digest")
        canonical_json(self.value)
        canonical_json(self.metadata)

    @property
    def fact_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase3CompositionEdge:
    edge_id: str
    source_fact: str
    target_fact: str
    relation: str
    status: Phase3FactStatus = Phase3FactStatus.SUPPORTED
    evidence_digest: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.edge_id.strip() or not self.source_fact.strip() or not self.target_fact.strip() or not self.relation.strip():
            raise ValueError("composition edges require id, source, target and relation")
        if not isinstance(self.status, Phase3FactStatus):
            object.__setattr__(self, "status", Phase3FactStatus(self.status))
        if self.evidence_digest:
            require_digest(self.evidence_digest, field_name="edge_evidence_digest")
        canonical_json(self.metadata)

    @property
    def edge_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase3DerivationRule:
    rule_id: str
    output_claim_id: str
    input_fact_ids: tuple[str, ...]
    policy_fact_ids: tuple[str, ...]
    transformation_version: str
    implementation_digest: str
    deterministic_result: Any
    status: Phase3FactStatus = Phase3FactStatus.SUPPORTED

    def __post_init__(self) -> None:
        if not self.rule_id.strip() or not self.output_claim_id.strip() or not self.transformation_version.strip():
            raise ValueError("derivation rule requires id, output claim and transformation version")
        if not self.input_fact_ids:
            raise ValueError("derivation rule requires explicit input facts")
        if not isinstance(self.status, Phase3FactStatus):
            object.__setattr__(self, "status", Phase3FactStatus(self.status))
        require_digest(self.implementation_digest, field_name="implementation_digest")
        canonical_json(self.deterministic_result)

    @property
    def rule_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase3CompositionQuery:
    query_id: str
    question: str
    subject: str
    target: str
    intent: str = "operational_risk_composition"

    def __post_init__(self) -> None:
        if not self.query_id.strip() or not self.question.strip() or not self.subject.strip() or not self.target.strip():
            raise ValueError("composition query requires id, question, subject and target")

    @property
    def query_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase3CompositionGraph:
    beast_object_type: str
    version: str
    graph_id: str
    query: Phase3CompositionQuery
    facts: tuple[Phase3CompositionFact, ...]
    edges: tuple[Phase3CompositionEdge, ...]
    derived_claim_ids: tuple[str, ...]
    residual_required: bool
    ordinary_answer_available: bool
    provider_calls_used: int
    production_authority_allowed: bool
    compiler_id: str = "beast.dai.phase3.composition-graph.v1"
    derivation_rules: tuple[Phase3DerivationRule, ...] = ()

    def __post_init__(self) -> None:
        if self.beast_object_type != "dai_phase3_composition_graph":
            raise ValueError("unexpected Phase-3 composition graph object type")
        if self.version != PHASE3_COMPOSITION_VERSION:
            raise ValueError("unexpected Phase-3 composition graph version")
        fact_ids = [fact.fact_id for fact in self.facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("composition fact ids must be unique")
        fact_id_set = set(fact_ids)
        for edge in self.edges:
            if edge.source_fact not in fact_id_set or edge.target_fact not in fact_id_set:
                raise ValueError(f"composition edge references unknown fact: {edge.edge_id}")
        for claim_id in self.derived_claim_ids:
            if claim_id not in fact_id_set:
                raise ValueError(f"derived claim id is not a fact: {claim_id}")
        rule_outputs = {rule.output_claim_id for rule in self.derivation_rules}
        missing_rules = set(self.derived_claim_ids) - rule_outputs
        if missing_rules:
            raise ValueError(f"derived claims missing derivation rules: {sorted(missing_rules)}")
        for rule in self.derivation_rules:
            if rule.output_claim_id not in fact_id_set:
                raise ValueError(f"derivation rule output is not a fact: {rule.rule_id}")
            for fact_id in (*rule.input_fact_ids, *rule.policy_fact_ids):
                if fact_id not in fact_id_set:
                    raise ValueError(f"derivation rule references unknown input fact: {rule.rule_id}")
        if self.provider_calls_used != 0:
            raise ValueError("Phase-3 composition graph must be zero-provider")
        if self.production_authority_allowed:
            raise ValueError("Phase-3 composition graph cannot grant production authority")
        if self.ordinary_answer_available and self.residual_required:
            raise ValueError("ordinary answer cannot be available while residual is required")

    @property
    def fact_map(self) -> dict[str, Phase3CompositionFact]:
        return {fact.fact_id: fact for fact in self.facts}

    @property
    def graph_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase3RelevanceSlice:
    """The minimal supported causal subgraph permitted to answer one query."""

    beast_object_type: str
    version: str
    graph_digest: str
    query_digest: str
    answer_claim_ids: tuple[str, ...]
    selected_fact_ids: tuple[str, ...]
    selected_edge_ids: tuple[str, ...]
    excluded_fact_ids: tuple[str, ...]
    excluded_edge_ids: tuple[str, ...]
    blocked_edge_ids: tuple[str, ...]
    residual_required: bool
    ordinary_answer_available: bool
    provider_calls_used: int
    production_authority_allowed: bool

    def __post_init__(self) -> None:
        if self.beast_object_type != "dai_phase3_relevance_slice":
            raise ValueError("unexpected Phase-3 relevance slice object type")
        require_digest(self.graph_digest, field_name="graph_digest")
        require_digest(self.query_digest, field_name="query_digest")
        if not self.answer_claim_ids:
            raise ValueError("relevance slice requires at least one answer claim")
        if self.ordinary_answer_available and self.residual_required:
            raise ValueError("ordinary answer cannot be available while relevance residue remains")
        if self.provider_calls_used != 0 or self.production_authority_allowed:
            raise ValueError("relevance pruning cannot grant provider or production authority")

    @property
    def slice_digest(self) -> str:
        return sha256_digest(self)


class Phase3ResidualAction(str, Enum):
    ANSWER = "answer"
    REFUSE = "refuse"


@dataclass(frozen=True, slots=True)
class Phase3ResidualRoute:
    """Capability gate between a relevance slice and any expression layer."""

    beast_object_type: str
    version: str
    graph_digest: str
    relevance_slice_digest: str
    action: Phase3ResidualAction
    unresolved_fact_ids: tuple[str, ...]
    unresolved_edge_ids: tuple[str, ...]
    speakable_fact_ids: tuple[str, ...]
    ordinary_answer_available: bool
    refusal_artifact_only: bool
    provider_calls_used: int
    production_authority_allowed: bool

    def __post_init__(self) -> None:
        if self.beast_object_type != "dai_phase3_residual_route":
            raise ValueError("unexpected Phase-3 residual route object type")
        if not isinstance(self.action, Phase3ResidualAction):
            object.__setattr__(self, "action", Phase3ResidualAction(self.action))
        require_digest(self.graph_digest, field_name="graph_digest")
        require_digest(self.relevance_slice_digest, field_name="relevance_slice_digest")
        unresolved = bool(self.unresolved_fact_ids or self.unresolved_edge_ids)
        if self.action is Phase3ResidualAction.REFUSE:
            if self.ordinary_answer_available or not self.refusal_artifact_only or self.speakable_fact_ids:
                raise ValueError("refusal route permits only a dedicated refusal artifact")
        if self.action is Phase3ResidualAction.ANSWER:
            if unresolved or not self.ordinary_answer_available or self.refusal_artifact_only:
                raise ValueError("ordinary answer route cannot contain unresolved residue")
        if self.provider_calls_used != 0 or self.production_authority_allowed:
            raise ValueError("residual route cannot grant provider or production authority")

    @property
    def route_digest(self) -> str:
        return sha256_digest(self)


def build_phase3_composition_graph(
    *,
    fossil_receipt_path: str | Path,
    lockfile_summary_path: str | Path,
    certificate_summary_path: str | Path,
) -> Phase3CompositionGraph:
    """Build the first multi-domain composition graph from receipt artifacts."""

    fossil = _read_json(Path(fossil_receipt_path))
    lockfile = _read_json(Path(lockfile_summary_path))
    certificate = _read_json(Path(certificate_summary_path))
    _verify_fossil_receipt(fossil, Path(fossil_receipt_path))
    _verify_lockfile_summary(lockfile, Path(lockfile_summary_path))
    _verify_certificate_summary(certificate, Path(certificate_summary_path))

    facts: list[Phase3CompositionFact] = [
        _fact(
            "fact:fossil:stale-listener",
            Phase3FactSource.FOSSIL,
            "stale_listener_capability",
            "frozen_capability_available",
            True,
            evidence_digest=str(fossil["receipt_digest"]),
            domain="socket_listener",
            metadata={"fossil_digest": fossil["fossil_digest"], "summary_digest": fossil["summary_digest"]},
        ),
        _fact(
            "fact:fossil:stale-listener:kernel-witness",
            Phase3FactSource.FOSSIL,
            "stale_listener_capability",
            "exact_kernel_witness_bound",
            True,
            evidence_digest=str(fossil["summary_digest"]),
            domain="socket_listener",
        ),
        _fact(
            "fact:lockfile:cleanup",
            Phase3FactSource.LIVE_RECEIPT,
            "pid_lockfile_capability",
            "stale_artifact_cleanup_verified",
            bool(lockfile["green"]),
            evidence_digest=str(lockfile["summary_digest"]),
            domain="lockfile",
            metadata={"cleanup_receipt_digest": lockfile["cleanup_receipt_digest"]},
        ),
        _fact(
            "fact:lockfile:replay-refusal",
            Phase3FactSource.LIVE_RECEIPT,
            "pid_lockfile_capability",
            "stale_world_replay_refused",
            True,
            evidence_digest=str(lockfile["replay_receipt_digest"]),
            domain="lockfile",
        ),
        _fact(
            "fact:certificate:expired-refusal",
            Phase3FactSource.LIVE_RECEIPT,
            "certificate_handshake_capability",
            "expired_certificate_refused_before_app_payload",
            bool(certificate["expired_certificate_refused"]) and not bool(certificate["expired_app_payload_received"]),
            evidence_digest=str(certificate["summary_digest"]),
            domain="certificate",
            metadata={"handshake_receipt_digest": certificate["handshake_receipt_digest"]},
        ),
        _fact(
            "fact:certificate:control-accepted",
            Phase3FactSource.LIVE_RECEIPT,
            "certificate_handshake_capability",
            "valid_control_certificate_accepted",
            bool(certificate["control_certificate_accepted"]),
            evidence_digest=str(certificate["handshake_receipt_digest"]),
            domain="certificate",
        ),
        _fact(
            "fact:topology:gateway-uses-listener",
            Phase3FactSource.TOPOLOGY,
            "api_gateway",
            "depends_on",
            "stale_listener_capability",
            domain="topology",
        ),
        _fact(
            "fact:topology:gateway-uses-lockfile",
            Phase3FactSource.TOPOLOGY,
            "api_gateway",
            "depends_on",
            "pid_lockfile_capability",
            domain="topology",
        ),
        _fact(
            "fact:topology:gateway-uses-certificate",
            Phase3FactSource.TOPOLOGY,
            "api_gateway",
            "depends_on",
            "certificate_handshake_capability",
            domain="topology",
        ),
        _fact(
            "fact:policy:production-authority",
            Phase3FactSource.POLICY,
            "phase3_composition",
            "production_authority_allowed",
            False,
            domain="policy",
        ),
        _fact(
            "fact:policy:provider-calls",
            Phase3FactSource.POLICY,
            "phase3_composition",
            "provider_calls_allowed",
            False,
            domain="policy",
        ),
        _fact(
            "fact:evidence:current-three-domains",
            Phase3FactSource.CURRENT_EVIDENCE,
            "phase3_evidence_set",
            "current_three_domains_bound",
            True,
            evidence_digest=sha256_digest({
                "fossil": fossil["receipt_digest"],
                "lockfile": lockfile["summary_digest"],
                "certificate": certificate["summary_digest"],
            }),
            domain="current_evidence",
            metadata={"domain_count": 3},
        ),
    ]

    supported_inputs = _all_true(facts, (
        "fact:fossil:stale-listener",
        "fact:fossil:stale-listener:kernel-witness",
        "fact:lockfile:cleanup",
        "fact:lockfile:replay-refusal",
        "fact:certificate:expired-refusal",
        "fact:certificate:control-accepted",
        "fact:evidence:current-three-domains",
    ))
    production_allowed = _fact_value(facts, "fact:policy:production-authority") is True
    residual_required = not supported_inputs
    composition_ready = supported_inputs and not residual_required
    bounded_answer_available = composition_ready and not production_allowed
    execution_refused = not production_allowed
    facts.extend([
        _fact(
            "claim:phase3:multi-domain-composition-ready",
            Phase3FactSource.DERIVED,
            "api_gateway",
            "multi_domain_composition_ready",
            composition_ready,
            domain="derived",
            metadata={"input_domains": ("socket_listener", "lockfile", "certificate")},
        ),
        _fact(
            "claim:phase3:bounded-answer-available",
            Phase3FactSource.DERIVED,
            "api_gateway",
            "bounded_composition_answer_available",
            bounded_answer_available,
            domain="derived",
        ),
        _fact(
            "claim:phase3:execution-refused",
            Phase3FactSource.DERIVED,
            "api_gateway",
            "execution_refused_by_policy",
            execution_refused,
            domain="derived",
        ),
    ])

    edges = (
        _edge("edge:topology:listener", "fact:topology:gateway-uses-listener", "claim:phase3:multi-domain-composition-ready", "contributes_topology"),
        _edge("edge:topology:lockfile", "fact:topology:gateway-uses-lockfile", "claim:phase3:multi-domain-composition-ready", "contributes_topology"),
        _edge("edge:topology:certificate", "fact:topology:gateway-uses-certificate", "claim:phase3:multi-domain-composition-ready", "contributes_topology"),
        _edge("edge:fossil:listener", "fact:fossil:stale-listener", "claim:phase3:multi-domain-composition-ready", "supports"),
        _edge("edge:lockfile:cleanup", "fact:lockfile:cleanup", "claim:phase3:multi-domain-composition-ready", "supports"),
        _edge("edge:certificate:refusal", "fact:certificate:expired-refusal", "claim:phase3:multi-domain-composition-ready", "supports"),
        _edge("edge:policy:bounded-answer", "fact:policy:production-authority", "claim:phase3:bounded-answer-available", "constrains"),
        _edge("edge:policy:execution-refusal", "fact:policy:production-authority", "claim:phase3:execution-refused", "requires_refusal"),
    )
    implementation_digest = sha256_bytes(Path(__file__).read_bytes())
    derivation_rules = (
        Phase3DerivationRule(
            rule_id="rule:phase3:multi-domain-composition-ready:v1",
            output_claim_id="claim:phase3:multi-domain-composition-ready",
            input_fact_ids=(
                "fact:fossil:stale-listener",
                "fact:fossil:stale-listener:kernel-witness",
                "fact:lockfile:cleanup",
                "fact:lockfile:replay-refusal",
                "fact:certificate:expired-refusal",
                "fact:certificate:control-accepted",
                "fact:evidence:current-three-domains",
                "fact:topology:gateway-uses-listener",
                "fact:topology:gateway-uses-lockfile",
                "fact:topology:gateway-uses-certificate",
            ),
            policy_fact_ids=(),
            transformation_version="supported_inputs_and_topology_all_true.v1",
            implementation_digest=implementation_digest,
            deterministic_result={"value": composition_ready, "residual_required": residual_required},
        ),
        Phase3DerivationRule(
            rule_id="rule:phase3:bounded-answer-available:v1",
            output_claim_id="claim:phase3:bounded-answer-available",
            input_fact_ids=("claim:phase3:multi-domain-composition-ready",),
            policy_fact_ids=("fact:policy:production-authority",),
            transformation_version="composition_ready_and_not_production_allowed.v1",
            implementation_digest=implementation_digest,
            deterministic_result={"value": bounded_answer_available, "composition_ready": composition_ready, "production_allowed": production_allowed},
        ),
        Phase3DerivationRule(
            rule_id="rule:phase3:execution-refused:v1",
            output_claim_id="claim:phase3:execution-refused",
            input_fact_ids=("fact:policy:production-authority",),
            policy_fact_ids=("fact:policy:production-authority",),
            transformation_version="not_production_allowed_implies_execution_refused.v1",
            implementation_digest=implementation_digest,
            deterministic_result={"value": execution_refused, "production_allowed": production_allowed},
        ),
    )
    query = Phase3CompositionQuery(
        query_id="phase3:query:api-gateway-cross-domain-risk",
        subject="api_gateway",
        target="operator",
        question=(
            "Can BEAST compose the stale-listener fossil, stale lockfile cleanup, "
            "and expired-certificate refusal evidence for a new bounded API gateway risk question?"
        ),
    )
    return Phase3CompositionGraph(
        beast_object_type="dai_phase3_composition_graph",
        version=PHASE3_COMPOSITION_VERSION,
        graph_id="phase3:composition:socket-lockfile-certificate:v1",
        query=query,
        facts=tuple(facts),
        edges=edges,
        derived_claim_ids=(
            "claim:phase3:multi-domain-composition-ready",
            "claim:phase3:bounded-answer-available",
            "claim:phase3:execution-refused",
        ),
        residual_required=residual_required,
        ordinary_answer_available=bounded_answer_available,
        provider_calls_used=0,
        production_authority_allowed=False,
        derivation_rules=derivation_rules,
    )


def phase3_composition_receipt(graph: Phase3CompositionGraph) -> dict[str, Any]:
    receipt = {
        "beast_object_type": "dai_phase3_composition_graph_receipt",
        "version": PHASE3_COMPOSITION_VERSION,
        "graph_id": graph.graph_id,
        "graph_digest": graph.graph_digest,
        "query_digest": graph.query.query_digest,
        "fact_count": len(graph.facts),
        "edge_count": len(graph.edges),
        "derivation_rule_count": len(graph.derivation_rules),
        "derivation_rule_digests": tuple(rule.rule_digest for rule in graph.derivation_rules),
        "derived_claim_ids": graph.derived_claim_ids,
        "residual_required": graph.residual_required,
        "ordinary_answer_available": graph.ordinary_answer_available,
        "provider_calls_used": graph.provider_calls_used,
        "production_authority_allowed": graph.production_authority_allowed,
        "execution_authority_allowed": False,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def prune_phase3_composition_graph(
    graph: Phase3CompositionGraph,
    *,
    answer_claim_ids: tuple[str, ...] | None = None,
) -> Phase3RelevanceSlice:
    """Return only causal support for the query's explicit answer claims.

    Crucially, relevance is graph reachability into a requested conclusion, not
    a shared subject label. Unsupported/stale edges leading into that conclusion
    become bounded residue; they are never silently promoted into narration.
    """
    facts = graph.fact_map
    requested = answer_claim_ids or _default_answer_claim_ids(graph)
    if not requested:
        raise Phase3CompositionError("query has no permitted answer claims")
    if any(claim_id not in graph.derived_claim_ids for claim_id in requested):
        raise Phase3CompositionError("relevance answer claim is not a graph-derived claim")

    selected_facts = set(requested)
    selected_edges: set[str] = set()
    blocked_edges: set[str] = set()
    rule_inputs = {
        rule.output_claim_id: tuple(dict.fromkeys((*rule.input_fact_ids, *rule.policy_fact_ids)))
        for rule in graph.derivation_rules
        if rule.status is Phase3FactStatus.SUPPORTED
    }
    changed = True
    while changed:
        changed = False
        for fact_id in tuple(selected_facts):
            for input_fact in rule_inputs.get(fact_id, ()):
                if input_fact not in selected_facts:
                    selected_facts.add(input_fact)
                    changed = True
        for edge in graph.edges:
            if edge.target_fact not in selected_facts:
                continue
            source = facts[edge.source_fact]
            target = facts[edge.target_fact]
            supported = (
                edge.status is Phase3FactStatus.SUPPORTED
                and source.status is Phase3FactStatus.SUPPORTED
                and target.status is Phase3FactStatus.SUPPORTED
                and edge.relation in SUPPORTED_RELEVANCE_RELATIONS
            )
            if not supported:
                blocked_edges.add(edge.edge_id)
                continue
            if edge.edge_id not in selected_edges:
                selected_edges.add(edge.edge_id)
                changed = True
            if edge.source_fact not in selected_facts:
                selected_facts.add(edge.source_fact)
                changed = True

    blocked = bool(blocked_edges)
    residual = graph.residual_required or blocked
    ordered_facts = tuple(fact.fact_id for fact in graph.facts if fact.fact_id in selected_facts)
    ordered_edges = tuple(edge.edge_id for edge in graph.edges if edge.edge_id in selected_edges)
    excluded_facts = tuple(fact.fact_id for fact in graph.facts if fact.fact_id not in selected_facts)
    excluded_edges = tuple(edge.edge_id for edge in graph.edges if edge.edge_id not in selected_edges)
    return Phase3RelevanceSlice(
        beast_object_type="dai_phase3_relevance_slice",
        version="2026-08-04.phase3.relevance.v1",
        graph_digest=graph.graph_digest,
        query_digest=graph.query.query_digest,
        answer_claim_ids=tuple(requested),
        selected_fact_ids=ordered_facts,
        selected_edge_ids=ordered_edges,
        excluded_fact_ids=excluded_facts,
        excluded_edge_ids=excluded_edges,
        blocked_edge_ids=tuple(sorted(blocked_edges)),
        residual_required=residual,
        ordinary_answer_available=graph.ordinary_answer_available and not residual,
        provider_calls_used=0,
        production_authority_allowed=False,
    )


def phase3_relevance_receipt(slice_: Phase3RelevanceSlice) -> dict[str, Any]:
    receipt = {
        "beast_object_type": "dai_phase3_relevance_receipt",
        "version": slice_.version,
        "slice_digest": slice_.slice_digest,
        "graph_digest": slice_.graph_digest,
        "query_digest": slice_.query_digest,
        "answer_claim_ids": slice_.answer_claim_ids,
        "selected_fact_ids": slice_.selected_fact_ids,
        "selected_edge_ids": slice_.selected_edge_ids,
        "excluded_fact_ids": slice_.excluded_fact_ids,
        "excluded_edge_ids": slice_.excluded_edge_ids,
        "blocked_edge_ids": slice_.blocked_edge_ids,
        "residual_required": slice_.residual_required,
        "ordinary_answer_available": slice_.ordinary_answer_available,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def route_phase3_residuals(
    graph: Phase3CompositionGraph,
    relevance: Phase3RelevanceSlice,
) -> Phase3ResidualRoute:
    """Enforce ``RESIDUAL_REQUIRED != speakable fact`` before expression.

    This function is deliberately a capability gate, not a wording preference:
    unresolved relevance makes ordinary output unavailable and leaves no facts
    available to a text/visual compiler. A future verified promotion must first
    rebuild a supported graph and relevance slice before this route can answer.
    """
    if relevance.graph_digest != graph.graph_digest or relevance.query_digest != graph.query.query_digest:
        raise Phase3CompositionError("residual route must bind the exact graph and query relevance slice")
    facts = graph.fact_map
    unresolved_facts: set[str] = set()
    for fact_id in relevance.selected_fact_ids:
        fact = facts[fact_id]
        if fact.status is not Phase3FactStatus.SUPPORTED:
            unresolved_facts.add(fact_id)
    edge_map = {edge.edge_id: edge for edge in graph.edges}
    for edge_id in relevance.blocked_edge_ids:
        edge = edge_map[edge_id]
        unresolved_facts.update((edge.source_fact, edge.target_fact))
    unresolved_edges = tuple(sorted(relevance.blocked_edge_ids))
    if relevance.residual_required:
        action = Phase3ResidualAction.REFUSE
    else:
        action = Phase3ResidualAction.ANSWER
    if action is Phase3ResidualAction.REFUSE:
        return Phase3ResidualRoute(
            beast_object_type="dai_phase3_residual_route",
            version="2026-08-04.phase3.residual-route.v1",
            graph_digest=graph.graph_digest,
            relevance_slice_digest=relevance.slice_digest,
            action=action,
            unresolved_fact_ids=tuple(sorted(unresolved_facts)),
            unresolved_edge_ids=unresolved_edges,
            speakable_fact_ids=(),
            ordinary_answer_available=False,
            refusal_artifact_only=True,
            provider_calls_used=0,
            production_authority_allowed=False,
        )
    return Phase3ResidualRoute(
        beast_object_type="dai_phase3_residual_route",
        version="2026-08-04.phase3.residual-route.v1",
        graph_digest=graph.graph_digest,
        relevance_slice_digest=relevance.slice_digest,
        action=action,
        unresolved_fact_ids=(),
        unresolved_edge_ids=(),
        speakable_fact_ids=relevance.selected_fact_ids,
        ordinary_answer_available=True,
        refusal_artifact_only=False,
        provider_calls_used=0,
        production_authority_allowed=False,
    )


def phase3_residual_route_receipt(route: Phase3ResidualRoute) -> dict[str, Any]:
    receipt = {
        "beast_object_type": "dai_phase3_residual_route_receipt",
        "version": route.version,
        "route_digest": route.route_digest,
        "graph_digest": route.graph_digest,
        "relevance_slice_digest": route.relevance_slice_digest,
        "action": route.action.value,
        "unresolved_fact_ids": route.unresolved_fact_ids,
        "unresolved_edge_ids": route.unresolved_edge_ids,
        "speakable_fact_ids": route.speakable_fact_ids,
        "ordinary_answer_available": route.ordinary_answer_available,
        "refusal_artifact_only": route.refusal_artifact_only,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def write_phase3_composition_graph(path: str | Path, graph: Phase3CompositionGraph) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(canonical_json(graph))
    payload["graph_digest"] = graph.graph_digest
    target.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def write_phase3_composition_receipt(path: str | Path, graph: Phase3CompositionGraph) -> dict[str, Any]:
    receipt = phase3_composition_receipt(graph)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    return receipt


def write_phase3_relevance_receipt(path: str | Path, slice_: Phase3RelevanceSlice) -> dict[str, Any]:
    receipt = phase3_relevance_receipt(slice_)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    return receipt


def write_phase3_residual_route_receipt(path: str | Path, route: Phase3ResidualRoute) -> dict[str, Any]:
    receipt = phase3_residual_route_receipt(route)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    return receipt


def _default_answer_claim_ids(graph: Phase3CompositionGraph) -> tuple[str, ...]:
    """Map declared intent to a small allowed answer surface, never all facts."""
    intent = f"{graph.query.intent} {graph.query.question}".casefold()
    preferred = [
        "claim:phase3:multi-domain-composition-ready",
        "claim:phase3:bounded-answer-available",
    ]
    if any(token in intent for token in ("execute", "execution", "mutate", "repair", "restart")):
        preferred.append("claim:phase3:execution-refused")
    return tuple(claim_id for claim_id in preferred if claim_id in graph.derived_claim_ids)


def _fact(
    fact_id: str,
    source: Phase3FactSource,
    subject: str,
    predicate: str,
    value: Any,
    *,
    object: str = "",
    status: Phase3FactStatus = Phase3FactStatus.SUPPORTED,
    evidence_digest: str = "",
    domain: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> Phase3CompositionFact:
    return Phase3CompositionFact(
        fact_id=fact_id,
        source=source,
        subject=subject,
        predicate=predicate,
        object=object,
        value=value,
        status=status,
        evidence_digest=evidence_digest,
        domain=domain,
        metadata=dict(metadata or {}),
    )


def _edge(edge_id: str, source_fact: str, target_fact: str, relation: str) -> Phase3CompositionEdge:
    return Phase3CompositionEdge(edge_id=edge_id, source_fact=source_fact, target_fact=target_fact, relation=relation)


def _all_true(facts: list[Phase3CompositionFact], fact_ids: tuple[str, ...]) -> bool:
    by_id = {fact.fact_id: fact for fact in facts}
    return all(
        fact_id in by_id
        and by_id[fact_id].status is Phase3FactStatus.SUPPORTED
        and by_id[fact_id].value is True
        for fact_id in fact_ids
    )


def _fact_value(facts: list[Phase3CompositionFact], fact_id: str) -> Any:
    for fact in facts:
        if fact.fact_id == fact_id:
            return fact.value
    raise Phase3CompositionError(f"missing fact {fact_id}")


def _verify_fossil_receipt(receipt: Mapping[str, Any], path: Path) -> None:
    if receipt.get("beast_object_type") != "dai_phase3_capability_fossil_receipt":
        raise Phase3CompositionError("unexpected fossil receipt object type")
    _verify_receipt_digest(receipt)
    if receipt.get("receipt_digest") != PHASE3_EXPECTED_FOSSIL_RECEIPT_DIGEST:
        raise Phase3CompositionError("fossil receipt is not the pinned Phase-3 fossil")
    if receipt.get("fossil_digest") != PHASE3_EXPECTED_FOSSIL_DIGEST or receipt.get("summary_digest") != PHASE3_EXPECTED_FOSSIL_SUMMARY_DIGEST:
        raise Phase3CompositionError("fossil receipt does not bind pinned Phase-2 summary")
    if receipt.get("composition_use_allowed") is not True or receipt.get("execution_authority_allowed") is not False:
        raise Phase3CompositionError("fossil authority boundary mismatch")
    if receipt.get("provider_calls_used") != 0:
        raise Phase3CompositionError("fossil provider boundary mismatch")
    if not path.is_file():
        raise Phase3CompositionError("fossil receipt path missing")


def _verify_lockfile_summary(summary: Mapping[str, Any], path: Path) -> None:
    if summary.get("beast_object_type") != "dai_phase3_lockfile_domain_summary":
        raise Phase3CompositionError("unexpected lockfile summary object type")
    _verify_summary_digest(summary)
    if summary.get("green") is not True:
        raise Phase3CompositionError("lockfile domain is not green")
    if summary.get("provider_calls_used") != 0 or summary.get("production_authority_allowed") is not False:
        raise Phase3CompositionError("lockfile authority/provider boundary mismatch")
    if not path.is_file():
        raise Phase3CompositionError("lockfile summary path missing")
    directory = path.parent
    cleanup = _read_json(directory / "phase3_lockfile_cleanup_receipt.json")
    replay = _read_json(directory / "phase3_lockfile_stale_world_replay_receipt.json")
    lease = _read_json(directory / "phase3_lockfile_world_lease.json")
    _verify_receipt_digest(cleanup)
    _verify_receipt_digest(replay)
    _verify_lease_digest(lease)
    if summary.get("cleanup_receipt_digest") != cleanup.get("receipt_digest"):
        raise Phase3CompositionError("lockfile summary does not bind cleanup receipt")
    if summary.get("replay_receipt_digest") != replay.get("receipt_digest"):
        raise Phase3CompositionError("lockfile summary does not bind replay receipt")
    if summary.get("lease_digest") != lease.get("lease_digest"):
        raise Phase3CompositionError("lockfile summary does not bind world lease")
    if cleanup.get("lease_digest") != summary.get("lease_digest") or replay.get("lease_digest") != summary.get("lease_digest"):
        raise Phase3CompositionError("lockfile receipts do not bind the summary lease")
    if cleanup.get("executed") is not True or cleanup.get("stale_lock_removed") is not True or replay.get("refused") is not True:
        raise Phase3CompositionError("lockfile receipt semantics do not support summary")


def _verify_certificate_summary(summary: Mapping[str, Any], path: Path) -> None:
    if summary.get("beast_object_type") != "dai_phase3_certificate_domain_summary":
        raise Phase3CompositionError("unexpected certificate summary object type")
    _verify_summary_digest(summary)
    if summary.get("green") is not True:
        raise Phase3CompositionError("certificate domain is not green")
    if summary.get("expired_certificate_refused") is not True or summary.get("expired_app_payload_received") is not False:
        raise Phase3CompositionError("certificate refusal boundary mismatch")
    if summary.get("provider_calls_used") != 0 or summary.get("production_authority_allowed") is not False:
        raise Phase3CompositionError("certificate authority/provider boundary mismatch")
    if not path.is_file():
        raise Phase3CompositionError("certificate summary path missing")
    directory = path.parent
    handshake = _read_json(directory / "phase3_certificate_handshake_receipt.json")
    lease = _read_json(directory / "phase3_certificate_world_lease.json")
    _verify_receipt_digest(handshake)
    _verify_lease_digest(lease)
    if summary.get("handshake_receipt_digest") != handshake.get("receipt_digest"):
        raise Phase3CompositionError("certificate summary does not bind handshake receipt")
    if summary.get("lease_digest") != lease.get("lease_digest") or handshake.get("lease_digest") != summary.get("lease_digest"):
        raise Phase3CompositionError("certificate receipt does not bind world lease")
    if handshake.get("expired_certificate_refused") is not True or handshake.get("control_certificate_accepted") is not True:
        raise Phase3CompositionError("certificate receipt semantics do not support summary")


def _verify_receipt_digest(receipt: Mapping[str, Any]) -> None:
    claimed = str(receipt.get("receipt_digest") or "")
    require_digest(claimed, field_name="receipt_digest")
    body = dict(receipt)
    body.pop("receipt_digest", None)
    if sha256_digest(body) != claimed:
        raise Phase3CompositionError("receipt digest does not recompute")


def _verify_summary_digest(summary: Mapping[str, Any]) -> None:
    claimed = str(summary.get("summary_digest") or "")
    require_digest(claimed, field_name="summary_digest")
    body = dict(summary)
    body.pop("summary_digest", None)
    if sha256_digest(body) != claimed:
        raise Phase3CompositionError("summary digest does not recompute")


def _verify_lease_digest(lease_payload: Mapping[str, Any]) -> None:
    claimed = str(lease_payload.get("lease_digest") or "")
    require_digest(claimed, field_name="lease_digest")
    lease = lease_payload.get("lease")
    if sha256_digest(lease) != claimed:
        raise Phase3CompositionError("lease digest does not recompute")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Phase3CompositionError(f"missing JSON artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise Phase3CompositionError(f"JSON artifact must be an object: {path}")
    return payload
