#!/usr/bin/env python3
"""Live proof: coding tasks through the ONE governed client (BEAST_GOVERNED_INTERCEPTION).

Phase 1 (routed): 10 tasks (6 gauntlet families incl. the failed refactor-rename,
multi-file toolchain and refguard composites, dual and far tasks) go through
GovernedModelClient with the capability scorecard ranking candidates (Ollama,
NIM Nemotron / DeepSeek / gpt-oss, HF Inference Providers router).
Phase 2 (head-to-head): every candidate alone on 3 tasks, to measure per-model
JSON validity and accept rate under schema-forced, streamed decoding.

Each task runs on a fresh temp copy; the verifier (visible tests) plus an
independent hidden check in a separate copy decide acceptance.  Evidence goes to
evidence/governed-interception-2026-11-16/live/.  No prompts, outputs or
credentials are written to receipts; prompt text is never stored.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import gauntlet_large as gl  # noqa: E402

from app.kernel.compute.capability_scorecard import CapabilityScorecard  # noqa: E402
from app.kernel.compute.family_crystals import run_verify  # noqa: E402
from app.kernel.compute.governed_client import Candidate, CircuitBreaker, GovernedModelClient, NIM_BASE, HF_ROUTER_BASE  # noqa: E402
from app.kernel.compute.structured_edit import EDITS_SCHEMA, edits_messages  # noqa: E402
from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog  # noqa: E402
from app.kernel.security.secret_vault import SecretVault  # noqa: E402

OUT = ROOT / "evidence" / "governed-interception-2026-11-16" / "live"
STATE = ROOT / ".beast" / "governed-interception"
ROUTED_TASKS = ["const-h1", "op-h1", "obo-h1", "exc-h1", "ren-h1", "ren-h2", "tool-h1", "refguard-h1", "dual-h1", "far-1"]
H2H_TASKS = ["const-h2", "ren-h3", "refguard-h2"]
HARD_TASKS = ["ren-h1", "ren-h2", "ren-h3", "refguard-h1", "refguard-h2"]
OLLAMA = "http://127.0.0.1:11434"


def candidates() -> list[Candidate]:
    return [
        Candidate(provider="ollama", model="qwen3:4b", kind="ollama", base_url=OLLAMA, placement="auto",
                  rung="local_specialist", max_tokens=1024, ttft_timeout_s=150, stall_timeout_s=40, timeout_s=300),
        Candidate(provider="ollama", model="qwen2.5-coder:7b", kind="ollama", base_url=OLLAMA, placement="gpu_full",
                  rung="local_specialist", max_tokens=1024, ttft_timeout_s=150, stall_timeout_s=40, timeout_s=300,
                  options={"options": {"num_gpu": 99, "num_ctx": 8192}}),
        Candidate(provider="ollama", model="granite3.3:2b", kind="ollama", base_url=OLLAMA, placement="auto",
                  rung="local_specialist", max_tokens=1024, ttft_timeout_s=120, stall_timeout_s=40, timeout_s=240),
        Candidate(provider="nim", model="nvidia/nemotron-3.5-lightning-30b-a3b", kind="nim", base_url=NIM_BASE,
                  key_env="NVIDIA_API_KEY", max_tokens=2048, ttft_timeout_s=60, stall_timeout_s=30, timeout_s=120),
        Candidate(provider="nim", model="deepseek-ai/deepseek-v4.1-flash", kind="nim", base_url=NIM_BASE,
                  key_env="NVIDIA_API_KEY", max_tokens=4096, ttft_timeout_s=60, stall_timeout_s=30, timeout_s=120),
        Candidate(provider="nim", model="openai/gpt-oss-20b", kind="nim", base_url=NIM_BASE, key_env="NVIDIA_API_KEY",
                  max_tokens=4096, ttft_timeout_s=60, stall_timeout_s=30, timeout_s=120),
        Candidate(provider="hf", model="openai/gpt-oss-120b:deepinfra", kind="hf_router", base_url=HF_ROUTER_BASE,
                  key_env="HF_TOKEN", key_file="~/.cache/huggingface/token", max_tokens=4096, ttft_timeout_s=60,
                  stall_timeout_s=30, timeout_s=120, usd_per_mtok_in=0.037, usd_per_mtok_out=0.17),
        Candidate(provider="hf", model="moonshotai/Kimi-K2.7-Code:deepinfra", kind="hf_router", base_url=HF_ROUTER_BASE,
                  key_env="HF_TOKEN", key_file="~/.cache/huggingface/token", max_tokens=2048, ttft_timeout_s=60,
                  stall_timeout_s=30, timeout_s=120, usd_per_mtok_in=0.68, usd_per_mtok_out=3.4),
    ]


def tgi_candidate() -> Candidate:
    base = os.environ.get("TGI_BASE_URL", "http://127.0.0.1:8090").rstrip("/")
    return Candidate(provider="tgi", model="Qwen/Qwen2.5-Coder-3B-Instruct-AWQ", kind="tgi", base_url=base + "/v1",
                     placement="gpu_full", rung="local_specialist", max_tokens=768, ttft_timeout_s=90, stall_timeout_s=20,
                     timeout_s=180)


def tgi_chain() -> list[Candidate]:
    """TGI first (local GPU, $0); Ollama excluded while TGI holds the GPU; cloud fallback as in the earlier proof."""
    cloud = [c for c in candidates() if c.provider in {"nim", "hf"} and c.model in {
        "nvidia/nemotron-3.5-lightning-30b-a3b", "openai/gpt-oss-120b:deepinfra", "moonshotai/Kimi-K2.7-Code:deepinfra"}]
    return [tgi_candidate(), *cloud]


def run_task(client: GovernedModelClient, name: str, run_id: str, workdir: Path) -> dict:
    task = gl.TASKS[name]
    root = gl.make_repo(workdir, name)
    failure = run_verify(task["verify"], root)["output"]
    messages = edits_messages(gl.context_files(root), failure, target=task["target"])
    verdicts: list[dict] = []

    def verify(value):
        edits = value.get("edits") if isinstance(value, dict) else None
        wt = workdir / name / f"wt{len(verdicts)}"
        check = gl.apply_and_verify(root, name, edits, wt)
        hidden = gl.hidden_check(wt, name) if check.get("passed") else {"passed": False}
        v = {"passed": bool(check.get("passed") and hidden.get("passed")), "visible_passed": bool(check.get("passed")),
             "hidden_passed": bool(hidden.get("passed")), "reason": check.get("reason") or ("" if hidden.get("passed") else "hidden_check_failed"),
             "files_changed": len(check.get("changed") or []),
             "feedback": (check.get("output_tail") or "") if not check.get("passed") else ("hidden intent check failed: the "
                         "old symbol must be gone and every caller updated" if not hidden.get("passed") else "")}
        verdicts.append(v)
        return v

    started = time.perf_counter()
    res = asyncio.run(client.complete(family=task["family"], messages=messages, schema=EDITS_SCHEMA, verify=verify, run_id=run_id))
    files = [p for p in task["files"] if not Path(p).name.startswith("test_")]
    return {"task": name, "family": task["family"], "source_files": len(files), "wall_s": round(time.perf_counter() - started, 2),
            **res.public(), "verdicts": [{**{k: v for k, v in d.items() if k != "feedback"}, "had_feedback": bool(d.get("feedback"))}
                                         for d in verdicts]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["routed", "h2h", "all", "hard", "tgi", "hf-smoke", "provider-smoke", "provider-hard"], default="all")
    ap.add_argument("--h2h-models", default="")
    ap.add_argument("--providers", default="fireworks,hyperbolic,replicate")
    ap.add_argument("--models", default="", help="comma list of candidate model ids (provider-hard)")
    args = ap.parse_args()
    SecretVault().load(override=False)  # loads NVIDIA_API_KEY into this process only; never printed
    os.environ["BEAST_GOVERNED_INTERCEPTION"] = "1"
    os.environ["BEAST_CAPABILITY_ROUTER"] = "1"
    OUT.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    receipts = GovernorReceiptLog(STATE / f"proof-receipts-{stamp}.jsonl")
    governor = ComputeGovernorSpine(receipts=receipts, enforce=True)
    scorecard = CapabilityScorecard(STATE / "capability_scorecard.json")
    breaker = CircuitBreaker(open_after=2, cooldown_s=600)
    rows = {"routed": [], "h2h": []}
    with tempfile.TemporaryDirectory(prefix="beast-governed-proof-") as tmp:
        work = Path(tmp)
        if args.phase in {"provider-smoke", "provider-hard"}:
            import dataclasses
            from app.kernel.compute.governed_client import provider_lane_candidates
            out = OUT.parent / "providers"
            out.mkdir(parents=True, exist_ok=True)
            cands = provider_lane_candidates(providers=[p for p in args.providers.split(",") if p])
            if "hf" in args.providers.split(","):
                from app.kernel.compute.governed_client import hf_router_candidates
                cands += hf_router_candidates()
            if args.phase == "provider-smoke":
                msgs = [{"role": "system", "content": "Reply only with the JSON edits object."},
                        {"role": "user", "content": "File cfg.py contains exactly: TIMEOUT = 10\nChange TIMEOUT to 30. "
                                                    "Return {\"edits\": [{\"path\", \"old_text\", \"new_text\"}]}."}]

                def ok(value):
                    e = (value or {}).get("edits") or [{}]
                    good = e[0].get("path") == "cfg.py" and "10" in e[0].get("old_text", "") and "30" in e[0].get("new_text", "")
                    return {"passed": bool(good), "reason": "" if good else "wrong_edit"}

                rows["provider_smoke"] = []
                only = [m for m in args.models.split(",") if m]
                for cand in cands:
                    if only and cand.model not in only:
                        continue
                    cand = dataclasses.replace(cand, max_tokens=min(cand.max_tokens, 512))
                    solo = GovernedModelClient([cand], scorecard=scorecard, governor=governor, breaker=breaker,
                                               use_scorecard=False, max_attempts=1)
                    res = asyncio.run(solo.complete(family="smoke-tiny", messages=msgs, schema=EDITS_SCHEMA, verify=ok,
                                                    run_id=f"provider-smoke:{cand.provider}:{cand.model}"))
                    c = res.public()["calls"][0] if res.calls else {}
                    row = {"provider": cand.provider, "route": cand.model, "accepted": res.accepted, **{k: c.get(k) for k in (
                        "status", "json_valid", "dialect", "early_stop", "ttft_ms", "latency_ms", "tokens_prompt",
                        "tokens_completion", "tokens_estimated", "spend_usd", "error")}}
                    rows["provider_smoke"].append(row)
                    print(json.dumps(row), flush=True)
                    (out / f"provider-smoke-{stamp}.json").write_text(json.dumps(rows["provider_smoke"], indent=1))
            else:
                wanted = [m for m in args.models.split(",") if m]
                chain = [c for c in cands if c.model in wanted]
                for cand in chain:
                    solo = GovernedModelClient([cand, cand], scorecard=scorecard, governor=governor, breaker=breaker,
                                               use_scorecard=False, max_attempts=2, feedback_turns=True)
                    rows.setdefault("provider_hard", [])
                    for name in list(dict.fromkeys(ROUTED_TASKS + H2H_TASKS)):
                        row = run_task(solo, name, f"provider-hard:{cand.model}:{name}", work)
                        row["candidate"] = cand.ident
                        rows["provider_hard"].append(row)
                        print(json.dumps({"cand": cand.ident, **{k: row[k] for k in ("task", "accepted", "model_calls", "wall_s")},
                                          "spend": round(sum(c["spend_usd"] for c in row["calls"]), 6)}), flush=True)
                        (out / f"provider-hard-{stamp}.json").write_text(json.dumps(rows["provider_hard"], indent=1))
            (out / f"scorecard-{args.phase}-{stamp}.json").write_text(json.dumps(scorecard.snapshot(), indent=1))
            (out / f"receipt-chain-{args.phase}-{stamp}.json").write_text(json.dumps(receipts.verify() | {"path": str(receipts.path.relative_to(ROOT))}, indent=1))
            print(json.dumps({"stamp": stamp, "chain": receipts.verify()}))
            return 0
        if args.phase == "hf-smoke":
            # Approved HF-router lanes: 1 tiny schema-forced call per (model, provider), minimal tokens.
            import dataclasses
            from app.kernel.compute.governed_client import hf_router_candidates
            out = OUT.parent / "tgi"
            out.mkdir(parents=True, exist_ok=True)
            msgs = [{"role": "system", "content": "Reply only with the JSON edits object."},
                    {"role": "user", "content": "File cfg.py contains exactly: TIMEOUT = 10\nChange TIMEOUT to 30. "
                                                "Return {\"edits\": [{\"path\", \"old_text\", \"new_text\"}]}."}]

            def ok(value):
                e = (value or {}).get("edits") or [{}]
                good = e[0].get("path") == "cfg.py" and "10" in e[0].get("old_text", "") and "30" in e[0].get("new_text", "")
                return {"passed": bool(good), "reason": "" if good else "wrong_edit"}

            rows["hf_smoke"] = []
            for cand in hf_router_candidates():
                cand = dataclasses.replace(cand, max_tokens=256)
                solo = GovernedModelClient([cand], scorecard=scorecard, governor=governor, breaker=breaker,
                                           use_scorecard=False, max_attempts=1)
                res = asyncio.run(solo.complete(family="smoke-tiny", messages=msgs, schema=EDITS_SCHEMA, verify=ok,
                                                run_id=f"hf-smoke:{cand.model}"))
                c = res.public()["calls"][0] if res.calls else {}
                row = {"route": cand.model, "accepted": res.accepted, **{k: c.get(k) for k in (
                    "status", "json_valid", "dialect", "early_stop", "ttft_ms", "latency_ms", "tokens_prompt",
                    "tokens_completion", "tokens_estimated", "spend_usd", "error")}}
                rows["hf_smoke"].append(row)
                print(json.dumps(row), flush=True)
                (out / f"hf-smoke-{stamp}.json").write_text(json.dumps(rows["hf_smoke"], indent=1))
            (out / f"scorecard-hf-smoke-{stamp}.json").write_text(json.dumps(scorecard.snapshot(), indent=1))
            (out / f"receipt-chain-hf-smoke-{stamp}.json").write_text(json.dumps(receipts.verify() | {"path": str(receipts.path.relative_to(ROOT))}, indent=1))
            print(json.dumps({"stamp": stamp, "chain": receipts.verify(), "spend_usd": round(sum(r["spend_usd"] or 0 for r in rows["hf_smoke"]), 6)}))
            return 0
        if args.phase == "tgi":
            out = OUT.parent / "tgi"
            out.mkdir(parents=True, exist_ok=True)
            from app.kernel.compute.governed_client import tgi_available
            if not tgi_available(tgi_candidate().base_url[:-3]):
                raise SystemExit("TGI /health not 200; refusing to run the tgi phase")
            tasks = list(dict.fromkeys(ROUTED_TASKS + H2H_TASKS))
            solo = GovernedModelClient([tgi_candidate()], scorecard=scorecard, governor=governor, breaker=breaker,
                                       use_scorecard=False, max_attempts=1)
            rows["tgi_solo"] = []
            for name in tasks:
                row = run_task(solo, name, f"tgi-solo:{name}", work)
                rows["tgi_solo"].append(row)
                print(json.dumps({"solo": "tgi", **{k: row[k] for k in ("task", "accepted", "model_calls", "wall_s")}}), flush=True)
                (out / f"tgi-solo-{stamp}.json").write_text(json.dumps(rows["tgi_solo"], indent=1))
            chain = GovernedModelClient(tgi_chain(), scorecard=scorecard, governor=governor, breaker=breaker,
                                        use_scorecard=False, max_attempts=4, feedback_turns=True)
            rows["tgi_routed"] = []
            for name in tasks:
                row = run_task(chain, name, f"tgi-routed:{name}", work)
                rows["tgi_routed"].append(row)
                print(json.dumps({"routed": "tgi-first", **{k: row[k] for k in ("task", "accepted", "accepted_by", "model_calls", "wall_s")}}), flush=True)
                (out / f"tgi-routed-{stamp}.json").write_text(json.dumps(rows["tgi_routed"], indent=1))
            (out / f"scorecard-{stamp}.json").write_text(json.dumps(scorecard.snapshot(), indent=1))
            (out / f"receipt-chain-{stamp}.json").write_text(json.dumps(receipts.verify() | {"path": str(receipts.path.relative_to(ROOT))}, indent=1))
            print(json.dumps({"stamp": stamp, "chain": receipts.verify()}))
            return 0
        if args.phase in {"routed", "all"}:
            client = GovernedModelClient(candidates(), scorecard=scorecard, governor=governor, breaker=breaker,
                                         use_scorecard=True, max_attempts=3)
            for name in ROUTED_TASKS:
                row = run_task(client, name, f"routed:{name}", work)
                rows["routed"].append(row)
                print(json.dumps({k: row[k] for k in ("task", "accepted", "accepted_by", "model_calls", "wall_s")}), flush=True)
                (OUT / f"routed-{stamp}.json").write_text(json.dumps(rows["routed"], indent=1))
        if args.phase == "hard":
            # Re-run of the tasks no model solved in the routed/h2h runs, now with verifier feedback turns.
            client = GovernedModelClient(candidates(), scorecard=scorecard, governor=governor, breaker=breaker,
                                         use_scorecard=True, max_attempts=4, feedback_turns=True)
            for name in HARD_TASKS:
                row = run_task(client, name, f"hard:{name}", work)
                rows["routed"].append(row)
                print(json.dumps({k: row[k] for k in ("task", "accepted", "accepted_by", "model_calls", "wall_s")}), flush=True)
                (OUT / f"hard-{stamp}.json").write_text(json.dumps(rows["routed"], indent=1))
        if args.phase in {"h2h", "all"}:
            wanted = [m for m in args.h2h_models.split(",") if m]
            for cand in candidates():
                if wanted and cand.model not in wanted:
                    continue
                solo = GovernedModelClient([cand], scorecard=scorecard, governor=governor, breaker=breaker,
                                           use_scorecard=False, max_attempts=1)
                for name in H2H_TASKS:
                    row = run_task(solo, name, f"h2h:{cand.model}:{name}", work)
                    row["candidate"] = cand.ident
                    rows["h2h"].append(row)
                    c = row["calls"][0] if row["calls"] else {}
                    print(json.dumps({"h2h": cand.ident, "task": name, "status": c.get("status"), "json_valid": c.get("json_valid"),
                                      "accepted": row["accepted"]}), flush=True)
                    (OUT / f"h2h-{stamp}.json").write_text(json.dumps(rows["h2h"], indent=1))
    (OUT / f"scorecard-{stamp}.json").write_text(json.dumps(scorecard.snapshot(), indent=1))
    (OUT / f"receipt-chain-{stamp}.json").write_text(json.dumps(receipts.verify() | {"path": str(receipts.path.relative_to(ROOT))}, indent=1))
    print(json.dumps({"stamp": stamp, "chain": receipts.verify()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
