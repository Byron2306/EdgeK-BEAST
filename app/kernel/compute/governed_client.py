"""One governed client for every BEAST model call (steps 1-6 of governed interception).

    intercept -> avoid -> shrink -> constrain -> stream -> verify & learn

* **Intercept**: proxy requests (``execute.py`` behind ``BEAST_GOVERNED_INTERCEPTION``)
  and internal callers (gauntlets, planners, specialists) call
  ``GovernedModelClient.complete`` instead of raw httpx.
* **Avoid**: an ``avoid`` hook (crystal / lattice lookup, D9 router) runs first;
  a verified hit returns with zero model calls.
* **Shrink**: candidates are ranked cheapest-capable first by the capability
  scorecard (``BEAST_CAPABILITY_ROUTER``), with a hard per-call output budget
  sized for reasoning models and an episode token budget enforced by the
  governor (``budget_exhausted`` -> DEFER).
* **Constrain**: request bodies force the action JSON schema in each
  provider's decoder dialect (``constrained_output``), with dialect fallback on
  400 and thinking disabled for reasoning models.
* **Stream**: every call streams; ``JsonStreamGate`` stops generation as soon
  as a complete schema-valid action has arrived, and cuts stalls / runaway
  prose.  Stalled local generations are torn down via the lifecycle layer
  (owned processes) or unloaded via the Ollama API (system daemon).
* **Verify & learn**: the caller's verifier decides; the outcome updates the
  scorecard (per provider/model/family/placement), the per-candidate circuit
  breaker, and appends a hash-chained ``model_call`` receipt to the governor
  log.  Receipts never contain prompts, outputs, headers or credentials, and
  every error string is redacted.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional, Sequence

import httpx

from app.kernel.compute.capability_scorecard import CapabilityScorecard
from app.kernel.compute.constrained_output import constrain_body, dialects_for, strip_unsupported
from app.kernel.compute.json_stream_gate import JsonStreamGate

SECRET_PATTERNS = re.compile(r"(nvapi-[A-Za-z0-9_\-]{8,}|hf_[A-Za-z0-9]{8,}|sk-[A-Za-z0-9_\-]{8,}|gsk_[A-Za-z0-9]{8,}|"
                             r"r8_[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_\-]{20,}|Bearer\s+[A-Za-z0-9._\-]{8,})")


def enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get("BEAST_GOVERNED_INTERCEPTION", "0")).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Candidate:
    provider: str                     # scorecard / breaker identity, e.g. "nim", "ollama", "hf", "tgi"
    model: str
    kind: str                         # wire dialect: ollama | nim | hf_router | openai | tgi | vllm
    base_url: str
    key_env: str = ""                 # env var NAME holding the credential (never the value)
    key_file: str = ""                # optional path holding the credential (e.g. ~/.cache/huggingface/token)
    auth_scheme: str = "Bearer"       # Authorization scheme (fal uses "Key")
    key_dotenv: str = ""              # optional dotenv file to read ``key_env`` from (e.g. .beast/provider_secrets.env)
    placement: str = "cloud"
    max_tokens: int = 1024
    timeout_s: float = 90.0
    ttft_timeout_s: float = 60.0      # first-token deadline (model load / queueing)
    stall_timeout_s: float = 20.0     # max gap between streamed chunks once started
    rung: str = "cloud"               # governor rung: local_specialist | cloud
    options: Dict[str, Any] = field(default_factory=dict)  # extra body fields (e.g. ollama options)
    usd_per_mtok_in: float = 0.0
    usd_per_mtok_out: float = 0.0

    @property
    def ident(self) -> str:
        return f"{self.provider}:{self.model}@{self.placement}"


class CircuitBreaker:
    def __init__(self, *, open_after: int = 2, cooldown_s: float = 120.0, clock: Callable[[], float] = time.monotonic):
        self.open_after, self.cooldown_s, self.clock = open_after, cooldown_s, clock
        self.failures: Dict[str, int] = {}
        self.opened_at: Dict[str, float] = {}

    def state(self, ident: str) -> Dict[str, Any]:
        opened = self.opened_at.get(ident)
        if opened is None:
            return {"state": "closed", "failures": self.failures.get(ident, 0)}
        if self.clock() - opened >= self.cooldown_s:
            return {"state": "half_open", "failures": self.failures.get(ident, 0)}
        return {"state": "open", "failures": self.failures.get(ident, 0)}

    def record(self, ident: str, ok: bool, *, transport_failure: bool) -> None:
        if ok:
            self.failures[ident] = 0
            self.opened_at.pop(ident, None)
            return
        if not transport_failure:
            return  # verifier rejections teach the scorecard; they do not trip the transport breaker
        self.failures[ident] = self.failures.get(ident, 0) + 1
        if self.failures[ident] >= self.open_after or self.state(ident)["state"] == "half_open":
            self.opened_at[ident] = self.clock()


def redact(text: Any, extra_values: Sequence[str] = ()) -> str:
    out = str(text or "")
    for value in extra_values:
        if value and len(value) >= 6:
            out = out.replace(value, "[REDACTED]")
    return SECRET_PATTERNS.sub("[REDACTED]", out)


@dataclass
class CallOutcome:
    candidate: Candidate
    status: str                       # ok | http_error | transport_error | stream_stall | runaway | json_invalid | verifier_reject | skipped_circuit_open | refused_governor
    json_valid: bool = False
    value: Any = None
    verify: Dict[str, Any] = field(default_factory=dict)
    dialect: str = ""
    early_stop: bool = False
    stop_reason: str = ""
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tokens_estimated: bool = False
    budget_headroom_tokens: int = 0   # max_tokens - completion tokens when stopped early (upper bound on saving)
    ttft_ms: float = 0.0
    latency_ms: float = 0.0
    spend_usd: float = 0.0
    error: str = ""
    receipt_id: str = ""
    governor_receipt: str = ""
    teardown: Dict[str, Any] = field(default_factory=dict)
    stream_observation: Dict[str, Any] = field(default_factory=dict)

    def public(self) -> Dict[str, Any]:
        return {"provider": self.candidate.provider, "model": self.candidate.model, "placement": self.candidate.placement,
                "status": self.status, "json_valid": self.json_valid, "passed": bool(self.verify.get("passed")),
                "verify_reason": self.verify.get("reason", ""), "dialect": self.dialect, "early_stop": self.early_stop,
                "stop_reason": self.stop_reason, "tokens_prompt": self.tokens_prompt,
                "tokens_completion": self.tokens_completion, "tokens_estimated": self.tokens_estimated,
                "budget_headroom_tokens": self.budget_headroom_tokens, "ttft_ms": round(self.ttft_ms, 1),
                "latency_ms": round(self.latency_ms, 1), "spend_usd": round(self.spend_usd, 6), "error": self.error,
                "receipt_id": self.receipt_id, "governor_receipt": self.governor_receipt, "teardown": self.teardown}


@dataclass
class GovernedResult:
    accepted: bool
    value: Any = None
    accepted_by: str = ""
    avoided: bool = False
    calls: List[CallOutcome] = field(default_factory=list)
    ranking: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""

    def public(self) -> Dict[str, Any]:
        return {"accepted": self.accepted, "accepted_by": self.accepted_by, "avoided": self.avoided, "reason": self.reason,
                "model_calls": len([c for c in self.calls if c.status not in {"skipped_circuit_open", "refused_governor"}]),
                "calls": [c.public() for c in self.calls],
                "ranking": [{"ident": f"{r['provider']}:{r['model']}@{r.get('placement', 'cloud')}", **r["score"]} for r in self.ranking]}


Verifier = Callable[[Any], Dict[str, Any] | Awaitable[Dict[str, Any]]]
AvoidHook = Callable[[str, List[Dict[str, str]]], Optional[Dict[str, Any]]]


class GovernedModelClient:
    def __init__(self, candidates: Sequence[Candidate], *, scorecard: CapabilityScorecard | None = None,
                 governor: Any = None, breaker: CircuitBreaker | None = None,
                 transport: httpx.AsyncBaseTransport | None = None, avoid: AvoidHook | None = None,
                 lifecycle: Any = None, lifecycle_handles: Mapping[str, Any] | None = None,
                 use_scorecard: bool | None = None, max_attempts: int = 3, episode_token_limit: float | None = None,
                 feedback_turns: bool = True, fixed_stream_dialect: str | None = None,
                 drain_stream: bool = False):
        from app.kernel.compute import capability_scorecard as _cs
        from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog

        self.candidates = list(candidates)
        if fixed_stream_dialect is not None and (
                not self.candidates or any(c.kind != "nim" for c in self.candidates)
                or len({c.ident for c in self.candidates}) != len(self.candidates)
                or len({c.base_url for c in self.candidates}) != 1
                or fixed_stream_dialect not in dialects_for("nim")
                or not 1 <= max_attempts <= len(self.candidates)
                or feedback_turns or avoid is not None or lifecycle is not None or lifecycle_handles):
            raise ValueError("fixed stream ablation requires distinct NIM candidates on one endpoint without feedback, reuse or lifecycle hooks")
        if drain_stream and fixed_stream_dialect is None:
            raise ValueError("drain_stream requires a fixed dialect")
        self.fixed_stream_dialect = fixed_stream_dialect
        self.drain_stream = bool(drain_stream)
        self.scorecard = scorecard if scorecard is not None else CapabilityScorecard()
        self.breaker = breaker or CircuitBreaker()
        self.governor = governor or ComputeGovernorSpine(receipts=GovernorReceiptLog(None), enforce=True)
        if getattr(self.governor, "circuits", None) is None:
            self.governor.circuits = lambda ident: self.breaker.state(ident)
        self.transport = transport
        self.avoid = avoid
        self.lifecycle = lifecycle
        self.lifecycle_handles = dict(lifecycle_handles or {})
        self.use_scorecard = _cs.enabled() if use_scorecard is None else use_scorecard
        self.max_attempts = max(1, int(max_attempts))
        self.episode_token_limit = episode_token_limit
        self.feedback_turns = bool(feedback_turns)
        self._tokens_used = 0.0
        self._signatures: List[str] = []

    # -- credentials (values stay in memory; only names/paths are ever recorded) -------------------
    def _secret(self, cand: Candidate) -> str:
        if cand.key_env and os.environ.get(cand.key_env):
            return os.environ[cand.key_env]
        if cand.key_file:
            try:
                return Path(os.path.expanduser(cand.key_file)).read_text(encoding="utf-8").strip()
            except OSError:
                return ""
        if cand.key_env and cand.key_dotenv:
            return dotenv_value(cand.key_dotenv, cand.key_env)
        return ""

    def _secret_values(self) -> List[str]:
        return [v for v in (self._secret(c) for c in self.candidates) if v]

    # -- governor ---------------------------------------------------------------------------------
    def _proposal(self, cand: Candidate, family: str, run_id: str, attempt: int):
        from app.kernel.governance.governor_spine import Proposal, _sha

        route = None
        if cand.rung == "local_specialist":
            body = {"route": "local_specialist_adapter", "proposal_only": True, "execution_granted": False,
                    "model": cand.model, "family": family}
            route = {**body, "digest": _sha(body)}
        return Proposal(kind=cand.rung, provider=cand.ident, tool_id=f"governed:{cand.provider}:{cand.model}",
                        route_decision=route, quality_cascade={"skipped": "governed-interception:verifier-is-the-gate"},
                        estimate={"tokens_total": float(cand.max_tokens)},
                        signature_material={"family": family, "run": run_id, "attempt": attempt, "model": cand.model})

    def _episode(self, run_id: str):
        from app.kernel.governance.governor_spine import Episode

        limits = {"tokens_total": float(self.episode_token_limit)} if self.episode_token_limit else {}
        return Episode(run_id=run_id, run_budget_used={"tokens_total": self._tokens_used}, limits=limits,
                       signatures=tuple(self._signatures))

    def _receipt(self, body: Dict[str, Any]) -> Dict[str, Any]:
        secrets = self._secret_values()
        clean = json.loads(redact(json.dumps(body, default=str), secrets))
        return self.governor.receipts._append({"type": "model_call", **clean})

    # -- ranking ----------------------------------------------------------------------------------
    def rank(self, family: str) -> List[Dict[str, Any]]:
        rows = [{"provider": c.provider, "model": c.model, "placement": c.placement, "_cand": c} for c in self.candidates]
        if self.use_scorecard:
            ranked = self.scorecard.rank(rows, family)
        else:
            ranked = [{**r, "score": {"value": 0.0, "source": "static_order"}} for r in rows]
        return ranked

    # -- streaming --------------------------------------------------------------------------------
    def _request(self, cand: Candidate, messages: List[Dict[str, str]], schema: Mapping[str, Any], dialect: str,
                 family: str) -> tuple[str, Dict[str, Any], Dict[str, str]]:
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream, application/x-ndjson, application/json"}
        secret = self._secret(cand)
        if secret:
            headers["Authorization"] = f"{cand.auth_scheme or 'Bearer'} {secret}"
        if cand.kind == "ollama":
            url = cand.base_url.rstrip("/") + "/api/chat"
            body = {"model": cand.model, "messages": messages, **{k: v for k, v in cand.options.items() if k != "options"}}
            if cand.options.get("options"):
                body["options"] = dict(cand.options["options"])
        else:
            url = cand.base_url.rstrip("/") + "/chat/completions"
            body = {"model": cand.model, "messages": messages, **cand.options}
        body = constrain_body(cand.kind, body, schema, dialect=dialect, name=f"beast_{family}", max_tokens=cand.max_tokens)
        return url, body, headers

    async def _stream_once(self, client: httpx.AsyncClient, cand: Candidate, url: str, body: Dict[str, Any],
                           headers: Dict[str, str], gate: JsonStreamGate, out: CallOutcome) -> None:
        started = time.perf_counter()
        usage: Dict[str, Any] = {}
        chars = 0
        capture = self.fixed_stream_dialect is not None
        if capture:
            stats = out.stream_observation
            stats.update(requests=1, http_status=None, content_bytes=0, sse_line_bytes=0,
                         done_seen=False, first_schema_ms=None, prompt_tokens=None,
                         completion_tokens=None, invalid_candidates=0, strict_document_valid=False)
            deltas = []
        async with client.stream("POST", url, json=body, headers=headers, timeout=httpx.Timeout(cand.timeout_s, connect=10.0)) as resp:
            if capture:
                stats["http_status"] = resp.status_code
            if resp.status_code >= 400:
                text = (await resp.aread()).decode("utf-8", "replace")
                out.status, out.error = "http_error", f"{resp.status_code}:{text[:300]}"
                return
            lines = resp.aiter_lines()
            first = True
            while True:
                deadline = cand.ttft_timeout_s if first else cand.stall_timeout_s
                try:
                    line = await asyncio.wait_for(lines.__anext__(), timeout=deadline)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    out.status, out.stop_reason = "stream_stall", ("ttft_timeout" if first else "inter_chunk_stall")
                    await resp.aclose()
                    break
                if capture:
                    stats["sse_line_bytes"] += len(line.encode("utf-8"))
                line = line.strip()
                if not line:
                    continue
                delta, done, chunk_usage = self._parse_line(cand.kind, line)
                if chunk_usage:
                    usage.update(chunk_usage)
                    if capture:
                        for name in ("prompt_tokens", "completion_tokens"):
                            value = chunk_usage.get(name)
                            if type(value) is int and value >= 0:
                                stats[name] = value
                if capture and done:
                    stats["done_seen"] = True
                if delta:
                    if first:
                        out.ttft_ms = (time.perf_counter() - started) * 1000
                        first = False
                    chars += len(delta)
                    if capture:
                        deltas.append(delta)
                        stats["content_bytes"] += len(delta.encode("utf-8"))
                    verdict = gate.feed(delta)
                    if capture and verdict == "stop" and stats["first_schema_ms"] is None:
                        stats["first_schema_ms"] = round((time.perf_counter() - started) * 1000, 3)
                    if self.drain_stream:
                        if done:
                            break
                        continue
                    if verdict == "stop":
                        out.early_stop, out.stop_reason = True, gate.stop_reason
                        await resp.aclose()
                        break
                    if verdict == "runaway":
                        out.status, out.stop_reason = "runaway", gate.stop_reason
                        await resp.aclose()
                        break
                elif first and chunk_usage is None and not done:
                    # reasoning / keep-alive chunks still count as liveness for the stall clock
                    pass
                if done:
                    break
        out.latency_ms = (time.perf_counter() - started) * 1000
        if capture:
            from app.kernel.compute.json_stream_gate import schema_valid

            stats["invalid_candidates"] = gate.finish()["invalid_candidates"]
            try:
                document = json.loads("".join(deltas))
            except (ValueError, RecursionError):
                pass
            else:
                stats["strict_document_valid"] = schema_valid(document, gate.schema)[0]
        out.tokens_prompt = int(usage.get("prompt_tokens") or 0)
        if not out.tokens_prompt:
            # usage arrives in the final chunk, which an early stop never reads: estimate from the request
            prompt_chars = sum(len(str(m.get("content") or "")) for m in body.get("messages") or [])
            if prompt_chars:
                out.tokens_prompt, out.tokens_estimated = max(1, round(prompt_chars / 3.6)), True
        if usage.get("completion_tokens"):
            out.tokens_completion = int(usage["completion_tokens"])
        else:
            out.tokens_completion, out.tokens_estimated = max(1, round(chars / 3.6)) if chars else 0, True
        if out.early_stop:
            out.budget_headroom_tokens = max(0, cand.max_tokens - out.tokens_completion)

    @staticmethod
    def _parse_line(kind: str, line: str) -> tuple[str, bool, Optional[Dict[str, Any]]]:
        if kind == "ollama":
            try:
                event = json.loads(line)
            except ValueError:
                return "", False, None
            delta = str((event.get("message") or {}).get("content") or event.get("response") or "")
            usage = None
            if event.get("done"):
                usage = {"prompt_tokens": event.get("prompt_eval_count") or 0, "completion_tokens": event.get("eval_count") or 0}
            return delta, bool(event.get("done")), usage
        if not line.startswith("data:"):
            return "", False, None
        data = line[5:].strip()
        if data == "[DONE]":
            return "", True, None
        try:
            event = json.loads(data)
        except ValueError:
            return "", False, None
        usage = event.get("usage") or None
        choices = event.get("choices") or []
        delta = ""
        if choices:
            d = choices[0].get("delta") or choices[0].get("message") or {}
            delta = str(d.get("content") or "")
        return delta, False, usage

    # -- teardown on stall ------------------------------------------------------------------------
    async def _teardown_stalled(self, client: httpx.AsyncClient, cand: Candidate, reason: str) -> Dict[str, Any]:
        handle = self.lifecycle_handles.get(cand.ident)
        if handle is not None and self.lifecycle is not None:
            try:
                return {"mode": "owned_process", **self.lifecycle.terminate(handle, reason=reason)}
            except Exception as exc:  # noqa: BLE001
                return {"mode": "owned_process", "error": type(exc).__name__}
        if cand.kind == "ollama":
            # System daemon: never kill it; unload the model instead (frees its VRAM/RAM).
            try:
                r = await client.post(cand.base_url.rstrip("/") + "/api/generate", json={"model": cand.model, "keep_alive": 0},
                                      timeout=30.0)
                return {"mode": "ollama_unload", "status": r.status_code}
            except httpx.HTTPError as exc:
                return {"mode": "ollama_unload", "error": type(exc).__name__}
        return {"mode": "connection_closed"}

    # -- main entry -------------------------------------------------------------------------------
    async def complete(self, *, family: str, messages: List[Dict[str, str]], schema: Mapping[str, Any],
                       verify: Verifier, run_id: str) -> GovernedResult:
        if self.avoid is not None:
            hit = self.avoid(family, messages)
            if hit is not None:
                rec = self._receipt({"run_id": run_id, "family": family, "status": "avoided", "model_calls": 0,
                                     "avoided_by": str(hit.get("by", "crystal"))})
                return GovernedResult(accepted=True, value=hit.get("value"), accepted_by=str(hit.get("by", "crystal")),
                                      avoided=True, reason=f"avoided:{rec.get('receipt_id')}")
        ranking = self.rank(family)
        result = GovernedResult(accepted=False, ranking=ranking)
        convo = list(messages)  # grows with verifier feedback turns; never written to receipts
        attempts = 0
        transport = self.transport
        async with httpx.AsyncClient(transport=transport, trust_env=False) as client:
            for row in ranking:
                if attempts >= self.max_attempts:
                    break
                cand: Candidate = row["_cand"]
                if self.breaker.state(cand.ident)["state"] == "open":
                    out = CallOutcome(candidate=cand, status="skipped_circuit_open")
                    out.receipt_id = self._receipt({"run_id": run_id, "family": family, "candidate": cand.ident,
                                                    "status": out.status}).get("receipt_id", "")
                    result.calls.append(out)
                    continue
                proposal = self._proposal(cand, family, run_id, attempts)
                decision = self.governor.admit(self._episode(run_id), proposal)
                self._signatures.append(proposal.signature())
                if not decision.permits():
                    out = CallOutcome(candidate=cand, status="refused_governor", error=",".join(decision.reasons),
                                      governor_receipt=decision.receipt_id)
                    out.receipt_id = self._receipt({"run_id": run_id, "family": family, "candidate": cand.ident,
                                                    "status": out.status, "reasons": list(decision.reasons)}).get("receipt_id", "")
                    result.calls.append(out)
                    if any(r.startswith("budget_exhausted") for r in decision.reasons):
                        result.reason = "governor_budget_exhausted"
                        break
                    continue
                attempts += 1
                out = await self.governor.run_admitted(decision, proposal, lambda: self._call(client, cand, list(convo), schema, family))
                out.governor_receipt = decision.receipt_id
                if out.json_valid and out.status == "ok":
                    v = verify(out.value)
                    if asyncio.iscoroutine(v):
                        v = await v
                    out.verify = dict(v or {})
                    if not out.verify.get("passed"):
                        out.status = "verifier_reject"
                        if self.feedback_turns:
                            # Repair turn for the next candidate: show the rejected action and the verifier's
                            # evidence (e.g. failing test tail), so it can return the complete corrected action.
                            feedback = str(out.verify.get("feedback") or "")[-1500:]
                            convo += [{"role": "assistant", "content": json.dumps(out.value)[:4000]},
                                      {"role": "user", "content": (
                                          f"The verifier rejected that action ({out.verify.get('reason') or 'rejected'})."
                                          + (f" Evidence after applying it:\n{feedback}\n" if feedback else " ")
                                          + "Reply with ONE complete corrected JSON action that includes every change "
                                            "needed (all files and call sites), and nothing else.")}]
                        if out.verify.get("runaway"):
                            out.teardown = await self._teardown_stalled(client, cand, "runaway_output")
                elif out.status == "ok":
                    out.status = "json_invalid"
                if out.status in {"stream_stall", "runaway"}:
                    out.teardown = await self._teardown_stalled(client, cand, "stream_stall" if out.status == "stream_stall" else "runaway_output")
                passed = out.status == "ok"
                self._tokens_used += out.tokens_prompt + out.tokens_completion
                out.spend_usd = (out.tokens_prompt * cand.usd_per_mtok_in + out.tokens_completion * cand.usd_per_mtok_out) / 1e6
                transport_failure = out.status in {"http_error", "transport_error", "stream_stall"}
                self.breaker.record(cand.ident, passed, transport_failure=transport_failure)
                self.scorecard.record(provider=cand.provider, model=cand.model, family=family, placement=cand.placement,
                                      passed=passed, json_valid=out.json_valid,
                                      tokens=out.tokens_prompt + out.tokens_completion, latency_ms=out.latency_ms,
                                      spend_usd=out.spend_usd, failure_kind="" if passed else out.status)
                out.receipt_id = self._receipt({
                    "run_id": run_id, "family": family, "candidate": cand.ident, "status": out.status,
                    "json_valid": out.json_valid, "passed": passed, "dialect": out.dialect, "early_stop": out.early_stop,
                    "stop_reason": out.stop_reason, "tokens_prompt": out.tokens_prompt,
                    "tokens_completion": out.tokens_completion, "tokens_estimated": out.tokens_estimated,
                    "ttft_ms": round(out.ttft_ms, 1), "latency_ms": round(out.latency_ms, 1),
                    "spend_usd": out.spend_usd, "error": out.error[:300], "governor_receipt": decision.receipt_id,
                    "breaker": self.breaker.state(cand.ident), "teardown": out.teardown,
                    "verify_reason": str(out.verify.get("reason", ""))[:200]}).get("receipt_id", "")
                result.calls.append(out)
                if passed:
                    result.accepted, result.value, result.accepted_by = True, out.value, cand.ident
                    result.reason = "verified"
                    break
        if not result.accepted and not result.reason:
            result.reason = "all_candidates_failed"
        return result

    async def _call_replicate(self, client: httpx.AsyncClient, cand: Candidate, messages: List[Dict[str, str]],
                              schema: Mapping[str, Any], secrets: List[str]) -> CallOutcome:
        """Replicate predictions API (not OpenAI-compatible): prompt-enforced JSON + validation + one repair retry.

        POST {base}/models/{owner}/{name}/predictions with ``Prefer: wait``; polls ``urls.get`` if still running.
        No grammar/JSON mode is assumed (dialect ``prompt_validate_retry``); the gate validates the whole output.
        """
        imap = {"prompt": "prompt", "system": "system_prompt", "max_tokens": "max_tokens", **(cand.options.get("input_map") or {})}
        system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
        system = (system + "\n" if system else "") + ("Respond with ONLY one JSON object (no prose, no code fences) that validates "
                                                       "against this JSON Schema:\n" + json.dumps(schema, separators=(",", ":")))
        turns = [m for m in messages if m.get("role") != "system"]
        out = CallOutcome(candidate=cand, status="ok", dialect="prompt_validate_retry")
        headers = {"Authorization": f"Bearer {self._secret(cand)}", "Prefer": "wait=60", "Content-Type": "application/json"}
        url = cand.base_url.rstrip("/") + f"/models/{cand.model}/predictions"
        started = time.perf_counter()
        tok_in = tok_out = 0
        for attempt in range(2):
            prompt = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in turns) + "\n\nASSISTANT:"
            inp: Dict[str, Any] = {imap["prompt"]: prompt, imap["max_tokens"]: cand.max_tokens, "temperature": 0}
            if imap.get("system"):
                inp[imap["system"]] = system
            else:
                inp[imap["prompt"]] = system + "\n\n" + prompt
            inp.update(cand.options.get("extra_input") or {})
            try:
                resp = await client.post(url, json={"input": inp}, headers=headers, timeout=cand.timeout_s)
                if resp.status_code >= 400:
                    out.status, out.error = "http_error", redact(f"{resp.status_code}:{resp.text[:300]}", secrets)
                    break
                pred = resp.json()
                deadline = time.perf_counter() + cand.timeout_s
                while pred.get("status") in {"starting", "processing"} and time.perf_counter() < deadline:
                    await asyncio.sleep(1.0)
                    pred = (await client.get(pred["urls"]["get"], headers=headers, timeout=30)).json()
            except httpx.HTTPError as exc:
                out.status, out.error = "transport_error", redact(f"{type(exc).__name__}: {exc}", secrets)[:300]
                break
            if pred.get("status") != "succeeded":
                out.status = "stream_stall" if pred.get("status") in {"starting", "processing"} else "http_error"
                out.error = redact(f"prediction_{pred.get('status')}:{str(pred.get('error'))[:200]}", secrets)
                break
            text = pred.get("output")
            text = "".join(text) if isinstance(text, list) else str(text or "")
            metrics = pred.get("metrics") or {}
            tok_in += int(metrics.get("input_token_count") or 0)
            tok_out += int(metrics.get("output_token_count") or 0) or max(1, round(len(text) / 3.6))
            if not out.ttft_ms:
                out.ttft_ms = (time.perf_counter() - started) * 1000
            gate = JsonStreamGate(schema=schema)
            gate.feed(text)
            final = gate.finish()
            out.json_valid, out.value = bool(final["valid"]), final["value"]
            out.status, out.error = "ok", ""
            if out.json_valid:
                break
            out.error = str(final.get("error") or "no_json_action")[:200]
            turns = turns + [{"role": "assistant", "content": text[:2000]},
                             {"role": "user", "content": "That was not a single valid JSON object matching the schema. "
                                                         "Reply again with ONLY the JSON object."}]
        out.dialect = "prompt_validate_retry" + (f":attempts={attempt + 1}" if out.status == "ok" else "")
        out.latency_ms = (time.perf_counter() - started) * 1000
        if out.status in {"http_error", "transport_error"} and not tok_out:
            return out  # nothing ran: no tokens, no spend
        if not tok_in:
            tok_in = max(1, round((len(system) + sum(len(str(m.get("content") or "")) for m in turns)) / 3.6))
            out.tokens_estimated = True
        out.tokens_prompt, out.tokens_completion = tok_in, tok_out
        return out

    async def _call(self, client: httpx.AsyncClient, cand: Candidate, messages: List[Dict[str, str]],
                    schema: Mapping[str, Any], family: str) -> CallOutcome:
        out = CallOutcome(candidate=cand, status="ok")
        secrets = self._secret_values()
        if cand.kind == "replicate":
            return await self._call_replicate(client, cand, messages, schema, secrets)
        if cand.provider == "tgi":
            # GPU self-scheduling: TGI batch about to run -> unload GPU-resident Ollama models first (keep_alive 0, throttled).
            from app.kernel.compute import gpu_scheduler

            if gpu_scheduler.enabled():
                self.__dict__.setdefault("gpu_prepare_events", []).append(await asyncio.to_thread(gpu_scheduler.ensure_tgi_gpu))
        dropped: set = set()  # optional knobs (chat_template_kwargs, reasoning_effort, stream_options) a server rejected
        dialects = ([self.fixed_stream_dialect] if self.fixed_stream_dialect is not None
                    else list(dialects_for(cand.kind)))
        i = 0
        while i < len(dialects):
            dialect = dialects[i]
            out = CallOutcome(candidate=cand, status="ok", dialect=dialect)
            gate = JsonStreamGate(schema=schema)
            url, body, headers = self._request(cand, messages, schema, dialect, family)
            for key in dropped:
                body.pop(key, None)
            try:
                await self._stream_once(client, cand, url, body, headers, gate, out)
            except httpx.HTTPError as exc:
                out.status, out.error = "transport_error", redact(f"{type(exc).__name__}: {exc}", secrets)[:300]
                return out
            if self.fixed_stream_dialect is None and out.status == "http_error" and out.error.startswith(("400", "422")):
                stripped = set(body) - set(strip_unsupported(body, out.error))
                if stripped - dropped:
                    dropped |= stripped  # retry the SAME dialect without the rejected knob
                    continue
                if dialect != "prompt_only":
                    out.error = redact(out.error, secrets)
                    i += 1
                    continue  # dialect not accepted by this server: fall back to the next one
            out.error = redact(out.error, secrets)
            if out.status in {"ok"}:
                final = gate.finish()
                out.json_valid = bool(final["valid"])
                out.value = final["value"]
                if not out.early_stop and final["valid"]:
                    out.stop_reason = "stream_end"
                if not out.json_valid:
                    out.error = str(final.get("error") or "no_json_action")[:200]
            return out
        return out


__all__ = ["Candidate", "CircuitBreaker", "GovernedModelClient", "GovernedResult", "CallOutcome", "enabled", "redact"]


# ---------------------------------------------------------------------------
# Default candidate fabric (names/paths only; values are read at call time).
# ---------------------------------------------------------------------------
NIM_BASE = "https://integrate.api.nvidia.com/v1"
HF_ROUTER_BASE = "https://router.huggingface.co/v1"
HF_TOKEN_FILE = "~/.cache/huggingface/token"


TGI_DEFAULT_BASE = "http://127.0.0.1:8090"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
PROVIDER_SECRETS_ENV = str(Path(__file__).resolve().parents[3] / ".beast" / "provider_secrets.env")
HF_LANES_PATH = Path(__file__).with_name("hf_router_lanes.json")


def dotenv_value(path: str, name: str) -> str:
    """Return ``name`` from a dotenv file (value stays in memory; never logged)."""
    try:
        for line in Path(os.path.expanduser(path)).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:].lstrip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def hf_router_candidates(env: Mapping[str, str] | None = None, *, path: str | Path | None = None) -> List[Candidate]:
    """One Candidate per approved (model, provider) HF-router route from ``hf_router_lanes.json``.

    The model id carries the route suffix (``model:provider``) so the scorecard and the breaker learn
    per (model, provider) cell.  ``BEAST_HF_ROUTER_MODELS`` (comma list of bare model ids) narrows the set.
    """
    env = os.environ if env is None else env
    cfg = json.loads(Path(path or HF_LANES_PATH).read_text(encoding="utf-8"))
    only = {m.strip() for m in str(env.get("BEAST_HF_ROUTER_MODELS") or "").split(",") if m.strip()}
    out: List[Candidate] = []
    for m in cfg.get("models", []):
        if only and m["model"] not in only:
            continue
        for r in m.get("routes", []):
            out.append(Candidate(provider="hf", model=f'{m["model"]}:{r["provider"]}', kind="hf_router",
                                 base_url=cfg.get("base_url", HF_ROUTER_BASE), key_env=cfg.get("key_env", "HF_TOKEN"),
                                 key_file=cfg.get("key_file", HF_TOKEN_FILE), max_tokens=int(m.get("max_tokens", 2048)),
                                 ttft_timeout_s=60, stall_timeout_s=30, timeout_s=120,
                                 usd_per_mtok_in=float(r.get("usd_per_mtok_in") or 0.0),
                                 usd_per_mtok_out=float(r.get("usd_per_mtok_out") or 0.0)))
    return out


PROVIDER_LANES_PATH = Path(__file__).with_name("provider_lanes.json")


def provider_lane_candidates(env: Mapping[str, str] | None = None, *, dotenv: str | None = None,
                             path: str | Path | None = None, providers: Sequence[str] | None = None) -> List[Candidate]:
    """Direct-provider lanes (Fireworks, Hyperbolic, Replicate) from ``provider_lanes.json``.

    A provider contributes candidates only when its key env var is set in the environment or in
    ``.beast/provider_secrets.env`` (checked by name; values are read at call time and never recorded).
    """
    env = os.environ if env is None else env
    dotenv = PROVIDER_SECRETS_ENV if dotenv is None else dotenv
    cfg = json.loads(Path(path or PROVIDER_LANES_PATH).read_text(encoding="utf-8"))
    out: List[Candidate] = []
    for name, prov in cfg.get("providers", {}).items():
        if providers and name not in providers:
            continue
        key_env = prov["key_env"]
        if not (env.get(key_env) or (dotenv and dotenv_value(dotenv, key_env))):
            continue
        for m in prov.get("models", []):
            out.append(Candidate(provider=name, model=m["model"], kind=prov.get("kind", "openai"), base_url=prov["base_url"],
                                 key_env=key_env, key_dotenv=dotenv or "", max_tokens=int(m.get("max_tokens", 2048)),
                                 auth_scheme=str(prov.get("auth_scheme") or "Bearer"),
                                 ttft_timeout_s=float(m.get("ttft_timeout_s", 60)), stall_timeout_s=30,
                                 timeout_s=float(m.get("timeout_s", 120)),
                                 options={k: v for k, v in m.items() if k in {"input_map", "extra_input"}},
                                 usd_per_mtok_in=float(m.get("usd_per_mtok_in") or 0.0),
                                 usd_per_mtok_out=float(m.get("usd_per_mtok_out") or 0.0)))
    return out


def gemini_candidate(env: Mapping[str, str] | None = None, *, dotenv: str | None = None) -> Optional[Candidate]:
    """Google Gemini via its OpenAI-compatible endpoint (json_schema response_format + streaming).

    Present only when ``GEMINI_API_KEY`` exists in the environment or in ``.beast/provider_secrets.env``
    (checked by name; the value is read at call time and never recorded).
    """
    env = os.environ if env is None else env
    dotenv = PROVIDER_SECRETS_ENV if dotenv is None else dotenv
    if not (env.get("GEMINI_API_KEY") or (dotenv and dotenv_value(dotenv, "GEMINI_API_KEY"))):
        return None
    return Candidate(provider="gemini", model=str(env.get("BEAST_GEMINI_MODEL") or "gemini-2.5-flash"), kind="gemini",
                     base_url=str(env.get("GEMINI_OPENAI_BASE") or GEMINI_BASE), key_env="GEMINI_API_KEY",
                     key_dotenv=dotenv or "", max_tokens=2048, ttft_timeout_s=60, stall_timeout_s=30, timeout_s=120,
                     usd_per_mtok_in=float(env.get("BEAST_GEMINI_USD_IN") or 0.30),
                     usd_per_mtok_out=float(env.get("BEAST_GEMINI_USD_OUT") or 2.50))


def tgi_available(base_url: str, *, timeout: float = 1.0, transport: httpx.BaseTransport | None = None) -> bool:
    """Probe a local TGI before routing to it (GET /health -> 200). TGI is optional."""
    try:
        with httpx.Client(transport=transport, trust_env=False, timeout=timeout) as c:
            return c.get(base_url.rstrip("/") + "/health").status_code == 200
    except (httpx.HTTPError, OSError):
        # OSError covers a missing CA bundle (FileNotFoundError from
        # ssl.create_default_context) and DNS/socket failures.  TGI is optional,
        # so a broken local probe must report "down" instead of escaping as a
        # 500 that takes the whole governed model inventory with it.
        return False


def default_candidates(env: Mapping[str, str] | None = None, *, include_7b: bool = False, probe_tgi: bool = True,
                       tgi_transport: httpx.BaseTransport | None = None) -> List[Candidate]:
    """Cheapest-first static order; the scorecard re-ranks it from evidence.

    Local Ollama models first (zero marginal cost), then NIM (free-tier credits),
    then the HF Inference Providers router (HF Pro credits), then local TGI if
    ``TGI_BASE_URL`` is set.  Credentials are referenced by env-var name / file
    path only.
    """
    env = os.environ if env is None else env
    ollama = str(env.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434")
    cands = [
        Candidate(provider="ollama", model="qwen3:4b", kind="ollama", base_url=ollama, placement="gpu_full",
                  rung="local_specialist", max_tokens=1024, ttft_timeout_s=120, stall_timeout_s=30, timeout_s=240),
        Candidate(provider="ollama", model="granite3.3:2b", kind="ollama", base_url=ollama, placement="gpu_full",
                  rung="local_specialist", max_tokens=1024, ttft_timeout_s=90, stall_timeout_s=30, timeout_s=180),
    ]
    if include_7b:
        cands.append(Candidate(provider="ollama", model="qwen2.5-coder:7b", kind="ollama", base_url=ollama,
                               placement="hybrid:6", rung="local_specialist", max_tokens=768, ttft_timeout_s=180,
                               stall_timeout_s=45, timeout_s=600, options={"options": {"num_gpu": 6, "num_ctx": 4096}}))
    cands += [
        Candidate(provider="nim", model="nvidia/nemotron-3.5-lightning-30b-a3b", kind="nim", base_url=NIM_BASE,
                  key_env="NVIDIA_API_KEY", max_tokens=2048, ttft_timeout_s=60, stall_timeout_s=30, timeout_s=120),
        Candidate(provider="nim", model="deepseek-ai/deepseek-v4.1-flash", kind="nim", base_url=NIM_BASE,
                  key_env="NVIDIA_API_KEY", max_tokens=4096, ttft_timeout_s=60, stall_timeout_s=30, timeout_s=120),
        Candidate(provider="nim", model="openai/gpt-oss-20b", kind="nim", base_url=NIM_BASE, key_env="NVIDIA_API_KEY",
                  max_tokens=4096, ttft_timeout_s=60, stall_timeout_s=30, timeout_s=120),
    ]
    if env.get("BEAST_HF_ROUTER_MODEL"):  # explicit single-model override (legacy knob)
        cands.append(Candidate(provider="hf", model=str(env["BEAST_HF_ROUTER_MODEL"]), kind="hf_router",
                               base_url=HF_ROUTER_BASE, key_env="HF_TOKEN", key_file=HF_TOKEN_FILE,
                               max_tokens=2048, ttft_timeout_s=60, stall_timeout_s=30, timeout_s=120))
    else:
        cands += hf_router_candidates(env)
    gem = gemini_candidate(env)
    if gem is not None:
        cands.append(gem)
    cands += provider_lane_candidates(env)
    tgi_base = str(env.get("TGI_BASE_URL") or TGI_DEFAULT_BASE).rstrip("/")
    tgi_up = bool(probe_tgi and tgi_available(tgi_base, transport=tgi_transport))
    if tgi_up:
        # Local GPU, zero marginal cost: insert right after the local Ollama models.
        local = sum(1 for c in cands if c.provider == "ollama")
        cands.insert(local, Candidate(provider="tgi", model="tgi", kind="tgi", base_url=tgi_base + "/v1",
                                      placement="gpu_full", rung="local_specialist", max_tokens=1024,
                                      ))
    from app.kernel.compute import gpu_scheduler

    if probe_tgi and gpu_scheduler.enabled(dict(env)):
        # One exclusive local GPU lane: TGI first while it holds the VRAM (GPU Ollama dropped), else Ollama.
        cands = gpu_scheduler.local_candidates(cands, tgi_up=tgi_up)
    return cands


__all__ += ["default_candidates", "tgi_available", "hf_router_candidates", "gemini_candidate", "dotenv_value", "provider_lane_candidates"]
