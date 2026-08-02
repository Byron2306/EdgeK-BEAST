#!/usr/bin/env python3
"""Plan, preflight, and execute the preregistered PGEC 450 matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROTOCOL_PATH = ROOT / "experiments" / "pgec_450" / "protocol.json"
RUN_ROOT = ROOT / "benchmarks" / "results" / "pgec_450_runs"
PROVIDER_ENV_PATH = ROOT / ".beast" / "provider_secrets.env"
DEFAULT_STATE_ROOT = ROOT / "benchmarks" / "state" / "pgec_450"
LANE_STORE_LABELS = {
    "raw": "raw",
    "beast_no_compute_governor": "governed_no_pgec",
    "full_beast_compute_governor": "full_pgec",
}


def load_protocol() -> Dict[str, Any]:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_provider_env(path: Path = PROVIDER_ENV_PATH) -> None:
    if not path.exists():
        return
    pattern = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = pattern.match(line)
        if not match:
            continue
        key, value = match.groups()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def inject_ollama_preset(protocol: Dict[str, Any]) -> None:
    from benchmarks import beast_systems_benchmark as systems

    cfg = protocol["route_contract"]["ollama"]
    systems.LIVE_PROVIDER_PRESETS["ollama"] = systems.LiveProvider(
        name="ollama",
        base_url=os.environ.get(cfg["base_url_env"], cfg["default_base_url"]),
        model=os.environ.get(cfg["model_env"], cfg["default_model"]),
        api_key_env=cfg["api_key_env"],
        timeout=float(cfg["timeout_seconds"]),
    )
    os.environ.setdefault(cfg["api_key_env"], "ollama-local")


def crystallization_policy(protocol: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "minimum_verified_occurrences": 2,
        "minimum_independent_hidden_passes": 2,
        "require_effect_hash_agreement": True,
        "require_same_verifier_contract": True,
        "require_same_tool_schema": True,
        "allow_provider_clean": True,
        "allow_deterministic_local": True,
        "allow_rescued": {
            "enabled": True,
            "minimum_verified_occurrences": 3,
        },
        "first_shadow_reuse_occurrence": 3,
        "first_active_reuse_occurrence": 5,
        "mutation_challenge_occurrence": 10,
        "false_reuse_tolerance": 0,
        "policy_generation": "pgec_450_policy_v1",
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "routes": list(protocol["design"]["routes"]),
        "families": list(protocol["design"]["task_families"]),
        "lanes": list(protocol["design"]["lanes"]),
    }


def stable_family_identity(protocol: Dict[str, Any], family: str) -> Dict[str, Any]:
    verifier_contract = sha256_text(f"verifier:{family}:v1")
    tool_schema = sha256_text(f"tool_schema:{family}:v1")
    policy = crystallization_policy(protocol)
    payload = {
        "task_family": family,
        "action_schema_version": "v1",
        "verifier_contract": verifier_contract,
        "tool_schema": tool_schema,
        "policy_class": "pgec_controlled_matrix",
        "workspace_domain": "edgek_beast_repo",
    }
    return {
        "family": family,
        "crystal_key": "sha256:" + sha256_text(canonical_json(payload)),
        "verifier_contract_digest": verifier_contract,
        "tool_schema_digest": tool_schema,
        "policy_generation": policy["policy_generation"],
        "workspace_domain": payload["workspace_domain"],
    }


def state_root_for(args: argparse.Namespace) -> Path:
    root = Path(getattr(args, "state_root", "") or DEFAULT_STATE_ROOT).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root


def provider_state_dir(args: argparse.Namespace, provider: str) -> Path:
    path = state_root_for(args) / provider
    path.mkdir(parents=True, exist_ok=True)
    return path


def lane_state_dirs_from_provider_dir(
    provider_dir: Path,
    protocol: Dict[str, Any],
    families: List[str] | None = None,
) -> Dict[str, str]:
    dirs: Dict[str, str] = {}
    selected_families = [str(item) for item in (families or []) if str(item)]
    single_family = selected_families[0] if len(selected_families) == 1 else ""
    for lane in protocol["design"]["lanes"]:
        label = LANE_STORE_LABELS.get(lane, lane)
        path = provider_dir / label
        if single_family:
            path = path / single_family
        path.mkdir(parents=True, exist_ok=True)
        dirs[lane] = str(path)
    return dirs


def lane_state_dirs(
    args: argparse.Namespace,
    provider: str,
    protocol: Dict[str, Any],
    families: List[str] | None = None,
) -> Dict[str, str]:
    return lane_state_dirs_from_provider_dir(provider_state_dir(args, provider), protocol, families=families)


def continuity_checkpoint_path(args: argparse.Namespace, provider: str) -> Path:
    return provider_state_dir(args, provider) / "continuity_checkpoint.json"


def load_continuity_checkpoint(args: argparse.Namespace, provider: str) -> Dict[str, Any]:
    path = continuity_checkpoint_path(args, provider)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_continuity_checkpoint(args: argparse.Namespace, provider: str, payload: Dict[str, Any]) -> None:
    path = continuity_checkpoint_path(args, provider)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def infer_resume_source(args: argparse.Namespace, provider: str, run_id: str, batch_index: int) -> str | None:
    explicit = str(getattr(args, "resume_from", "") or "").strip()
    if explicit:
        return explicit
    if batch_index <= 0:
        return None
    checkpoint = load_continuity_checkpoint(args, provider)
    if str(checkpoint.get("run_id") or "") != run_id:
        return None
    previous_batch = int(checkpoint.get("batch_index") or -1)
    source = str(checkpoint.get("live_execution") or "")
    if previous_batch == batch_index - 1 and source:
        return source
    candidate = RUN_ROOT / f"pilot_{run_id}_b{batch_index-1:03d}" / "live_execution.json"
    if candidate.exists():
        return str(candidate)
    return None


def continuity_report(
    protocol: Dict[str, Any],
    provider: str,
    run_id: str,
    state_dir: Path,
    resume_source: str | None,
    batch_index: int,
    families: List[str] | None = None,
) -> Dict[str, Any]:
    policy = crystallization_policy(protocol)
    lane_dirs = lane_state_dirs_from_provider_dir(state_dir, protocol, families=families)
    ordered_occurrences = list(protocol["design"]["occurrence_points"])
    report: Dict[str, Any] = {
        "beast_object_type": "pgec_450_continuity_preflight",
        "version": "1.1",
        "generated_at": utc_now(),
        "experiment_id": run_id,
        "provider": provider,
        "run_id": run_id,
        "batch_index": batch_index,
        "state_dir": str(state_dir),
        "same_experiment_id": True,
        "same_state_store": True,
        "same_policy_generation": True,
        "same_verifier_contract": True,
        "policy_generation": policy["policy_generation"],
        "promotion_policy": {
            "minimum_verified_occurrences": policy["minimum_verified_occurrences"],
            "minimum_independent_hidden_passes": policy["minimum_independent_hidden_passes"],
            "first_shadow_reuse_occurrence": policy["first_shadow_reuse_occurrence"],
            "first_active_reuse_occurrence": policy["first_active_reuse_occurrence"],
            "mutation_challenge_occurrence": policy["mutation_challenge_occurrence"],
            "rescued_policy": policy["allow_rescued"],
        },
        "occurrence_order": ordered_occurrences,
        "lane_state_dirs": lane_dirs,
        "resume_source": resume_source,
        "families": {},
        "blocked_reasons": [],
    }
    resume_rows: List[Dict[str, Any]] = []
    if resume_source:
        try:
            payload = json.loads(Path(resume_source).read_text(encoding="utf-8"))
            resume_rows = list(payload.get("controlled_observations") or [])
        except Exception:
            report["blocked_reasons"].append("resume_source_unreadable")
    for family in protocol["design"]["task_families"]:
        identity = stable_family_identity(protocol, family)
        prior_occurrences_found = 0
        candidate_state = "observed"
        prior = sorted({
            int(row.get("occurrence"))
            for row in resume_rows
            if row.get("provider") == provider
            and row.get("family") == family
            and row.get("lane") == "full_beast_compute_governor"
            and row.get("completed")
        })
        prior_occurrences_found = len(prior)
        if 1 in prior and 2 in prior:
            candidate_state = "verified_candidate"
        elif 1 in prior:
            candidate_state = "candidate"
        contiguous_prefix: List[int] = []
        for occurrence in ordered_occurrences:
            if occurrence in prior:
                contiguous_prefix.append(occurrence)
            else:
                break
        next_expected = None
        if len(contiguous_prefix) < len(ordered_occurrences):
            next_expected = ordered_occurrences[len(contiguous_prefix)]
        reuse_windows = {
            "shadow_reuse_ready": policy["first_shadow_reuse_occurrence"] in prior or contiguous_prefix[:2] == [1, 2],
            "active_reuse_ready": policy["first_active_reuse_occurrence"] in prior,
            "mutation_challenge_seen": policy["mutation_challenge_occurrence"] in prior,
        }
        report["families"][family] = identity | {
            "prior_occurrences_found": prior_occurrences_found,
            "prior_occurrences": prior,
            "contiguous_prefix": contiguous_prefix,
            "next_expected_occurrence": next_expected,
            "candidate_state": candidate_state,
            "reuse_windows": reuse_windows,
            "family_fingerprint": "sha256:" + sha256_text(canonical_json({
                "family": family,
                "protocol_sha256": policy["protocol_sha256"],
                "task_family": family,
            })),
            "applicability_fingerprint": "sha256:" + sha256_text(canonical_json({
                "family": family,
                "workspace_domain": identity["workspace_domain"],
                "policy_generation": identity["policy_generation"],
                "provider": provider,
            })),
        }
    if batch_index > 0 and not resume_source:
        report["blocked_reasons"].append("state_store_missing_prior_occurrences")
    return report


def continuity_final_report(
    protocol: Dict[str, Any],
    provider: str,
    run_id: str,
    state_dir: Path,
    run_dir: Path,
    preflight: Dict[str, Any],
    batch_index: int,
    families: List[str] | None = None,
) -> Dict[str, Any]:
    ordered_occurrences = list(protocol["design"]["occurrence_points"])
    policy = crystallization_policy(protocol)
    report: Dict[str, Any] = {
        "beast_object_type": "pgec_450_continuity_final",
        "version": "1.1",
        "generated_at": utc_now(),
        "experiment_id": run_id,
        "provider": provider,
        "run_id": run_id,
        "batch_index": batch_index,
        "state_dir": str(state_dir),
        "lane_state_dirs": lane_state_dirs_from_provider_dir(state_dir, protocol, families=families),
        "policy_generation": policy["policy_generation"],
        "observed_occurrences": [],
        "contiguous_policy_sequence": False,
        "same_state_root": True,
        "same_family_fingerprint": False,
        "same_verifier_contract": False,
        "reuse_at": [],
        "mutation_challenge_at": policy["mutation_challenge_occurrence"],
        "passed": False,
        "blocked_reasons": [],
        "families": {},
        "preflight_ref": str(run_dir / "continuity_preflight.json"),
    }
    live_path = run_dir / "live_execution.json"
    if not live_path.exists():
        report["blocked_reasons"].append("live_execution_missing")
        return report
    try:
        payload = json.loads(live_path.read_text(encoding="utf-8"))
    except Exception:
        report["blocked_reasons"].append("live_execution_unreadable")
        return report

    rows = list(payload.get("controlled_observations") or [])
    diagnostics = list(payload.get("crystallization_diagnostics") or [])
    families = sorted({
        str(row.get("family"))
        for row in rows
        if row.get("provider") == provider and row.get("lane") == "full_beast_compute_governor"
    })
    if not families:
        report["blocked_reasons"].append("no_full_pgec_rows")
        return report

    for family in families:
        family_rows = [
            dict(row) for row in rows
            if row.get("provider") == provider
            and row.get("family") == family
            and row.get("lane") == "full_beast_compute_governor"
        ]
        family_rows.sort(key=lambda row: int(row.get("occurrence") or 0))
        observed = [int(row.get("occurrence") or 0) for row in family_rows]
        family_diags = [
            dict(item) for item in diagnostics
            if item.get("provider") == provider
            and item.get("family") == family
            and item.get("lane") == "full_beast_compute_governor"
        ]
        family_fingerprints = sorted({str(item.get("family_fingerprint") or "") for item in family_diags if item.get("family_fingerprint")})
        verifier_contracts = sorted({str(item.get("boundary_digest") or "") for item in family_diags if item.get("boundary_digest")})
        reuse_at = [
            int(row.get("occurrence") or 0)
            for row in family_rows
            if bool(row.get("deterministic_reuse")) and int(row.get("occurrence") or 0) < int(policy["mutation_challenge_occurrence"])
        ]
        contiguous = observed == ordered_occurrences[: len(observed)]
        family_passed = (
            observed == ordered_occurrences
            and contiguous
            and len(family_fingerprints) == 1
            and len(verifier_contracts) == 1
            and 3 in reuse_at
            and 5 in reuse_at
        )
        report["families"][family] = {
            "observed_occurrences": observed,
            "contiguous_policy_sequence": contiguous,
            "same_state_root": True,
            "same_family_fingerprint": len(family_fingerprints) == 1,
            "same_verifier_contract": len(verifier_contracts) == 1,
            "reuse_at": reuse_at,
            "mutation_challenge_at": policy["mutation_challenge_occurrence"],
            "passed": family_passed,
            "preflight_family": (preflight.get("families") or {}).get(family) or {},
        }

    primary_family = families[0]
    primary = report["families"][primary_family]
    report["family"] = primary_family
    report["observed_occurrences"] = list(primary["observed_occurrences"])
    report["contiguous_policy_sequence"] = bool(primary["contiguous_policy_sequence"])
    report["same_family_fingerprint"] = bool(primary["same_family_fingerprint"])
    report["same_verifier_contract"] = bool(primary["same_verifier_contract"])
    report["reuse_at"] = list(primary["reuse_at"])
    report["passed"] = bool(primary["passed"]) and not report["blocked_reasons"]
    if len(families) > 1:
        report["passed"] = report["passed"] and all(bool(item.get("passed")) for item in report["families"].values())
    return report


def plan_rows(protocol: Dict[str, Any], providers: List[str] | None = None) -> List[Dict[str, Any]]:
    from benchmarks.mega_test_tasks import build_observation_plan

    design = protocol["design"]
    selected = providers or list(design["routes"])
    return [row.to_dict() for row in build_observation_plan(
        providers=selected,
        families=design["task_families"],
        occurrences=design["occurrence_points"],
        lanes=design["lanes"],
        mode="controlled",
    )]


def selected_batch_families(
    protocol: Dict[str, Any],
    providers: List[str],
    batch_size: int,
    batch_index: int,
) -> List[str]:
    rows = plan_rows(protocol, providers=providers)
    start = int(batch_index) * int(batch_size)
    end = start + int(batch_size)
    batch = rows[start:end]
    return sorted({str(row.get("family")) for row in batch if row.get("family")})


def write_plan(protocol: Dict[str, Any]) -> Dict[str, Any]:
    inject_ollama_preset(protocol)
    rows = plan_rows(protocol)
    expected = int(protocol["design"]["expected_observations"])
    if len(rows) != expected:
        raise RuntimeError(f"Frozen matrix expected {expected} rows, generated {len(rows)}")
    out = ROOT / "benchmarks" / "results" / "pgec_450_preregistered"
    out.mkdir(parents=True, exist_ok=True)
    jsonl = out / "matrix_plan.jsonl"
    jsonl.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
    manifest = {
        "beast_object_type": "pgec_450_matrix_manifest",
        "version": "1.0",
        "generated_at": utc_now(),
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "matrix_sha256": sha256_file(jsonl),
        "observations": len(rows),
        "dimensions": protocol["design"],
        "confirmatory": True,
    }
    (out / "matrix_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def http_probe(url: str, timeout: float = 3.0) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return {"reachable": True, "status": int(response.status)}
    except urllib.error.HTTPError as exc:
        return {"reachable": True, "status": int(exc.code)}
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}


def preflight(protocol: Dict[str, Any]) -> Dict[str, Any]:
    load_provider_env()
    inject_ollama_preset(protocol)
    from benchmarks.beast_systems_benchmark import provider_from_preset

    routes: Dict[str, Any] = {}
    for route in protocol["design"]["routes"]:
        provider = provider_from_preset(route)
        env_names = [item.strip() for item in provider.api_key_env.split(",") if item.strip()]
        secret_present = route == "ollama" or any(bool(os.environ.get(name)) for name in env_names)
        route_result: Dict[str, Any] = {
            "route": route,
            "base_url": provider.base_url,
            "model": provider.model,
            "credential_present": secret_present,
            "configured": secret_present,
        }
        if route == "ollama":
            openai_probe = http_probe(provider.base_url.rstrip("/") + "/models")
            native_base = provider.base_url.rstrip("/")
            if native_base.endswith("/v1"):
                native_base = native_base[:-3]
            native_probe = http_probe(native_base.rstrip("/") + "/api/tags")
            route_result["probe"] = {
                "openai_models": openai_probe,
                "native_tags": native_probe,
            }
            route_result["configured"] = bool(openai_probe.get("reachable") or native_probe.get("reachable"))
        routes[route] = route_result
    result = {
        "beast_object_type": "pgec_450_preflight",
        "version": "1.0",
        "generated_at": utc_now(),
        "host": socket.gethostname(),
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "routes": routes,
        "ready_routes": [name for name, row in routes.items() if row["configured"]],
        "all_routes_ready": all(row["configured"] for row in routes.values()),
    }
    return result


def run_batch(args: argparse.Namespace, protocol: Dict[str, Any]) -> int:
    inject_ollama_preset(protocol)
    providers = args.providers.split(",") if args.providers else list(protocol["design"]["routes"])
    providers = [p.strip() for p in providers if p.strip()]
    unknown = sorted(set(providers) - set(protocol["design"]["routes"]))
    if unknown:
        raise SystemExit(f"Routes outside preregistration: {', '.join(unknown)}")
    if providers != protocol["design"]["routes"] and not args.pilot:
        raise SystemExit("Subset route execution requires --pilot; pilot cells cannot replace confirmatory cells.")

    from benchmarks import beast_definitive_mega_test as mega

    run_id = args.run_id or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    label = "pilot" if args.pilot else "confirmatory"
    if len(providers) != 1:
        raise SystemExit("PGEC state continuity currently requires a single provider per run invocation.")
    provider_id = providers[0]
    state_dir = provider_state_dir(args, provider_id)
    batch_families = selected_batch_families(protocol, providers, args.batch_size, args.batch_index)
    resume_source = infer_resume_source(args, provider_id, run_id, args.batch_index)
    continuity = continuity_report(protocol, provider_id, run_id, state_dir, resume_source, args.batch_index, families=batch_families)
    if args.batch_index > 0 and continuity["blocked_reasons"]:
        raise SystemExit(
            "Refusing to continue PGEC batch continuity because the continuity preflight is blocked: "
            + ", ".join(continuity["blocked_reasons"])
        )
    os.environ["BEAST_PGEC_STATE_DIR"] = str(state_dir)
    os.environ["BEAST_PGEC_EXPERIMENT_ID"] = str(run_id)
    for lane, lane_dir in lane_state_dirs(args, provider_id, protocol, families=batch_families).items():
        env_key = f"BEAST_PGEC_STATE_DIR_{re.sub(r'[^A-Z0-9]+', '_', lane.upper())}"
        os.environ[env_key] = lane_dir
    os.environ["BEAST_PGEC_POLICY_GENERATION"] = str(crystallization_policy(protocol)["policy_generation"])
    output_name = f"pgec_450_runs/{label}_{run_id}_b{args.batch_index:03d}"
    argv = [
        "--mode", "controlled",
        "--providers", ",".join(providers),
        "--families", ",".join(protocol["design"]["task_families"]),
        "--occurrences", ",".join(str(v) for v in protocol["design"]["occurrence_points"]),
        "--lanes", ",".join(protocol["design"]["lanes"]),
        "--batch-size", str(args.batch_size),
        "--batch-index", str(args.batch_index),
        "--output", output_name,
        "--skip-crystal-phases",
    ]
    if args.live:
        argv.append("--live")
    else:
        argv.append("--dry-run")
    if resume_source:
        argv += ["--resume-from", resume_source]
    if args.cross_source_provider:
        argv += ["--cross-source-provider", args.cross_source_provider]

    rc = mega.main(argv)
    run_dir = ROOT / "benchmarks" / "results" / output_name
    metadata = {
        "beast_object_type": "pgec_450_batch_registration",
        "version": "1.0",
        "run_id": run_id,
        "classification": label,
        "generated_at": utc_now(),
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "providers": providers,
        "batch_size": args.batch_size,
        "batch_index": args.batch_index,
        "live": bool(args.live),
        "return_code": rc,
        "state_dir": str(state_dir),
        "resume_source": resume_source,
    }
    if run_dir.exists():
        (run_dir / "pgec_registration.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (run_dir / "continuity_preflight.json").write_text(json.dumps(continuity, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        final_continuity = continuity_final_report(protocol, provider_id, run_id, state_dir, run_dir, continuity, args.batch_index, families=batch_families)
        (run_dir / "continuity_final.json").write_text(json.dumps(final_continuity, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        save_continuity_checkpoint(args, provider_id, {
            "run_id": run_id,
            "batch_index": args.batch_index,
            "live_execution": str(run_dir / "live_execution.json"),
            "state_dir": str(state_dir),
            "policy_generation": crystallization_policy(protocol)["policy_generation"],
            "updated_at": utc_now(),
        })
    return int(rc)


def main() -> int:
    load_provider_env()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    sub.add_parser("preflight")
    run = sub.add_parser("run")
    run.add_argument("--providers", default=None)
    run.add_argument("--batch-size", type=int, default=15)
    run.add_argument("--batch-index", type=int, required=True)
    run.add_argument("--run-id", default=None)
    run.add_argument("--live", action="store_true", default=True)
    run.add_argument("--dry-run", dest="live", action="store_false")
    run.add_argument("--pilot", action="store_true")
    run.add_argument("--resume-from", default=None)
    run.add_argument("--cross-source-provider", default=None)
    run.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    args = parser.parse_args()
    protocol = load_protocol()
    if args.command == "plan":
        print(json.dumps(write_plan(protocol), indent=2, sort_keys=True))
        return 0
    if args.command == "preflight":
        print(json.dumps(preflight(protocol), indent=2, sort_keys=True))
        return 0
    return run_batch(args, protocol)


if __name__ == "__main__":
    raise SystemExit(main())
