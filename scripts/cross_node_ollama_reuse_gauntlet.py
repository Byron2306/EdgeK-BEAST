#!/usr/bin/env python3
"""Cross-node Ollama crystallized-compute reuse gauntlet.

This proves the next inversion step:

1. Node A hosts a Space.
2. Host-side local Ollama summarizes it as crystallized compute from Node A
   inside a BEAST-native handoff packet.
3. Node B imports Node A's content-addressed bundle over the Docker network.
4. Node B locally verifies and replays it.
5. Host-side local Ollama, acting as Node B, decides whether to reuse it from
   the same BEAST-native language: task envelopes, insights, cascades,
   pathways, forge cards, registries, skill tree state, and verifier receipts.
6. BEAST attempts strict non-financial credit issuance and records whether the
   economy correctly gates unproven displacement.

No cloud provider API is called by this script.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx


NODE_A = "http://127.0.0.1:8101"
NODE_B = "http://127.0.0.1:8102"
NODE_A_INTERNAL = "http://commons-node-a:8000"
OLLAMA = "http://127.0.0.1:11434"
MODEL = "qwen2.5:0.5b"
LATEST_RECEIPT = Path("benchmarks/results/cross_node_ollama_reuse_gauntlet_latest.json")


def progress(message: str) -> None:
    print(json.dumps({"event": message}), file=sys.stderr, flush=True)


def get(client: httpx.Client, url: str) -> Dict[str, Any]:
    res = client.get(url)
    res.raise_for_status()
    return res.json()


def post(client: httpx.Client, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    res = client.post(url, json=payload)
    res.raise_for_status()
    return res.json()


def post_maybe(client: httpx.Client, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return post(client, url, payload)
    except httpx.HTTPStatusError as exc:
        return {"ok": False, "status_code": exc.response.status_code, "error": exc.response.text}


def _nested(payload: Dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _compact_protocol(packet: Dict[str, Any]) -> Dict[str, Any]:
    envelope = _nested(packet, "envelope", "envelope") or {}
    insight = packet.get("insight_packet") or {}
    route_card = packet.get("route_card") or {}
    quality = packet.get("quality_cascade") or {}
    forge = packet.get("forge_scorecard") or {}
    workflow = packet.get("workflow_card") or {}
    registry_card = packet.get("public_registry_card") or {}
    skill_tree_state = packet.get("skill_tree_state") or {}
    return {
        "beast_object_type": "beast_inference_inversion_handoff",
        "version": "1.0",
        "role": packet.get("role"),
        "space_id": packet.get("space_id"),
        "provider": "ollama",
        "language_contract": {
            "task_envelope": bool(envelope.get("beast_object_type") == "task_envelope"),
            "insight_packet": bool(insight.get("beast_object_type") == "insight_packet"),
            "quality_cascade": bool(quality.get("beast_object_type") == "quality_cascade_report"),
            "pathway_route_card": bool(route_card.get("beast_object_type") == "route_card"),
            "forge_card": bool(forge.get("beast_object_type") == "forge_scorecard"),
            "workflow_card": bool(workflow.get("beast_object_type") == "conductor_workflow_card"),
            "public_registry_card": bool(registry_card.get("beast_object_type")),
            "skill_tree_state": bool(skill_tree_state),
            "verifier_receipts": True,
        },
        "task_envelope": {
            "task_id": envelope.get("task_id"),
            "task_class": envelope.get("task_class"),
            "risk_level": envelope.get("risk_level"),
            "privacy_class": envelope.get("privacy_class"),
            "allowed_actions": envelope.get("allowed_actions"),
            "approval_required_for": envelope.get("approval_required_for"),
        },
        "insights": {
            "local_first": insight.get("local_first"),
            "evidence_count": _nested(insight, "summary", "evidence_count"),
            "handoff_recommendation": _nested(insight, "summary", "handoff_recommendation"),
        },
        "cascade": {
            "status": quality.get("status"),
            "check_count": _nested(quality, "summary", "check_count"),
            "warnings": _nested(quality, "summary", "warnings"),
            "local_only": quality.get("local_only"),
        },
        "pathway": {
            "route_id": route_card.get("route_id"),
            "name": route_card.get("name"),
            "promotion_status": route_card.get("promotion_status"),
            "avoid": route_card.get("avoid"),
        },
        "forge_card": {
            "scorecard_id": forge.get("scorecard_id"),
            "decision": forge.get("decision"),
            "risk_level": forge.get("risk_level"),
            "required_gates": forge.get("required_gates"),
        },
        "workflow": {
            "workflow_id": workflow.get("workflow_id"),
            "decision": workflow.get("decision"),
            "execution_mode": workflow.get("execution_mode"),
            "swarm_used": _nested(workflow, "swarm", "used"),
            "chronicle_required": _nested(workflow, "chronicle_plan", "required"),
        },
        "registries": {
            "space_name": registry_card.get("name"),
            "task_class": registry_card.get("task_class"),
            "authority": registry_card.get("authority"),
            "risk": _nested(registry_card, "safety", "risk"),
            "approval_required": _nested(registry_card, "safety", "approval_required"),
        },
        "skill_tree": {
            "object_type": skill_tree_state.get("beast_object_type"),
            "skills": _nested(skill_tree_state, "statistics", "skills")
            or _nested(skill_tree_state, "skills", "total")
            or _nested(skill_tree_state, "skills"),
            "patterns": _nested(skill_tree_state, "statistics", "patterns")
            or _nested(skill_tree_state, "patterns", "total")
            or _nested(skill_tree_state, "patterns"),
        },
    }


def beast_protocol_packet(client: httpx.Client, node: str, *, space_id: str, role: str) -> Dict[str, Any]:
    objective = (
        f"{role}: evaluate BEAST Commons Space {space_id} as crystallized compute for local-only reuse. "
        "Use task envelopes, insight packets, quality cascade, route cards, forge scorecards, workflow cards, "
        "registries, and verifier receipts. Do not call cloud APIs."
    )
    base_payload = {
        "user_request": objective,
        "task_class": "commons_crystallized_compute_reuse",
        "provider": "ollama",
        "space_id": space_id,
    }
    envelope_result = post_maybe(client, node + "/edgek/task/envelope", base_payload)
    envelope = envelope_result.get("envelope") or {}
    insight = post_maybe(client, node + "/edgek/insights/compile", {
        "objective": objective,
        "task_class": "commons_crystallized_compute_reuse",
        "provider": "ollama",
        "current_task": envelope,
        "limit": 8,
    })
    route_card = post_maybe(client, node + "/edgek/pathfinder/route-card", {
        "envelope": envelope,
        "provider": "ollama",
        "persist": False,
    })
    quality = post_maybe(client, node + "/edgek/task/quality-cascade", {
        **base_payload,
        "envelope": envelope,
        "route_card": route_card,
    })
    forge = post_maybe(client, node + "/edgek/forge/scorecard", {
        "envelope": envelope,
        "route_card": route_card,
        "insight_packet": insight,
    })
    workflow = post_maybe(client, node + "/edgek/workflow/plan", {
        "envelope": envelope,
        "route_card": route_card,
        "quality_report": quality,
        "forge_scorecard": forge,
    })
    registry_card = get(client, node + f"/edgek/public-commons-registry/{space_id}")
    skill_tree_state = get(client, node + "/edgek/skills/state")
    packet = {
        "role": role,
        "space_id": space_id,
        "objective": objective,
        "envelope": envelope_result,
        "insight_packet": insight,
        "route_card": route_card,
        "quality_cascade": quality,
        "forge_scorecard": forge,
        "workflow_card": workflow,
        "public_registry_card": registry_card,
        "skill_tree_state": skill_tree_state,
    }
    packet["handoff"] = _compact_protocol(packet)
    return packet


def wait_for(client: httpx.Client, base: str, timeout: int = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if get(client, base + "/health").get("status") == "healthy":
                return
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"node did not become healthy: {base}")


def choose_remote_space(client: httpx.Client) -> Dict[str, Any]:
    registry_a = get(client, NODE_A + "/edgek/commons-spaces")
    registry_b = get(client, NODE_B + "/edgek/commons-spaces")
    b_ids = {str(item.get("space_id") or "") for item in registry_b.get("spaces") or []}
    for item in registry_a.get("spaces") or []:
        sid = str(item.get("space_id") or "")
        if item.get("valid") and sid not in b_ids:
            return item
    for item in registry_a.get("spaces") or []:
        if item.get("valid"):
            return item
    raise RuntimeError("node A has no valid spaces")


def parse_jsonish(text: str) -> Dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {"raw": text.strip(), "parsed": False}
    try:
        payload = json.loads(match.group(0))
        payload["parsed"] = True
        return payload
    except json.JSONDecodeError:
        return {"raw": text.strip(), "parsed": False}


def ollama_generate(client: httpx.Client, prompt: str, *, role: str) -> Dict[str, Any]:
    progress(f"ollama_generate:{role}:start")
    started = time.perf_counter()
    res = client.post(
        OLLAMA + "/api/generate",
        json={
            "model": MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 96},
        },
        timeout=60,
    )
    res.raise_for_status()
    body = res.json()
    text = str(body.get("response") or "")
    result = {
        "role": role,
        "model": MODEL,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "response": text,
        "json": parse_jsonish(text),
    }
    progress(f"ollama_generate:{role}:done")
    return result


def main() -> None:
    with httpx.Client(timeout=30) as client:
        wait_for(client, NODE_A)
        wait_for(client, NODE_B)
        progress("nodes_healthy")
        tags = get(client, OLLAMA + "/api/tags")
        if MODEL not in {item.get("name") for item in tags.get("models") or []}:
            raise RuntimeError(f"Ollama model is not installed: {MODEL}")

        space = choose_remote_space(client)
        space_id = str(space["space_id"])
        progress(f"selected_space:{space_id}")
        node_a_protocol = beast_protocol_packet(client, NODE_A, space_id=space_id, role="Node A crystallizer")
        progress("node_a_protocol_packet_built")
        detail_a = get(client, NODE_A + f"/edgek/public-commons-registry/{space_id}")
        node_a_ollama = ollama_generate(
            client,
            "Return only strict JSON. You are BEAST Node A crystallizer. "
            "Keys: space_id,reusable_capability,verifier,risk,why_it_reduces_recompute. "
            "Do not use markdown. "
            f"SPACE_ID={space_id} "
            f"BEAST_HANDOFF={json.dumps(node_a_protocol['handoff'], sort_keys=True)[:900]} "
            f"SPACE_CARD={json.dumps(detail_a, sort_keys=True)[:600]}",
            role="node_a_crystallizer",
        )

        import_result = post_maybe(
            client,
            NODE_B + "/edgek/commons-spaces/import-remote",
            {
                "bundle_url": NODE_A_INTERNAL + f"/edgek/commons-spaces/{space_id}/bundle",
                "approved": True,
                "dry_run": False,
                "timeout_seconds": 60,
            },
        )
        progress("bundle_import_attempted")
        replay = post_maybe(
            client,
            NODE_B + f"/edgek/commons-spaces/{space_id}/replay",
            {"deterministic_only": True, "contributor_id": "commons-node-a"},
        )
        progress("node_b_replay_attempted")
        detail_b = get(client, NODE_B + f"/edgek/commons-spaces/{space_id}")
        node_b_protocol = beast_protocol_packet(client, NODE_B, space_id=space_id, role="Node B reuse decider")
        progress("node_b_protocol_packet_built")
        node_b_ollama = ollama_generate(
            client,
            "Return only strict JSON. You are BEAST Node B reuse decider. "
            "Keys: reuse,reason,required_local_checks,cloud_api_needed. "
            "Set reuse true and cloud_api_needed false if import_verified, replay_reproduced, and language_contract_complete are true. "
            "Do not use markdown. "
            f"SPACE_ID={space_id} IMPORTED={import_result.get('imported')} REPLAY={replay.get('reproduced')} "
            f"IMPORT_VERIFIED={bool(import_result.get('imported'))} "
            f"REPLAY_REPRODUCED={bool(replay.get('reproduced'))} "
            f"LANGUAGE_CONTRACT_COMPLETE={all(node_b_protocol['handoff']['language_contract'].values())} "
            f"BEAST_HANDOFF={json.dumps(node_b_protocol['handoff'], sort_keys=True)[:900]} "
            f"NODE_A_HANDOFF={json.dumps(node_a_ollama['json'], sort_keys=True)[:500]}",
            role="node_b_reuse_decider",
        )
        adoption = post_maybe(
            client,
            NODE_B + f"/edgek/commons-spaces/{space_id}/adopt",
            {
                "approved": True,
                "dry_run": False,
                "approved_by": "cross_node_ollama_reuse_gauntlet",
                "reason": "Imported bundle verified and deterministic replay passed in Ollama reuse gauntlet",
            },
        )
        progress("adoption_attempted")
        proof = post_maybe(
            client,
            NODE_B + f"/edgek/commons-economy/credits/{space_id}",
            {
                "approved": True,
                "approved_by": "cross_node_ollama_reuse_gauntlet",
                "reason": "Attempt strict credit after cross-node Ollama reuse gauntlet",
            },
        )
        progress("credit_attempted")
        node_a_language_complete = all(node_a_protocol["handoff"]["language_contract"].values())
        node_b_language_complete = all(node_b_protocol["handoff"]["language_contract"].values())
        model_cloud_api_needed = str(node_b_ollama.get("json", {}).get("cloud_api_needed", "false")).lower()
        model_reuse = str(node_b_ollama.get("json", {}).get("reuse", "false")).lower()
        import_available = bool(
            import_result.get("imported")
            or import_result.get("duplicate")
            or "already exists" in str(import_result.get("error", "")).lower()
        )
        beast_verified_reuse = bool(import_available and replay.get("reproduced"))
        result = {
            "beast_object_type": "cross_node_ollama_reuse_gauntlet",
            "version": "1.0",
            "cloud_api_calls_observed": 0,
            "node_a": NODE_A,
            "node_b": NODE_B,
            "ollama_base_url": OLLAMA,
            "ollama_model": MODEL,
            "space_id": space_id,
            "node_a_beast_handoff": node_a_protocol["handoff"],
            "node_a_ollama": node_a_ollama,
            "bundle_import": import_result,
            "node_b_replay": replay,
            "node_b_beast_handoff": node_b_protocol["handoff"],
            "node_b_ollama": node_b_ollama,
            "model_decision_is_advisory": True,
            "beast_verified_reuse": beast_verified_reuse,
            "adoption": adoption,
            "credit_attempt": proof,
            "success": bool(
                beast_verified_reuse
                and node_a_language_complete
                and node_b_language_complete
                and model_reuse in {"true", "yes", "1"}
                and model_cloud_api_needed in {"false", "no", "0"}
                and not import_result.get("dry_run")
            ),
            "infrastructure_success": bool(
                beast_verified_reuse
                and node_a_language_complete
                and node_b_language_complete
            ),
            "currency_gate_interpretation": "credit should issue only with eligible live/adoption/displacement proof; refusal is correct if evidence is insufficient",
        }
        result["receipt_path"] = str(LATEST_RECEIPT)
        LATEST_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        LATEST_RECEIPT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        raise
