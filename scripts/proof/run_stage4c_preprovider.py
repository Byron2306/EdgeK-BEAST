"""Fixed-route pre-provider interception pilot on synthetic validation contracts."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import random
from statistics import median
import time

import httpx
from jsonschema import Draft202012Validator

from app.kernel.compute.capability_scorecard import CapabilityScorecard
from app.kernel.compute.compute_ir import DeterministicDisplacementProof
from app.kernel.compute.compute_ledger import ComputeLedger
from app.kernel.compute.governed_client import Candidate, GovernedModelClient, NIM_BASE
from app.kernel.compute.inference_interceptor import InferenceComputeInterceptor
from app.kernel.compute.perceive import EdgeKIR
from app.kernel.governance.compute_governor import ComputeGovernor
from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog
from scripts.proof.run_coder_efficiency_matrix import canonical, digest, git, REPO, write_json
from scripts.proof.run_stage4b_governed_proxy import MODEL, DIALECTS

ARMS = ("pass_through", "shadow", "verified_local")
SCHEMA = {"type": "object", "properties": {
    "retry": {"type": "integer"}, "label": {"type": "string"}},
    "required": ["retry", "label"]}
RESPONSE_SCHEMA = {"type": "object", "properties": {
    "valid": {"type": "boolean"}, "error_paths": {"type": "array", "items": {"type": "string"}}},
    "required": ["valid", "error_paths"], "additionalProperties": False}


@dataclass(frozen=True)
class Case:
    instance: dict
    eligible: bool = True
    intervention: str = "none"


CASES = {
    "valid": Case({"retry": 2, "label": "pilot"}),
    "invalid_type": Case({"retry": "2", "label": "pilot"}),
    "missing_proof": Case({"retry": 2, "label": "pilot"}, False, "missing_proof"),
    "wrong_proof_digest": Case({"retry": 2, "label": "pilot"}, False, "wrong_proof_digest"),
    "incomplete_transform": Case({"retry": 2, "label": "pilot"}, False, "incomplete_transform"),
}


def oracle(instance):
    errors = list(Draft202012Validator(SCHEMA).iter_errors(instance))
    return {"valid": not errors,
            "error_paths": sorted("$" + "".join(f".{part}" for part in e.absolute_path) for e in errors)}


def make_plan(cases, repeats, seed):
    rng = random.Random(seed)
    blocks = [(case, r) for case in cases for r in range(1, repeats + 1)]
    rng.shuffle(blocks)
    plan = []
    for case, repeat in blocks:
        provider_seed = rng.randrange(1, 2**31)
        arms = list(ARMS)
        rng.shuffle(arms)
        plan.extend({"trial_id": f"{case}-{repeat:02d}-{arm}", "case": case,
                     "repeat": repeat, "arm": arm, "provider_seed": provider_seed,
                     "expected_local_eligible": CASES[case].eligible} for arm in arms)
    return plan


def messages_for(instance):
    return [
        {"role": "system", "content": "Validate the instance against the JSON Schema and return one JSON object "
                                      'with keys "valid" (boolean) and "error_paths" (array of strings). '
                                      "Use an empty array for a valid instance. Report invalid property types as "
                                      'paths such as "$.field". Use no Markdown and do not coerce types.'},
        {"role": "user", "content": canonical({"schema": SCHEMA, "instance": instance}).decode()},
    ]


def metadata_for(case, expected):
    output_hash = "sha256:" + digest(canonical(expected))
    proof_hash = "sha256:" + "0" * 64 if case.intervention == "wrong_proof_digest" else output_hash
    # Deliberately synthetic authority only. Not promoted reuse or production evidence.
    proof = DeterministicDisplacementProof(
        candidate_name="schema_validation", task_class="contract", risk_class="low",
        allowed_transform="schema_validation", verifier_command="stage4c_fixture_oracle",
        visible_tests_equal_or_better=True, hidden_tests_equal_or_better=True,
        scope_checks_equal_or_better=True, rollback_equal_or_better=True,
        security_checks_equal_or_better=True, paired_ablation_runs=1, confidence=0.99,
        approved_for_enforcement=True, policy_version="stage4c_synthetic_only",
        expected_output_sha256=proof_hash, proof_id="stage4c_fixture_only",
        impact_fingerprint={"state": "active", "reusable": True},
    )
    return {
        "task_class": "contract", "deterministic_candidates": ["schema_validation"],
        "displacement_proofs": [] if case.intervention == "missing_proof" else [proof.to_dict()],
        "deterministic_work": {"schema_validation": {
            "schema": SCHEMA, "instance": case.instance,
            "expect_valid": expected["valid"], "expected_output_sha256": output_hash,
            "complete_task": case.intervention != "incomplete_transform",
        }},
    }


class CountedTransport(httpx.AsyncBaseTransport):
    def __init__(self, backend):
        self.backend = backend
        self.requests = 0

    async def handle_async_request(self, request):
        self.requests += 1
        if self.requests != 1:
            raise RuntimeError("Stage 4C transport exceeded the one-request trial cap")
        return await self.backend.handle_async_request(request)

    async def aclose(self):
        if self.backend is not None:
            await self.backend.aclose()


def scripted_response(expected):
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=(
        b"data: " + canonical({"choices": [{"delta": {"content": canonical(expected).decode()}}]})
        + b'\n\ndata: {"usage":{"prompt_tokens":40,"completion_tokens":14}}\n\ndata: [DONE]\n\n'))


async def run_trial(out, row, *, live, model=MODEL, dialect=DIALECTS[0], backend=None):
    trial = out / "trials" / row["trial_id"]
    trial.mkdir(parents=True)
    case = CASES[row["case"]]
    expected = oracle(case.instance)
    messages = messages_for(case.instance)
    arm = row["arm"]
    started = time.perf_counter()
    interceptor = interception = None
    route = "provider"
    transform_results = []
    if arm != "pass_through":
        mode = "phase2_shadow" if arm == "shadow" else "phase2_enforce"
        interceptor = InferenceComputeInterceptor(
            governor=ComputeGovernor(mode=mode),
            ledger=ComputeLedger(str(trial / "compute.sqlite3")),
            promoted_capability_store=trial / "no_promoted_capabilities.json",
        )
        ir = EdgeKIR(messages=messages, model=model, max_tokens=256, metadata=metadata_for(case, expected))
        interception = interceptor.begin(ir, "nim")
        route = interceptor.execution_route(interception)
        transform_results = [r.to_dict() for r in interception.deterministic_shadow_results]
    prep_ms = (time.perf_counter() - started) * 1000
    if route not in {"provider", "deterministic"} or (arm != "verified_local" and route != "provider"):
        raise RuntimeError("unexpected route in fixed experiment")

    transport = CountedTransport(backend)
    observed_usage = {"prompt_tokens": None, "completion_tokens": None}
    provider_status = None
    http_status = None
    if route == "deterministic":
        try:
            response = interceptor.deterministic_response(interception)
            value = response["result"]
        finally:
            await transport.aclose()
        verified = value == expected
        status = "deterministic_succeeded" if verified else "deterministic_failed_oracle"
    else:
        if transport.backend is None:
            transport.backend = (httpx.AsyncHTTPTransport(retries=0) if live
                                 else httpx.MockTransport(lambda _: scripted_response(expected)))
        candidate = Candidate("nim", model, "nim", NIM_BASE, key_env="NVIDIA_API_KEY" if live else "",
                              max_tokens=256, timeout_s=45, ttft_timeout_s=35, stall_timeout_s=15,
                              options={"seed": row["provider_seed"]})
        client = GovernedModelClient(
            [candidate], transport=transport, use_scorecard=False, max_attempts=1, feedback_turns=False,
            fixed_stream_dialect=dialect, drain_stream=True,
            governor=ComputeGovernorSpine(receipts=GovernorReceiptLog(trial / "provider.jsonl"), enforce=True),
            scorecard=CapabilityScorecard(trial / "scorecard.json"),
        )
        result = await client.complete(family="stage4c", messages=messages, schema=RESPONSE_SCHEMA,
            verify=lambda value: {"passed": value == expected, "reason": "independent_schema_oracle"},
            run_id=row["trial_id"])
        if len(result.calls) != 1:
            raise RuntimeError("expected exactly one governed outcome")
        call = result.calls[0]
        provider_status = call.status
        http_status = call.stream_observation.get("http_status")
        for key in observed_usage:
            observed_usage[key] = call.stream_observation.get(key)
        response = {"usage": observed_usage}
        verified = result.accepted
        status = call.status

    requested = route == "provider"
    receipt = None
    if interception is not None:
        receipt = interceptor.complete(interception, response=response, status=status,
                                       provider_execution_requested=requested,
                                       behavior_preserved=verified).to_dict()
    should_local = arm == "verified_local" and case.eligible
    consistent = (route == ("deterministic" if should_local else "provider")
                  and transport.requests == int(requested))
    return {**row, "status": status, "verified": verified, "selected_route": route,
            "route_control_passed": consistent, "provider_requests": transport.requests,
            "provider_status": provider_status, "http_status": http_status, "provider_usage": observed_usage,
            "observed_avoidance": bool(should_local and route == "deterministic"
                                       and not transport.requests and verified),
            "interception_ms": round(prep_ms, 3), "wall_ms": round((time.perf_counter() - started) * 1000, 3),
            "transform_results": transform_results, "receipt": receipt,
            "request_messages_sha256": digest(canonical(messages)), "oracle_sha256": digest(canonical(expected))}


def summarize(plan, rows, *, live, abort):
    arms = {}
    for arm in ARMS:
        trials = [r for r in rows if r["arm"] == arm and r["status"] != "not_run"]
        time_vals = [r["wall_ms"] for r in trials if r.get("verified") and "wall_ms" in r]
        arms[arm] = {
            "planned": sum(r["arm"] == arm for r in plan),
            "attempted": len(trials), "verified": sum(bool(r.get("verified")) for r in trials),
            "provider_requests": sum(r.get("provider_requests", 0) for r in trials),
            "deterministic_resolutions_verified": sum(bool(r.get("observed_avoidance")) for r in trials),
            "near_miss_provider_calls": sum(r.get("provider_requests", 0) for r in trials
                                            if not r["expected_local_eligible"]),
            "route_controls_passed": sum(bool(r.get("route_control_passed")) for r in trials),
            "median_verified_wall_ms": median(time_vals) if time_vals else None,
        }
    paired = []
    blocks = {}
    for r in rows:
        blocks.setdefault((r["case"], r["repeat"]), {})[r["arm"]] = r
    for (case, repeat), block in blocks.items():
        if not all(block.get(arm, {}).get("route_control_passed") for arm in ARMS):
            continue
        base, shadow, local = (block[arm] for arm in ARMS)
        paired.append({"case": case, "repeat": repeat,
            "verified_provider_requests_avoided": int(base["verified"] and base["provider_requests"] == 1
                and local["observed_avoidance"]),
            "local_vs_pass_through_wall_ms": round(local["wall_ms"] - base["wall_ms"], 3),
            "shadow_vs_pass_through_wall_ms": round(shadow["wall_ms"] - base["wall_ms"], 3),
        })
    return {"schema": "beast.stage4c.preprovider.v1",
        "evidence_class": "live_synthetic_fixture_authority" if live else "mock_transport_controls",
        "planned": len(plan), "attempted": sum(r["status"] != "not_run" for r in rows),
        "abort": abort, "arms": arms, "paired": paired,
        "paired_verified_provider_requests_avoided": sum(p["verified_provider_requests_avoided"] for p in paired)
            if live else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--provider", choices=("scripted", "nim"), default="scripted")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--dialect", choices=DIALECTS, default=DIALECTS[0])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--seed", type=int, default=4327)
    parser.add_argument("--request-cap", type=int, default=0)
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 10:
        parser.error("repeats must be 1–10")
    plan = make_plan(tuple(CASES), args.repeats, args.seed)
    live = args.provider == "nim"
    if live and (not os.environ.get("NVIDIA_API_KEY") or args.request_cap < len(plan)):
        parser.error("live requires NVIDIA_API_KEY and --request-cap >= total planned trials")
    out = args.out.resolve()
    out.mkdir(parents=True)
    write_json(out / "plan.json", {"code_head": git(REPO, "rev-parse", "HEAD").strip(),
        "seed": args.seed, "provider": args.provider, "endpoint": NIM_BASE,
        "model": args.model, "dialect": args.dialect, "rows": plan,
        "schema_sha256": digest(canonical(SCHEMA)),
        "response_schema_sha256": digest(canonical(RESPONSE_SCHEMA)),
        "cases": {name: {"messages_sha256": digest(canonical(messages_for(case.instance))),
                         "intervention": case.intervention, "eligible": case.eligible}
                  for name, case in CASES.items()},
        "claim_boundary": "Synthetic contracts and fixture-only authority. No promotion or production changes. "
                          "Same constrained drain whenever provider is called. No token or billing estimate."})
    rows, abort = [], None
    for row in plan:
        if abort:
            result = {**row, "status": "not_run", "verified": None}
        else:
            try:
                result = asyncio.run(run_trial(out, row, live=live, model=args.model, dialect=args.dialect))
            except Exception as exc:
                result = {**row, "status": "harness_error", "verified": False, "error_type": type(exc).__name__}
            if not result.get("route_control_passed") or result.get("http_status") in {400, 401, 403, 404, 422, 429}:
                abort = {"trial_id": row["trial_id"], "status": result["status"],
                         "http_status": result.get("http_status"), "error_type": result.get("error_type")}
        rows.append(result)
        with (out / "attempts.jsonl").open("ab") as f:
            f.write(canonical(result) + b"\n")
        print(row["trial_id"], result["status"], "route=", result.get("selected_route"),
              "requests=", result.get("provider_requests"), "verified=", result["verified"], flush=True)
    write_json(out / "summary.json", summarize(plan, rows, live=live, abort=abort))
    files = sorted(p for p in out.rglob("*") if p.is_file())
    (out / "SHA256SUMS").write_text("".join(f"{digest(p.read_bytes())}  {p.relative_to(out)}\n" for p in files))
    print("REPORT:", out)
    return 1 if abort or (not live and not all(r["verified"] for r in rows)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
