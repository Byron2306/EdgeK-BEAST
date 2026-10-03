"""Deterministic Phase-3 text and visual expression from authorized facts only.

The visual compiler never accepts generated text as input. Both compilers use
the same route-authorized semantic facts, while independent verifiers inspect
their outputs without calling either compiler.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import html
import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest
from app.kernel.dai.phase3_composition import (
    Phase3CompositionGraph,
    Phase3RelevanceSlice,
    Phase3ResidualAction,
    Phase3ResidualRoute,
    prune_phase3_composition_graph,
    route_phase3_residuals,
)


PHASE3_EXPRESSION_VERSION = "2026-08-04.phase3.expression.v1"


@dataclass(frozen=True, slots=True)
class Phase3ExpressionBundle:
    beast_object_type: str
    version: str
    graph_digest: str
    route_digest: str
    semantic_digest: str
    action: str
    text: str
    svg: str
    expressed_fact_ids: tuple[str, ...]
    ordinary_answer_available: bool
    refusal_artifact_only: bool
    provider_calls_used: int
    production_authority_allowed: bool

    def __post_init__(self) -> None:
        if self.beast_object_type != "dai_phase3_expression_bundle":
            raise ValueError("unexpected Phase-3 expression bundle object type")
        if self.version != PHASE3_EXPRESSION_VERSION:
            raise ValueError("unexpected Phase-3 expression version")
        if self.refusal_artifact_only and (self.ordinary_answer_available or self.expressed_fact_ids):
            raise ValueError("refusal expression cannot contain ordinary facts")
        if self.provider_calls_used != 0 or self.production_authority_allowed:
            raise ValueError("Phase-3 expression cannot grant provider or production authority")

    @property
    def bundle_digest(self) -> str:
        return sha256_digest(self)


def compile_phase3_expression(
    graph: Phase3CompositionGraph,
    route: Phase3ResidualRoute,
    relevance: Phase3RelevanceSlice | None = None,
) -> Phase3ExpressionBundle:
    """Compile text and SVG separately from route-authorized semantic facts."""
    trusted_relevance, trusted_route, semantic_digest = _trusted_expression_context(graph, route, relevance)
    facts = graph.fact_map
    selected = tuple(facts[fact_id] for fact_id in trusted_route.speakable_fact_ids)
    if trusted_route.action is Phase3ResidualAction.REFUSE:
        text = _compile_refusal_text(graph, trusted_route, semantic_digest)
        svg = _compile_refusal_svg(graph, trusted_route, semantic_digest)
        expressed = ()
    else:
        text = _compile_answer_text(graph, selected, semantic_digest)
        svg = _compile_answer_svg(graph, selected, semantic_digest)
        expressed = tuple(fact.fact_id for fact in selected)
    return Phase3ExpressionBundle(
        beast_object_type="dai_phase3_expression_bundle",
        version=PHASE3_EXPRESSION_VERSION,
        graph_digest=graph.graph_digest,
        route_digest=trusted_route.route_digest,
        semantic_digest=semantic_digest,
        action=trusted_route.action.value,
        text=text,
        svg=svg,
        expressed_fact_ids=expressed,
        ordinary_answer_available=trusted_route.ordinary_answer_available,
        refusal_artifact_only=trusted_route.refusal_artifact_only,
        provider_calls_used=0,
        production_authority_allowed=False,
    )


def verify_phase3_text_entailment(
    graph: Phase3CompositionGraph,
    route: Phase3ResidualRoute,
    bundle: Phase3ExpressionBundle,
    relevance: Phase3RelevanceSlice | None = None,
) -> dict[str, Any]:
    """Independently inspect text propositions; do not call the text compiler."""
    context_error = ""
    try:
        _trusted_relevance, trusted_route, expected_semantic_digest = _trusted_expression_context(graph, route, relevance)
    except Exception as exc:
        trusted_route = route
        expected_semantic_digest = ""
        context_error = f"{type(exc).__name__}: {exc}"
    expected = tuple(trusted_route.speakable_fact_ids)
    facts = graph.fact_map
    text_lines = bundle.text.splitlines()
    semantic_line = f"Semantic digest: {bundle.semantic_digest}"
    gates: dict[str, bool] = {
        "derivation_context_recomputed": not context_error,
        "graph_bound": bundle.graph_digest == graph.graph_digest,
        "route_bound": bundle.route_digest == trusted_route.route_digest,
        "semantic_digest_independently_derived": bool(expected_semantic_digest) and bundle.semantic_digest == expected_semantic_digest,
        "action_matches_route": bundle.action == trusted_route.action.value,
        "ordinary_answer_gate_matches": bundle.ordinary_answer_available == trusted_route.ordinary_answer_available,
        "expressed_ids_match_route": bundle.expressed_fact_ids == expected,
        "text_semantic_digest_marker_matches": semantic_line in text_lines,
    }
    if trusted_route.action is Phase3ResidualAction.REFUSE:
        unresolved = ", ".join((*trusted_route.unresolved_fact_ids, *trusted_route.unresolved_edge_ids)) or "unresolved relevance state"
        allowed_lines = {
            f"Refusal: ordinary answer unavailable for {graph.query.query_id}.",
            f"Reason: unresolved or unsupported causal support ({unresolved}).",
            semantic_line,
            "Boundary: no fact assertion, provider call, production action or execution action was emitted.",
        }
        gates.update({
            "dedicated_refusal_present": bundle.text.startswith("Refusal:"),
            "ordinary_fact_markers_absent": "Fact " not in bundle.text,
            "no_expressed_facts": not bundle.expressed_fact_ids,
            "closed_world_refusal_text": set(text_lines) == allowed_lines and len(text_lines) == len(allowed_lines),
        })
    else:
        allowed_lines = {
            f"Answer: {graph.query.question}",
            semantic_line,
            "Boundary: zero provider calls; production and execution authority remain unavailable.",
        }
        gates["answer_header_present"] = bundle.text.startswith("Answer:")
        for fact_id in expected:
            fact = facts[fact_id]
            marker = f"Fact {fact_id}:"
            predicate = _humanize(fact.predicate)
            value = _value_text(fact.value)
            object_clause = f" -> {fact.object}" if fact.object else ""
            allowed_lines.add(f"Fact {fact.fact_id}: {fact.subject}{object_clause}; {predicate} = {value}.")
            line = next((candidate for candidate in text_lines if candidate.startswith(marker)), "")
            gates[f"text_has_{fact_id}"] = line.startswith(marker) and predicate in line and f"= {value}." in line
        for fact_id in set(facts) - set(expected):
            gates[f"text_excludes_{fact_id}"] = f"Fact {fact_id}:" not in bundle.text
        gates["closed_world_answer_text"] = set(text_lines) == allowed_lines and len(text_lines) == len(allowed_lines)
    red_gates = tuple(sorted(name for name, passed in gates.items() if not passed))
    receipt = {
        "beast_object_type": "dai_phase3_text_entailment_receipt",
        "version": PHASE3_EXPRESSION_VERSION,
        "bundle_digest": bundle.bundle_digest,
        "semantic_digest": bundle.semantic_digest,
        "expected_semantic_digest": expected_semantic_digest,
        "derivation_context_error": context_error,
        "verified": not red_gates,
        "red_gates": red_gates,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def verify_phase3_visual_entailment(
    graph: Phase3CompositionGraph,
    route: Phase3ResidualRoute,
    bundle: Phase3ExpressionBundle,
    relevance: Phase3RelevanceSlice | None = None,
) -> dict[str, Any]:
    """Independently inspect SVG propositions and layout; do not use text."""
    context_error = ""
    try:
        _trusted_relevance, trusted_route, expected_semantic_digest = _trusted_expression_context(graph, route, relevance)
    except Exception as exc:
        trusted_route = route
        expected_semantic_digest = ""
        context_error = f"{type(exc).__name__}: {exc}"
    expected = tuple(trusted_route.speakable_fact_ids)
    gates: dict[str, bool] = {
        "derivation_context_recomputed": not context_error,
        "graph_bound": bundle.graph_digest == graph.graph_digest,
        "route_bound": bundle.route_digest == trusted_route.route_digest,
        "semantic_digest_independently_derived": bool(expected_semantic_digest) and bundle.semantic_digest == expected_semantic_digest,
        "svg_is_independent_artifact": "<svg" in bundle.svg and "<text" in bundle.svg,
    }
    try:
        root = ET.fromstring(bundle.svg)
        width = int(root.attrib.get("width", "0"))
        height = int(root.attrib.get("height", "0"))
        gates["visual_semantic_digest_marker_matches"] = root.attrib.get("data-semantic-digest") == bundle.semantic_digest
        gates["visual_element_grammar_closed"] = _svg_element_grammar_closed(root)
        nodes = {node.attrib.get("data-fact-id", ""): node for node in root.findall(".//*[@data-fact-id]")}
        text_values = tuple(
            item.text or ""
            for item in root.iter()
            if item.tag.rsplit("}", 1)[-1] == "text"
        )
        if trusted_route.action is Phase3ResidualAction.REFUSE:
            reason = ", ".join((*trusted_route.unresolved_fact_ids, *trusted_route.unresolved_edge_ids)) or "unresolved causal support"
            allowed_text = [
                "REFUSAL - ordinary answer unavailable",
                reason,
                f"semantic: {bundle.semantic_digest}",
            ]
            gates["refusal_visual_present"] = root.find(".//*[@data-refusal-artifact='true']") is not None
            gates["no_fact_nodes"] = not nodes
            gates["closed_world_refusal_visual_text"] = Counter(text_values) == Counter(allowed_text)
        else:
            allowed_text = ["BEAST Phase-3 authorized composition", f"semantic: {bundle.semantic_digest}"]
            gates["node_set_matches_route"] = tuple(nodes) == expected
            expected_edges = {
                edge.edge_id
                for edge in graph.edges
                if edge.source_fact in expected and edge.target_fact in expected and edge.status.value == "supported"
            }
            rendered_edges = {edge.attrib.get("data-edge-id", "") for edge in root.findall(".//*[@data-edge-id]")}
            gates["visual_edge_set_matches_authorized_graph"] = rendered_edges == expected_edges
            gates["visual_edges_bind_known_nodes"] = all(
                edge.attrib.get("data-source-fact") in expected and edge.attrib.get("data-target-fact") in expected
                for edge in root.findall(".//*[@data-edge-id]")
            )
            for fact_id in expected:
                fact = graph.fact_map[fact_id]
                node = nodes.get(fact_id)
                labels = " ".join(
                    item.text or ""
                    for item in node.iter()
                    if item.tag.rsplit("}", 1)[-1] == "text"
                ) if node is not None else ""
                gates[f"visual_has_{fact_id}"] = node is not None and _humanize(fact.predicate) in labels and _value_text(fact.value) in labels
                allowed_text.extend((fact.subject, _humanize(fact.predicate), f"value: {_value_text(fact.value)}"))
                if node is not None:
                    x, y, node_width, node_height = (int(node.attrib[key]) for key in ("data-x", "data-y", "data-width", "data-height"))
                    gates[f"visual_inside_canvas_{fact_id}"] = x >= 0 and y >= 0 and x + node_width <= width and y + node_height <= height
            gates["closed_world_answer_visual_text"] = Counter(text_values) == Counter(allowed_text)
    except (ET.ParseError, ValueError, KeyError):
        gates["svg_parses"] = False
    red_gates = tuple(sorted(name for name, passed in gates.items() if not passed))
    receipt = {
        "beast_object_type": "dai_phase3_visual_entailment_receipt",
        "version": PHASE3_EXPRESSION_VERSION,
        "bundle_digest": bundle.bundle_digest,
        "semantic_digest": bundle.semantic_digest,
        "expected_semantic_digest": expected_semantic_digest,
        "derivation_context_error": context_error,
        "verified": not red_gates,
        "red_gates": red_gates,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def phase3_expression_receipt(
    bundle: Phase3ExpressionBundle,
    text_entailment: dict[str, Any],
    visual_entailment: dict[str, Any],
) -> dict[str, Any]:
    joined = bool(text_entailment.get("verified")) and bool(visual_entailment.get("verified"))
    receipt = {
        "beast_object_type": "dai_phase3_expression_receipt",
        "version": PHASE3_EXPRESSION_VERSION,
        "bundle_digest": bundle.bundle_digest,
        "semantic_digest": bundle.semantic_digest,
        "action": bundle.action,
        "ordinary_answer_available": bundle.ordinary_answer_available and joined,
        "refusal_artifact_only": bundle.refusal_artifact_only,
        "expressed_fact_ids": bundle.expressed_fact_ids,
        "text_entailment_receipt_digest": text_entailment["receipt_digest"],
        "visual_entailment_receipt_digest": visual_entailment["receipt_digest"],
        "joined_verification": joined,
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def write_phase3_expression_artifacts(
    root: str | Path,
    bundle: Phase3ExpressionBundle,
    text_entailment: dict[str, Any],
    visual_entailment: dict[str, Any],
) -> dict[str, Any]:
    target = Path(root)
    target.mkdir(parents=True, exist_ok=True)
    (target / "phase3_expression.txt").write_text(bundle.text + "\n", encoding="utf-8")
    (target / "phase3_expression.svg").write_text(bundle.svg + "\n", encoding="utf-8")
    (target / "phase3_expression_bundle.json").write_text(canonical_json({**asdict(bundle), "bundle_digest": bundle.bundle_digest}) + "\n", encoding="utf-8")
    (target / "phase3_text_entailment_receipt.json").write_text(canonical_json(text_entailment) + "\n", encoding="utf-8")
    (target / "phase3_visual_entailment_receipt.json").write_text(canonical_json(visual_entailment) + "\n", encoding="utf-8")
    receipt = phase3_expression_receipt(bundle, text_entailment, visual_entailment)
    (target / "phase3_expression_receipt.json").write_text(canonical_json(receipt) + "\n", encoding="utf-8")
    return receipt


def derive_phase3_expression_semantic_digest(
    graph: Phase3CompositionGraph,
    route: Phase3ResidualRoute,
    relevance: Phase3RelevanceSlice | None = None,
) -> str:
    """Independently derive the semantic digest from graph/relevance/route law."""

    _trusted_relevance, _trusted_route, semantic_digest = _trusted_expression_context(graph, route, relevance)
    return semantic_digest


def _trusted_expression_context(
    graph: Phase3CompositionGraph,
    route: Phase3ResidualRoute,
    relevance: Phase3RelevanceSlice | None,
) -> tuple[Phase3RelevanceSlice, Phase3ResidualRoute, str]:
    if route.graph_digest != graph.graph_digest:
        raise ValueError("expression route must bind the exact composition graph")
    expected_relevance = prune_phase3_composition_graph(
        graph,
        answer_claim_ids=relevance.answer_claim_ids if relevance is not None else None,
    )
    if relevance is not None and relevance.slice_digest != expected_relevance.slice_digest:
        raise ValueError("provided relevance slice does not recompute from graph")
    expected_route = route_phase3_residuals(graph, expected_relevance)
    if route.route_digest != expected_route.route_digest:
        raise ValueError("residual route does not recompute from graph and relevance")
    semantic_digest = sha256_digest(_semantic_derivation_payload(graph, expected_relevance, expected_route))
    return expected_relevance, expected_route, semantic_digest


def _semantic_derivation_payload(
    graph: Phase3CompositionGraph,
    relevance: Phase3RelevanceSlice,
    route: Phase3ResidualRoute,
) -> dict[str, Any]:
    facts = graph.fact_map
    edge_map = {edge.edge_id: edge for edge in graph.edges}
    selected_facts = tuple(facts[fact_id] for fact_id in route.speakable_fact_ids)
    selected_edges = tuple(edge_map[edge_id] for edge_id in relevance.selected_edge_ids)
    policy_facts = tuple(fact for fact in graph.facts if fact.source.value == "policy")
    return {
        "semantic_derivation_version": "2026-08-04.phase3.expression-semantic-derivation.v2",
        "graph_digest": graph.graph_digest,
        "graph_id": graph.graph_id,
        "graph_compiler_id": graph.compiler_id,
        "graph_version": graph.version,
        "query": asdict(graph.query),
        "query_digest": graph.query.query_digest,
        "relevance": {
            "slice_digest": relevance.slice_digest,
            "answer_claim_ids": relevance.answer_claim_ids,
            "selected_fact_ids": relevance.selected_fact_ids,
            "selected_edge_ids": relevance.selected_edge_ids,
            "excluded_fact_ids": relevance.excluded_fact_ids,
            "blocked_edge_ids": relevance.blocked_edge_ids,
            "ordinary_answer_available": relevance.ordinary_answer_available,
            "residual_required": relevance.residual_required,
        },
        "route": {
            "route_digest": route.route_digest,
            "action": route.action.value,
            "speakable_fact_ids": route.speakable_fact_ids,
            "unresolved_fact_ids": route.unresolved_fact_ids,
            "unresolved_edge_ids": route.unresolved_edge_ids,
            "ordinary_answer_available": route.ordinary_answer_available,
            "refusal_artifact_only": route.refusal_artifact_only,
        },
        "selected_facts": tuple(_semantic_fact(fact) for fact in selected_facts),
        "selected_edges": tuple(_semantic_edge(edge) for edge in selected_edges),
        "policy_facts": tuple(_semantic_fact(fact) for fact in policy_facts),
        "derived_claim_ids": graph.derived_claim_ids,
        "composition_result": {
            "graph_residual_required": graph.residual_required,
            "graph_ordinary_answer_available": graph.ordinary_answer_available,
            "route_ordinary_answer_available": route.ordinary_answer_available,
            "provider_calls_used": graph.provider_calls_used,
            "production_authority_allowed": graph.production_authority_allowed,
        },
    }


def _semantic_fact(fact: Any) -> dict[str, Any]:
    return {
        "fact_id": fact.fact_id,
        "source": fact.source.value,
        "subject": fact.subject,
        "predicate": fact.predicate,
        "object": fact.object,
        "value": fact.value,
        "status": fact.status.value,
        "evidence_digest": fact.evidence_digest,
        "domain": fact.domain,
        "metadata": dict(fact.metadata),
        "fact_digest": fact.fact_digest,
    }


def _semantic_edge(edge: Any) -> dict[str, Any]:
    return {
        "edge_id": edge.edge_id,
        "source_fact": edge.source_fact,
        "target_fact": edge.target_fact,
        "relation": edge.relation,
        "status": edge.status.value,
        "evidence_digest": edge.evidence_digest,
        "metadata": dict(edge.metadata),
        "edge_digest": edge.edge_digest,
    }


def _compile_answer_text(graph: Phase3CompositionGraph, facts: tuple[Any, ...], semantic_digest: str) -> str:
    lines = [f"Answer: {graph.query.question}", f"Semantic digest: {semantic_digest}"]
    for fact in facts:
        object_clause = f" -> {fact.object}" if fact.object else ""
        lines.append(f"Fact {fact.fact_id}: {fact.subject}{object_clause}; {_humanize(fact.predicate)} = {_value_text(fact.value)}.")
    lines.append("Boundary: zero provider calls; production and execution authority remain unavailable.")
    return "\n".join(lines)


def _compile_refusal_text(graph: Phase3CompositionGraph, route: Phase3ResidualRoute, semantic_digest: str) -> str:
    unresolved = ", ".join((*route.unresolved_fact_ids, *route.unresolved_edge_ids)) or "unresolved relevance state"
    return "\n".join((
        f"Refusal: ordinary answer unavailable for {graph.query.query_id}.",
        f"Reason: unresolved or unsupported causal support ({unresolved}).",
        f"Semantic digest: {semantic_digest}",
        "Boundary: no fact assertion, provider call, production action or execution action was emitted.",
    ))


def _compile_answer_svg(graph: Phase3CompositionGraph, facts: tuple[Any, ...], semantic_digest: str) -> str:
    width, node_width, node_height, margin, gap = 1000, 450, 82, 24, 18
    columns = 2
    rows = max(1, (len(facts) + columns - 1) // columns)
    height = margin * 2 + rows * node_height + max(0, rows - 1) * gap + 56
    pieces = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" data-semantic-digest="{semantic_digest}">']
    pieces.append('<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#6a9bc2"/></marker></defs><rect width="100%" height="100%" fill="#08111f"/><text x="24" y="30" fill="#e6f1ff" font-size="18">BEAST Phase-3 authorized composition</text>')
    positions = {}
    for index, fact in enumerate(facts):
        column, row = index % columns, index // columns
        positions[fact.fact_id] = (margin + column * (node_width + gap), 48 + row * (node_height + gap))
    selected_ids = set(positions)
    for edge in graph.edges:
        if edge.source_fact not in selected_ids or edge.target_fact not in selected_ids or edge.status.value != "supported":
            continue
        source_x, source_y = positions[edge.source_fact]
        target_x, target_y = positions[edge.target_fact]
        edge_id = html.escape(edge.edge_id, quote=True)
        pieces.append(
            f'<line data-edge-id="{edge_id}" data-source-fact="{html.escape(edge.source_fact, quote=True)}" data-target-fact="{html.escape(edge.target_fact, quote=True)}" '
            f'x1="{source_x + node_width // 2}" y1="{source_y + node_height // 2}" x2="{target_x + node_width // 2}" y2="{target_y + node_height // 2}" stroke="#6a9bc2" stroke-width="2" marker-end="url(#arrow)"/>'
        )
    for index, fact in enumerate(facts):
        x, y = positions[fact.fact_id]
        predicate = html.escape(_humanize(fact.predicate))
        subject = html.escape(fact.subject)
        value = html.escape(_value_text(fact.value))
        fact_id = html.escape(fact.fact_id, quote=True)
        pieces.append(
            f'<g data-fact-id="{fact_id}" data-x="{x}" data-y="{y}" data-width="{node_width}" data-height="{node_height}">'
            f'<rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" rx="10" fill="#12304a" stroke="#58b6ff"/>'
            f'<text x="{x + 12}" y="{y + 25}" fill="#ffffff" font-size="13">{subject}</text>'
            f'<text x="{x + 12}" y="{y + 49}" fill="#8ed1ff" font-size="12">{predicate}</text>'
            f'<text x="{x + 12}" y="{y + 70}" fill="#72e3a6" font-size="12">value: {value}</text></g>'
        )
    pieces.append(f'<text x="24" y="{height - 14}" fill="#a9b9c8" font-size="10">semantic: {semantic_digest}</text></svg>')
    return "".join(pieces)


def _compile_refusal_svg(graph: Phase3CompositionGraph, route: Phase3ResidualRoute, semantic_digest: str) -> str:
    reason = html.escape(", ".join((*route.unresolved_fact_ids, *route.unresolved_edge_ids)) or "unresolved causal support")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="180" viewBox="0 0 800 180" data-semantic-digest="{semantic_digest}">'
        '<rect width="100%" height="100%" fill="#241116"/>'
        '<g data-refusal-artifact="true"><rect x="24" y="28" width="752" height="112" rx="10" fill="#4a1820" stroke="#ff8495"/>'
        f'<text x="44" y="66" fill="#ffffff" font-size="20">REFUSAL - ordinary answer unavailable</text><text x="44" y="96" fill="#ffbdc6" font-size="12">{reason}</text>'
        f'<text x="44" y="122" fill="#d5aab2" font-size="10">semantic: {semantic_digest}</text></g></svg>'
    )


def _humanize(value: str) -> str:
    return value.replace("_", " ")


def _value_text(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (dict, list, tuple)):
        return canonical_json(value)
    return str(value)


def _svg_element_grammar_closed(root: ET.Element) -> bool:
    allowed_attrs = {
        "svg": {"xmlns", "width", "height", "viewBox", "data-semantic-digest"},
        "defs": set(),
        "marker": {"id", "markerWidth", "markerHeight", "refX", "refY", "orient"},
        "path": {"d", "fill"},
        "rect": {"width", "height", "fill", "x", "y", "rx", "stroke"},
        "text": {"x", "y", "fill", "font-size"},
        "g": {"data-fact-id", "data-x", "data-y", "data-width", "data-height", "data-refusal-artifact"},
        "line": {"data-edge-id", "data-source-fact", "data-target-fact", "x1", "y1", "x2", "y2", "stroke", "stroke-width", "marker-end"},
    }
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag not in allowed_attrs:
            return False
        if not set(element.attrib).issubset(allowed_attrs[tag]):
            return False
        if element.tail and element.tail.strip():
            return False
        if tag != "text" and element.text and element.text.strip():
            return False
    return True
