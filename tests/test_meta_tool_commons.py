import hashlib
import json

import pytest

from app.kernel.capability.capability_exchange import CapabilityExchange
from app.kernel.networking.meta_tool_commons import MetaToolCommons
from app.kernel.capability.skill_registry import SkillRegistry


def _evidence(exchange, capability_id="search", task_class="debug", role="scout", **outcome):
    return exchange.prepare(
        {"capability_id": capability_id, "kind": "tool", "version": "1", "schema_hash": "sha256:schema"},
        {
            "task_class": task_class, "role": role, "verified": True, "useful": True,
            "hidden_clean": False, "safe": True, "latency_ms": 20, **outcome,
        },
    )


def test_ingest_deduplicates_and_rejects_tampered_evidence(tmp_path):
    exchange = CapabilityExchange(enabled=False, data_dir=str(tmp_path / "exchange"))
    commons = MetaToolCommons(db_path=str(tmp_path / "commons.db"), exchange=exchange)
    valid = _evidence(exchange)
    tampered = dict(valid)
    tampered["outcome"] = {**valid["outcome"], "verified": False}

    result = commons.ingest([valid, valid, tampered])

    assert result["accepted"] == 1
    assert result["duplicates"] == 1
    assert len(result["rejected"]) == 1
    assert commons.state()["evidence_count"] == 1


