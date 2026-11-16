"""IDE model/provider inventory for the governed router (2026-11-16).

Lists real lanes: Auto (BEAST governed), live TGI/Ollama, and provider/HF lanes
whose key is present (checked by env-var *name* or dotenv presence only).
Never returns key values, headers, prompts, or raw credentials.
Scorecard rankings are attached per task family when evidence exists.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import httpx

from app.kernel.compute.capability_scorecard import CapabilityScorecard, DEFAULT_PATH as SCORECARD_PATH
from app.kernel.compute.governed_client import (
    Candidate,
    GovernedModelClient,
    default_candidates,
    dotenv_value,
    provider_lane_candidates,
    hf_router_candidates,
    tgi_available,
    TGI_DEFAULT_BASE,
    PROVIDER_SECRETS_ENV,
)

AUTO_ID = "auto"
AUTO_PROVIDER = "beast"
LOCAL_PROVIDERS = {"ollama", "local_ollama", "tgi", "llama_cpp"}


FAMILY_ALIASES = {
    "rename": "refactor-rename-symbol",
    "refactor-rename": "refactor-rename-symbol",
    "symbol-rename": "refactor-rename-symbol",
    "refguard": "composite-refguard",
    "reference-guard": "composite-refguard",
    "composite_refguard": "composite-refguard",
}

# Recorded 2026-11-16 provider-gauntlet HTTP 402/403 auth or billing blocks.
# Credential *names* may still be present; lanes stay visible and selectable,
# but Auto will not pick a blocked account.
PROVIDER_ACCOUNT_BLOCKS: Dict[str, Dict[str, Any]] = {
    "sambanova": {"http_status": 402, "reason": "payment_method_required", "recorded": "2026-11-16"},
    "hyperbolic": {"http_status": 403, "reason": "inference_requires_verified_phone", "recorded": "2026-11-16"},
    "replicate": {"http_status": 402, "reason": "insufficient_credit", "recorded": "2026-11-16"},
    "fal": {"http_status": 403, "reason": "exhausted_balance", "recorded": "2026-11-16"},
    "fal_llm": {"http_status": 403, "reason": "exhausted_balance", "recorded": "2026-11-16"},
    "fal_media": {"http_status": 403, "reason": "exhausted_balance", "recorded": "2026-11-16"},
}


def normalize_family(family: str) -> str:
    raw = str(family or "").strip() or "rename"
    return FAMILY_ALIASES.get(raw, FAMILY_ALIASES.get(raw.lower(), raw))


def _account_block(provider: str) -> Optional[Dict[str, Any]]:
    return PROVIDER_ACCOUNT_BLOCKS.get(str(provider or "").strip().lower())


def _blocked_status(block: Mapping[str, Any]) -> str:
    code = block.get("http_status")
    reason = block.get("reason") or "account_blocked"
    return f"Blocked · billing/auth ({code}) · {reason}"


def _lane_ready(cand: Candidate, env: Mapping[str, str]) -> bool:
    """True when a candidate can be offered. Local lanes need no key. Others need a named secret present."""
    if cand.provider in LOCAL_PROVIDERS and not cand.key_env and not cand.key_file:
        return True
    if cand.key_env and env.get(cand.key_env):
        return True
    dotenv = cand.key_dotenv or PROVIDER_SECRETS_ENV
    if cand.key_env and dotenv and dotenv_value(dotenv, cand.key_env):
        return True
    if cand.key_file:
        try:
            return Path(cand.key_file).expanduser().is_file()
        except OSError:
            return False
    return False


def _short_model(model: str) -> str:
    name = str(model or "").strip()
    if "models/" in name:
        name = name.rsplit("models/", 1)[-1]
    if "/" in name and not name.startswith("accounts/"):
        name = name.split("/")[-1]
    return name or model


def _route_id(provider: str, model: str) -> str:
    return f"{provider}::{model}"


def _ollama_live(base_url: str, *, timeout: float = 1.2) -> tuple[bool, List[Dict[str, Any]]]:
    try:
        with httpx.Client(trust_env=False, timeout=timeout) as client:
            response = client.get(base_url.rstrip("/") + "/api/tags")
            if response.status_code != 200:
                return False, []
            rows = []
            for item in (response.json() or {}).get("models") or []:
                name = str(item.get("name") or item.get("model") or "").strip()
                if not name:
                    continue
                details = item.get("details") if isinstance(item.get("details"), dict) else {}
                rows.append({
                    "name": name,
                    "size": item.get("size"),
                    "quantization": details.get("quantization_level") or "",
                    "family": details.get("family") or "",
                })
            return True, rows
    except (httpx.HTTPError, ValueError, json.JSONDecodeError, OSError):
        return False, []


def _tgi_live_model(base_url: str, *, timeout: float = 1.2) -> tuple[bool, str]:
    if not tgi_available(base_url, timeout=timeout):
        return False, ""
    model = "tgi"
    try:
        with httpx.Client(trust_env=False, timeout=timeout) as client:
            models = client.get(base_url.rstrip("/") + "/v1/models")
            if models.status_code == 200:
                payload = models.json() or {}
                entries = payload.get("data") or payload.get("models") or []
                if entries:
                    first = entries[0] if isinstance(entries[0], dict) else {}
                    model = str(first.get("id") or first.get("name") or model)
                    return True, model
            info = client.get(base_url.rstrip("/") + "/info")
            if info.status_code == 200:
                payload = info.json() or {}
                model = str(payload.get("model_id") or payload.get("id") or payload.get("model") or model)
    except (httpx.HTTPError, ValueError, json.JSONDecodeError, OSError):
        pass
    return True, model


def _load_scorecard(path: str | Path | None = None) -> CapabilityScorecard:
    target = Path(path) if path is not None else SCORECARD_PATH
    card = CapabilityScorecard(target, persist=False)
    if target.exists():
        try:
            card.load()
        except (OSError, ValueError, json.JSONDecodeError, TypeError):
            card.cells = {}
    return card


def _family_ranks(candidates: Sequence[Candidate], scorecard: CapabilityScorecard) -> Dict[str, List[Dict[str, Any]]]:
    families = sorted({
        row["family"] for row in scorecard.snapshot().get("cells") or []
        if row.get("family") and row["family"] != "*" and not str(row["family"]).startswith("smoke")
    })
    ranks: Dict[str, List[Dict[str, Any]]] = {}
    rows = [{"provider": c.provider, "model": c.model, "placement": c.placement or "cloud"} for c in candidates]
    for family in families:
        ranked = scorecard.rank(rows, family, consume_cooldown=False)
        ranks[family] = []
        for index, item in enumerate(ranked, start=1):
            score = item.get("score") or {}
            if float(score.get("attempts") or 0) < 0.5 and score.get("source") == "prior":
                continue
            ranks[family].append({
                "rank": index,
                "provider": item.get("provider"),
                "model": item.get("model"),
                "placement": item.get("placement") or "cloud",
                "pass_rate": score.get("pass_rate"),
                "json_rate": score.get("json_rate"),
                "attempts": score.get("attempts"),
                "value": score.get("value"),
            })
    return ranks


def _attach_families(provider: str, model: str, ranks: Mapping[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    families: Dict[str, Any] = {}
    best_for: List[str] = []
    for family, rows in ranks.items():
        match = next((row for row in rows if row.get("provider") == provider and row.get("model") == model), None)
        if not match:
            continue
        families[family] = {
            "rank": match["rank"],
            "pass_rate": match.get("pass_rate"),
            "json_rate": match.get("json_rate"),
            "attempts": match.get("attempts"),
        }
        if match["rank"] == 1:
            best_for.append(family)
    return {"families": families, "best_for": best_for}


def _auto_row(ranks: Mapping[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    leaders = {}
    for family, rows in ranks.items():
        if not rows:
            continue
        top = rows[0]
        leaders[family] = {
            "rank": 1,
            "provider": top.get("provider"),
            "model": top.get("model"),
            "pass_rate": top.get("pass_rate"),
        }
    return {
        "id": AUTO_ID,
        "model": AUTO_ID,
        "provider": AUTO_PROVIDER,
        "label": "Auto (BEAST governed)",
        "role": "Capability router picks the best available lane per task family",
        "status": "Default route",
        "runtime": "BEAST governed",
        "selectable": True,
        "configured": True,
        "reachable": True,
        "governed_auto": True,
        "installed": False,
        "live": None,
        "confidence": 0,
        "latency": "routed per call",
        "speed": "n/a",
        "size": "",
        "context": "n/a",
        "quantization": "",
        "placement": "",
        "key_env": "",
        "families": leaders,
        "best_for": list(leaders),
    }


def _candidate_row(cand: Candidate, *, live: Optional[bool], status: str, role: str,
                   extra: Optional[Dict[str, Any]] = None,
                   ranks: Optional[Mapping[str, List[Dict[str, Any]]]] = None) -> Dict[str, Any]:
    scored = _attach_families(cand.provider, cand.model, ranks or {})
    best_rate = 0.0
    for info in scored["families"].values():
        try:
            best_rate = max(best_rate, float(info.get("pass_rate") or 0))
        except (TypeError, ValueError):
            pass
    row = {
        "id": _route_id(cand.provider, cand.model),
        "model": cand.model,
        "provider": cand.provider,
        "label": f"{_short_model(cand.model)} · {cand.provider}",
        "role": role,
        "status": status,
        "runtime": cand.kind or cand.provider,
        "selectable": True,
        "configured": True,
        "reachable": live is not False,
        "governed_auto": False,
        "installed": bool(live) if cand.provider in LOCAL_PROVIDERS else False,
        "live": live,
        "confidence": int(round(best_rate * 100)) if best_rate else 0,
        "latency": "n/a",
        "speed": "n/a",
        "size": "",
        "context": "n/a",
        "quantization": "",
        "placement": cand.placement or ("gpu_full" if cand.provider in LOCAL_PROVIDERS else "cloud"),
        "key_env": cand.key_env or "",
        "usd_per_mtok_in": cand.usd_per_mtok_in,
        "usd_per_mtok_out": cand.usd_per_mtok_out,
        **scored,
    }
    if extra:
        row.update(extra)
    return row


def build_inventory(*, env: Mapping[str, str] | None = None, probe_live: bool = True) -> Dict[str, Any]:
    """Return a redacted, selectable lane inventory for the IDE pickers."""
    env = os.environ if env is None else env
    ollama_base = str(env.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434")
    tgi_base = str(env.get("TGI_BASE_URL") or TGI_DEFAULT_BASE).rstrip("/")
    ollama_up, ollama_rows = _ollama_live(ollama_base) if probe_live else (False, [])
    tgi_up, tgi_model = _tgi_live_model(tgi_base) if probe_live else (False, "")
    live_ollama = {row["name"] for row in ollama_rows}

    # Discover credentialed + local candidates without probing TGI twice.
    discovered = [c for c in default_candidates(env, probe_tgi=False) if _lane_ready(c, env)]
    scorecard = _load_scorecard()
    # Rank the union of discovered + live local models.
    rank_cands: List[Candidate] = list(discovered)
    if tgi_up and not any(c.provider == "tgi" for c in rank_cands):
        rank_cands.append(Candidate(provider="tgi", model=tgi_model or "tgi", kind="tgi",
                                    base_url=tgi_base + "/v1", placement="gpu_full"))
    for row in ollama_rows:
        if not any(c.provider == "ollama" and c.model == row["name"] for c in rank_cands):
            rank_cands.append(Candidate(provider="ollama", model=row["name"], kind="ollama",
                                        base_url=ollama_base, placement="gpu_full"))
    ranks = _family_ranks(rank_cands, scorecard)

    registry: List[Dict[str, Any]] = [_auto_row(ranks)]
    seen: set[str] = {AUTO_ID}

    if tgi_up:
        cand = next((c for c in discovered if c.provider == "tgi"), None)
        model = tgi_model or (cand.model if cand else "tgi")
        tgi_cand = Candidate(provider="tgi", model=model, kind="tgi",
                             base_url=tgi_base + "/v1", placement="gpu_full")
        row = _candidate_row(tgi_cand, live=True, status="Live · local TGI",
                             role="Local TGI", ranks=ranks,
                             extra={"size": "local GPU", "runtime": "TGI"})
        registry.append(row)
        seen.add(row["id"])

    for item in ollama_rows:
        cand = Candidate(provider="ollama", model=item["name"], kind="ollama",
                         base_url=ollama_base, placement="gpu_full")
        row = _candidate_row(cand, live=True, status="Live · local Ollama",
                             role="Local Ollama", ranks=ranks,
                             extra={"size": str(item.get("size") or ""),
                                    "quantization": str(item.get("quantization") or ""),
                                    "runtime": "Ollama"})
        if row["id"] not in seen:
            registry.append(row)
            seen.add(row["id"])

    for cand in discovered:
        if cand.provider in {"ollama", "local_ollama", "tgi"}:
            # Live locals already added; skip stale hardcoded names that are not installed.
            continue
        block = _account_block(cand.provider)
        extra = {"runtime": cand.kind or cand.provider, "size": "remote"}
        if block:
            extra["blocked"] = True
            extra["block"] = dict(block)
        row = _candidate_row(
            cand, live=None if not block else False,
            status=_blocked_status(block) if block else "Credentials ready · inference unverified",
            role="Configured lane",
            ranks=ranks,
            extra=extra,
        )
        if row["id"] not in seen:
            registry.append(row)
            seen.add(row["id"])

    providers_present = sorted({
        row["provider"] for row in registry if row["provider"] and row["provider"] != AUTO_PROVIDER
    })
    families = sorted(ranks)
    return {
        "beast_object_type": "ide_model_inventory",
        "generated_at": time.time(),
        "default_id": AUTO_ID,
        "default_label": "Auto (BEAST governed)",
        "policy": "Auto (BEAST governed) uses the capability router; explicit picks pin one lane through the governed path.",
        "live": {
            "tgi": {"up": tgi_up, "base_url": tgi_base, "model": tgi_model or ""},
            "ollama": {"up": ollama_up, "base_url": ollama_base, "models": sorted(live_ollama)},
        },
        "providers_present": providers_present,
        "blocked_providers": sorted({
            name for name in PROVIDER_ACCOUNT_BLOCKS
            if name in {row["provider"] for row in registry}
        }),
        "families": families,
        "family_leaders": {
            family: {
                "provider": rows[0]["provider"],
                "model": rows[0]["model"],
                "pass_rate": rows[0].get("pass_rate"),
            }
            for family, rows in ranks.items() if rows
        },
        "scorecard_cells": len(scorecard.cells),
        "registry": registry,
        "count": len(registry),
    }


def resolve_route(payload: Mapping[str, Any] | None = None, *, env: Mapping[str, str] | None = None,
                  probe_live: bool = True) -> Dict[str, Any]:
    """Resolve Auto or an explicit picker id to a concrete candidate (no call)."""
    payload = payload or {}
    inventory = build_inventory(env=env, probe_live=probe_live)
    requested_id = str(payload.get("id") or payload.get("route_id") or "").strip()
    requested_model = str(payload.get("model") or "").strip()
    requested_provider = str(payload.get("provider") or "").strip()
    family = normalize_family(payload.get("family") or "rename")
    auto = (
        payload.get("governed_auto") is True
        or requested_id in {AUTO_ID, "beast-auto", ""}
        or requested_model in {AUTO_ID, "beast-auto", ""}
        or requested_provider in {AUTO_PROVIDER, ""}
    ) and not (requested_id and requested_id not in {AUTO_ID, "beast-auto"} and "::" in requested_id)

    if requested_id and requested_id not in {AUTO_ID, "beast-auto"}:
        auto = False
    if requested_provider and requested_provider not in {AUTO_PROVIDER, ""} and requested_model not in {AUTO_ID, "beast-auto", ""}:
        auto = False

    registry = inventory["registry"]
    selected = None
    if not auto:
        for row in registry:
            if requested_id and row["id"] == requested_id:
                selected = row
                break
            if requested_provider and requested_model and row["provider"] == requested_provider and row["model"] == requested_model:
                selected = row
                break
            if not requested_provider and requested_model and row["model"] == requested_model:
                selected = row
                break
        if selected is None:
            return {"ok": False, "error": "requested route is not in the available inventory",
                    "requested": {"id": requested_id, "provider": requested_provider, "model": requested_model},
                    "resolved": None}, None

    env = os.environ if env is None else env
    cands = [c for c in default_candidates(env, probe_tgi=probe_live) if _lane_ready(c, env)]
    # Include live ollama models not in the hardcoded defaults.
    ollama_base = str(env.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434")
    for name in inventory.get("live", {}).get("ollama", {}).get("models") or []:
        if not any(c.provider == "ollama" and c.model == name for c in cands):
            cands.append(Candidate(provider="ollama", model=name, kind="ollama",
                                   base_url=ollama_base, placement="gpu_full"))
    tgi_info = inventory.get("live", {}).get("tgi") or {}
    if tgi_info.get("up") and not any(c.provider == "tgi" for c in cands):
        cands.append(Candidate(provider="tgi", model=tgi_info.get("model") or "tgi", kind="tgi",
                               base_url=str(tgi_info.get("base_url") or TGI_DEFAULT_BASE).rstrip("/") + "/v1",
                               placement="gpu_full"))

    if not auto and selected:
        pinned = [c for c in cands if c.provider == selected["provider"] and (
            c.model == selected["model"] or c.model == "tgi" and selected["provider"] == "tgi"
        )]
        if not pinned and selected["provider"] == "tgi":
            pinned = [c for c in cands if c.provider == "tgi"]
        if not pinned:
            return {"ok": False, "error": "requested lane has no governed candidate",
                    "requested": {"id": selected["id"], "provider": selected["provider"], "model": selected["model"]},
                    "resolved": None}, None
        cands = pinned

    if auto:
        unblocked = [c for c in cands if _account_block(c.provider) is None]
        if unblocked:
            cands = unblocked
    scorecard = _load_scorecard()
    ranked = scorecard.rank(
        [{"provider": c.provider, "model": c.model, "placement": c.placement or "cloud", "_cand": c} for c in cands],
        family, consume_cooldown=False,
    ) if cands else []
    winner = ranked[0] if ranked else None
    cand: Optional[Candidate] = winner.get("_cand") if winner else (cands[0] if cands else None)
    if cand is None:
        return {"ok": False, "error": "no governed candidates are currently available",
                "requested": {"id": requested_id, "provider": requested_provider, "model": requested_model, "auto": auto},
                "resolved": None}, None
    return {
        "ok": True,
        "requested": {
            "id": requested_id or (AUTO_ID if auto else selected["id"] if selected else ""),
            "provider": requested_provider or (AUTO_PROVIDER if auto else ""),
            "model": requested_model or (AUTO_ID if auto else ""),
            "auto": auto,
            "family": family,
        },
        "resolved": {
            "id": _route_id(cand.provider, cand.model),
            "provider": cand.provider,
            "model": cand.model,
            "placement": cand.placement or "",
            "kind": cand.kind,
            "via": "capability_router" if auto else "explicit_pin",
            "family": family,
            "score": (winner or {}).get("score") if winner else None,
            "blocked": bool(_account_block(cand.provider)),
            "block": _account_block(cand.provider),
        },
        "inventory_count": inventory.get("count"),
    }, cand


async def resolve_and_optionally_call(payload: Mapping[str, Any] | None = None, *,
                                      env: Mapping[str, str] | None = None) -> Dict[str, Any]:
    """Resolve a picker selection and, for local lanes only, make one cheap governed call.

    Paid providers are resolved but not called from this probe (spend cap).
    Receipts never include prompts, outputs, keys, or headers.
    """
    payload = dict(payload or {})
    want_call = bool(payload.get("call"))
    resolved, cand = resolve_route(payload, env=env, probe_live=True)
    if not resolved.get("ok"):
        return resolved
    result = {
        "ok": True,
        "requested": resolved["requested"],
        "resolved": resolved["resolved"],
        "called": False,
        "spend_usd": 0.0,
        "latency_ms": None,
        "call_status": "",
        "error": "",
    }
    if not want_call or cand is None:
        return result
    if cand.provider not in LOCAL_PROVIDERS:
        result["call_status"] = "skipped_non_local"
        result["error"] = "Live probe only calls local TGI/Ollama so spend stays at zero."
        return result

    from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog

    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    scorecard = CapabilityScorecard(persist=False)
    client = GovernedModelClient(
        [cand],
        scorecard=scorecard,
        governor=ComputeGovernorSpine(receipts=GovernorReceiptLog(None), enforce=False),
        use_scorecard=False,
        max_attempts=1,
        feedback_turns=False,
    )
    # Bound the cheap probe at the candidate so we cannot emit a long completion.
    cand.max_tokens = min(int(cand.max_tokens or 16), 16)
    started = time.time()
    try:
        outcome = await client.complete(
            family="smoke-ide-route",
            messages=[{"role": "user", "content": 'Reply with JSON {"ok": true} and nothing else.'}],
            schema=schema,
            verify=lambda value: {"passed": isinstance(value, dict) and value.get("ok") is True},
            run_id="ide-model-route-probe",
        )
    except Exception as exc:  # noqa: BLE001 — probe must never raise into the IDE
        result["call_status"] = "error"
        result["error"] = str(exc.__class__.__name__)
        result["latency_ms"] = round((time.time() - started) * 1000, 1)
        return result
    call = outcome.calls[0] if outcome.calls else None
    result["called"] = True
    result["latency_ms"] = round((time.time() - started) * 1000, 1)
    result["call_status"] = getattr(call, "status", "") if call else ("accepted" if outcome.accepted else "no_call")
    result["accepted"] = bool(outcome.accepted)
    result["called_provider"] = cand.provider
    result["called_model"] = cand.model
    if call is not None:
        result["spend_usd"] = float(getattr(call, "spend_usd", 0.0) or 0.0)
    # Confirm the lane that ran matches the resolved pin/router choice.
    result["matches_resolved"] = (
        result.get("called_provider") == resolved["resolved"]["provider"]
        and result.get("called_model") == resolved["resolved"]["model"]
    )
    return result


__all__ = [
    "AUTO_ID",
    "AUTO_PROVIDER",
    "build_inventory",
    "resolve_route",
    "resolve_and_optionally_call",
]


def resolve_route_public(payload=None, *, env=None, probe_live=True):
    public, _cand = resolve_route(payload, env=env, probe_live=probe_live)
    return public