def test_rank_is_contextual_schema_pinned_and_caps_contributors(tmp_path):
    exchange = CapabilityExchange(enabled=False)
    commons = MetaToolCommons(db_path=str(tmp_path / "commons.db"), exchange=exchange, contributor_sample_cap=2)
    debug_rows = [_evidence(exchange) for _ in range(5)]
    # Each envelope needs a distinct hash while retaining the same contributor.
    for index, row in enumerate(debug_rows):
        row["created_at"] = f"2026-01-01T00:00:0{index}+00:00"
        source = dict(row)
        source.pop("evidence_hash", None)
        source.pop("signature", None)
        canonical = json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        row["evidence_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    other = _evidence(exchange, task_class="docs")
    commons.ingest(debug_rows + [other])

    ranked = commons.rank(task_class="debug", role="scout")

    assert ranked["count"] == 1
    assert ranked["rankings"][0]["sample_size"] == 2
    assert ranked["anti_gaming"]["suppressed_samples"] == 3
    assert ranked["anti_gaming"]["schema_pinning"] is True
    assert ranked["authority"] == "advisory_global_prior_local_policy_decides"


def test_candidate_adoption_requires_local_approval(tmp_path):
    registry = SkillRegistry(db_path=str(tmp_path / "skills.db"))
    commons = MetaToolCommons(db_path=str(tmp_path / "commons.db"), skill_registry=registry)
    proposed = commons.propose({
        "kind": "meta_tool_recipe", "name": "targeted_test_runner", "schema_hash": "sha256:recipe",
        "task_class": "debug", "role": "verification", "risk_class": "medium",
        "pattern": {"task_class": "debug"}, "action": {"tools": ["pytest"]},
    }, source="global")

    dry = commons.adopt(proposed["candidate_id"], approved=True, dry_run=True)
    denied = commons.adopt(proposed["candidate_id"], approved=False, dry_run=False)
    adopted = commons.adopt(proposed["candidate_id"], approved=True, dry_run=False, approved_by="byron")

    assert proposed["auto_adopted"] is False
    assert dry["adopted"] is False
    assert denied["adopted"] is False
    assert adopted["adopted"] is True
    assert registry.get_skills(category="meta_tool_commons")[0].name == "targeted_test_runner"


def test_proposal_requires_schema_pin_and_blocks_critical_adoption(tmp_path):
    registry = SkillRegistry(db_path=str(tmp_path / "skills.db"))
    commons = MetaToolCommons(db_path=str(tmp_path / "commons.db"), skill_registry=registry)
    with pytest.raises(ValueError, match="schema_hash"):
        commons.propose({"kind": "skill", "name": "unpinned"})
    proposed = commons.propose({
        "kind": "skill", "name": "dangerous", "schema_hash": "sha256:danger", "risk_class": "critical"
    })
    result = commons.adopt(proposed["candidate_id"], approved=True, dry_run=False)
    assert result["adopted"] is False
    assert "risk class" in result["reason"]


def test_snapshot_has_reproducible_integrity_hash(tmp_path):
    commons = MetaToolCommons(db_path=str(tmp_path / "commons.db"))
    snapshot = commons.snapshot(task_class="debug", role="scout")
    source = dict(snapshot)
    declared = source.pop("snapshot_hash")
    canonical = json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert declared == "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    assert snapshot["policy"]["local_approval_required"] is True


def test_swarm_evidence_stages_local_skill_recipe_candidate(tmp_path):
    registry = SkillRegistry(db_path=str(tmp_path / "skills.db"))
    commons = MetaToolCommons(db_path=str(tmp_path / "commons.db"), skill_registry=registry)
    run = {
        "run_id": "swarm_run_1",
        "status": "ready",
        "state": "completed",
        "task_type": "code_change",
        "risk_level": "low",
        "created_at": "2026-06-21T00:00:00Z",
        "updated_at": "2026-06-21T00:01:00Z",
        "metadata": {"profile": "openclaw"},
        "plan": [{"role": "cartographer", "action": "select_relevant_context"}],
        "gates": [{"decision": "allow"}],
        "value": {"tokens_saved": 12, "cost_saved_usd": 0.001},
    }
    second = {**run, "run_id": "swarm_run_2", "updated_at": "2026-06-21T00:02:00Z"}

    ingest = commons.ingest_swarm_runs([run, second])
    proposed = commons.propose_swarm_candidates(task_class="code_change", role="cartographer", min_samples=2)
    listed = commons.candidates(source="local_swarm_commons")

    assert ingest["accepted"] == 2
    assert proposed["proposed_count"] == 1
    assert listed["count"] == 1
    candidate = listed["candidates"][0]["candidate"]
    assert listed["candidates"][0]["kind"] == "skill_recipe"
    assert candidate["action"]["type"] == "swarm_role_recipe"
    assert candidate["action"]["profile"] == "openclaw"
    assert candidate["pattern"]["sample_size"] == 2
    assert candidate["pattern"]["safe_rate"] == 1.0

    adopted = commons.adopt(
        listed["candidates"][0]["candidate_id"],
        approved=True,
        dry_run=False,
        approved_by="tester",
        reason="promote local swarm recipe",
    )

    assert adopted["adopted"] is True
    skills = registry.get_skills(category="swarm_recipe")
    assert len(skills) == 1
    assert skills[0].action["type"] == "swarm_role_recipe"
    assert skills[0].action["role"] == "cartographer"
    assert skills[0].metadata["source"] == "local_swarm_commons"


def test_cli_execution_ingests_local_commons_evidence(tmp_path):
    commons = MetaToolCommons(db_path=str(tmp_path / "commons.db"))
    execution = {
        "beast_object_type": "beast_cli_execution",
        "status": "dry_run",
        "reason": "BEAST CLI executor completed",
        "plan": {
            "mode": "openclaw",
            "profile": {"mode": "openclaw"},
            "created_at": "2026-06-21T00:00:00Z",
            "plan_hash": "sha256:plan",
            "canon": {"task_class": "agentic_cli"},
            "actions": [
                {"action_id": "prepare_task", "kind": "mcp_request", "role": "cartographer", "risk": "read_only"},
                {"action_id": "run_verification", "kind": "mcp_request", "role": "verifier", "risk": "read_only"},
            ],
        },
        "results": [
            {"action_id": "prepare_task", "executed": False, "reason": "dry_run"},
            {"action_id": "run_verification", "executed": False, "reason": "dry_run"},
        ],
        "summary": {"action_count": 2, "executed_count": 0, "blocked_count": 2},
    }

    first = commons.ingest_cli_execution(execution)
    second = commons.ingest_cli_execution(execution)
    ranked = commons.rank(task_class="agentic_cli", role="cartographer", limit=5)

    assert first["accepted"] == 2
    assert second["duplicates"] == 2
    assert ranked["count"] == 1
    assert ranked["rankings"][0]["capability_id"].startswith("cli_openclaw_cartographer_prepare_task")


def test_ollama_scout_calibration_ingests_verifier_outcome(tmp_path):
    commons = MetaToolCommons(db_path=str(tmp_path / "commons.db"))
    scout = {
        "decision_contract": {
            "source": "ollama",
            "task_type": "code_change",
            "risk": "low",
            "confidence": 0.84,
            "needs_cloud": False,
            "privacy_level": "local_only",
        }
    }
    verifier = {
        "status": "passed",
        "verified": True,
        "safe": True,
        "verifier": "pytest",
        "created_at": "2026-06-21T00:00:00Z",
    }

    first = commons.ingest_ollama_calibration(scout, verifier)
    second = commons.ingest_ollama_calibration(scout, verifier)
    ranked = commons.rank(task_class="code_change", role="ollama_scout", limit=5)

    assert first["accepted"] == 1
    assert first["confidence_bucket"] == 0.8
    assert first["matched_verifier"] is True
    assert second["duplicates"] == 1
    assert ranked["count"] == 1
    assert ranked["rankings"][0]["capability_id"].startswith("ollama_scout_ollama_code_change_low")


def test_kv_cache_transport_ingests_only_real_reuse_evidence(tmp_path):
    commons = MetaToolCommons(db_path=str(tmp_path / "commons.db"))
    empty = commons.ingest_kv_cache_evidence({
        "beast_object_type": "kv_cache_transport_stats",
        "total_blocks": 0,
        "operations_logged": 0,
    })
    stats = {
        "beast_object_type": "kv_cache_transport_stats",
        "total_blocks": 1,
        "compressed_blocks": 0,
        "total_size_bytes": 2048,
        "blocks_by_engine": {"vllm": 1},
        "blocks_by_location": {"network": 1},
        "operations_logged": 4,
    }
    result = {
        "adapter": "LocalKVEngineAdapter",
        "engine": "vllm",
        "looked_up": True,
        "payload_round_tripped": True,
        "storage_persisted": True,
        "network_manifest_ready": True,
        "operations_logged": 4,
        "estimated_tokens_saved": 128,
        "created_at": "2026-06-21T00:00:00Z",
    }

    first = commons.ingest_kv_cache_evidence(stats, result)
    second = commons.ingest_kv_cache_evidence(stats, result)
    ranked = commons.rank(task_class="kv_cache_reuse", role="kv_cache_transport", limit=5)

    assert empty["prepared"] == 0
    assert empty["accepted"] == 0
    assert first["accepted"] == 1
    assert first["verified"] is True
    assert first["useful"] is True
    assert second["duplicates"] == 1
    assert ranked["count"] == 1
    assert ranked["rankings"][0]["capability_id"].startswith("kv_cache_vllm_localkvengineadapter")


def test_evidence_plane_rolls_up_reuse_bridges_without_raw_payloads(tmp_path):
    commons = MetaToolCommons(db_path=str(tmp_path / "commons.db"))
    swarm = {
        "run_id": "swarm_run_1",
        "status": "ready",
        "state": "completed",
        "task_type": "code_change",
        "risk_level": "low",
        "created_at": "2026-06-21T00:00:00Z",
        "updated_at": "2026-06-21T00:01:00Z",
        "metadata": {"profile": "openclaw"},
        "plan": [{"role": "cartographer", "action": "select_relevant_context"}],
        "gates": [{"decision": "allow"}],
        "value": {"tokens_saved": 12, "cost_saved_usd": 0.001},
    }
    cli = {
        "status": "dry_run",
        "plan": {
            "mode": "openclaw",
            "created_at": "2026-06-21T00:00:00Z",
            "plan_hash": "sha256:plan",
            "actions": [{"action_id": "prepare_task", "kind": "mcp_request", "role": "cartographer", "risk": "read_only"}],
        },
        "results": [{"action_id": "prepare_task", "executed": False, "reason": "dry_run"}],
    }
    ollama = {"decision_contract": {"source": "ollama", "task_type": "code_change", "risk": "low", "confidence": 0.9}}
    verifier = {"status": "passed", "verified": True, "safe": True, "created_at": "2026-06-21T00:00:00Z"}
    kv_stats = {
        "total_blocks": 1,
        "operations_logged": 4,
        "total_size_bytes": 2048,
        "blocks_by_engine": {"vllm": 1},
        "blocks_by_location": {"network": 1},
    }
    kv_result = {"adapter": "LocalKVEngineAdapter", "engine": "vllm", "looked_up": True, "payload_round_tripped": True, "created_at": "2026-06-21T00:00:00Z"}

    commons.ingest_swarm_runs([swarm])
    commons.ingest_cli_execution(cli)
    commons.ingest_ollama_calibration(ollama, verifier)
    commons.ingest_kv_cache_evidence(kv_stats, kv_result)
    plane = commons.evidence_plane()

    names = {item["plane"] for item in plane["planes"]}
    assert {"swarm", "cli", "ollama", "kv_cache"} <= names
    assert plane["evidence_count"] == 4
    assert plane["plane_count"] == 4
    assert plane["plane_hash"].startswith("sha256:")
    dumped = json.dumps(plane, sort_keys=True).lower()
    assert "prompt" not in dumped
    assert "source_code" not in dumped
    assert "file_path" not in dumped


def test_discovery_ingest_stages_schema_pinned_hypotheses_without_raw_docs(tmp_path):
    commons = MetaToolCommons(db_path=str(tmp_path / "commons.db"))
    raw_body = "RAW SECRET TRAINING BODY SHOULD NEVER BE STORED"
    payload = {
        "stage_candidates": True,
        "sources": [
            {
                "source_type": "mcp_tool_catalog",
                "source_id": "local-mcp",
                "trust_level": "local",
                "items": [
                    {
                        "name": "repo_symbol_search",
                        "description": "Read-only symbol search over an indexed repository.",
                        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
                        "category": "code_navigation",
                        "risk_class": "low",
                    }
                ],
            },
            {
                "source_type": "plugin_manifest",
                "source_id": "plugin-catalog",
                "trust_level": "known",
                "manifest": {
                    "id": "safe.repo.navigator",
                    "name": "Safe Repo Navigator",
                    "version": "1.0.0",
                    "publisher": "beast-local",
                    "risk_class": "medium",
                    "entrypoint": {"kind": "python", "module": "safe_repo.navigator"},
                    "tools": [
                        {
                            "name": "find_symbols",
                            "description": "Find symbols in local project metadata.",
                            "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"}}},
                        }
                    ],
                    "permissions": {
                        "filesystem_read": [],
                        "filesystem_write": [],
                        "network_domains": [],
                        "environment": [],
                    },
                    "budget": {
                        "max_tokens_per_call": 0,
                        "max_cost_usd_per_call": 0,
                        "max_latency_ms": 250,
                        "calls_per_hour": 60,
                    },
                    "approval_policy": {
                        "install": True,
                        "first_run": True,
                        "network": True,
                        "external_write": True,
                        "filesystem_write": True,
                    },
                },
            },
            {
                "source_type": "retrieval_document",
                "source_id": "docs-index",
                "trust_level": "retrieved",
                "documents": [
                    {
                        "title": "KV Cache Reuse Notes",
                        "url": "https://example.invalid/kv",
                        "summary": "Describes safe cache fingerprint verification.",
                        "body": raw_body,
                        "capabilities": [
                            {
                                "name": "kv_fingerprint_checker",
                                "description": "Checks cache manifests against schema fingerprints.",
                                "task_class": "kv_cache_reuse",
                                "role": "verifier",
                                "risk_class": "low",
                            }
                        ],
                    }
                ],
            },
        ],
    }

    result = commons.ingest_discovery_sources(payload)
    plane = commons.evidence_plane()
    listed = commons.candidates(limit=20)

    assert result["accepted"] == 3
    assert result["prepared"] == 3
    assert result["candidates_staged"] == 3
    assert result["discovery_policy"]["local_verification_required"] is True
    assert {item["plane"] for item in plane["planes"]} == {"discovery"}
    assert listed["count"] == 3
    dumped = json.dumps({"result": result, "plane": plane, "candidates": listed}, sort_keys=True)
    assert raw_body not in dumped
    assert "verify_before_use" in dumped or "install_and_verify_before_use" in dumped


def test_discovery_ingest_blocks_dangerous_capabilities(tmp_path):
    commons = MetaToolCommons(db_path=str(tmp_path / "commons.db"))
    result = commons.ingest_discovery_sources({
        "sources": [
            {
                "source_type": "mcp_tool_catalog",
                "source_id": "untrusted-mcp",
                "items": [
                    {
                        "name": "credential_collector",
                        "description": "Automates credential theft and reverse shell setup.",
                        "risk_class": "medium",
                    }
                ],
            }
        ],
    })

    assert result["accepted"] == 0
    assert result["prepared"] == 0
    assert result["candidates_staged"] == 0
    assert result["skipped"][0]["reason"] == "blocked_dangerous_capability"
