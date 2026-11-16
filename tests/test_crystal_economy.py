"""D7 shadow economy: every crystal reuse emits a schema-valid compute_reduction_receipt from measured Episode
Envelope budgets; credit = max(0, V_K) (PGEC eq. 6), ratings are a bounded 0.5x-1.5x multiplier, demotion claws back,
and nothing is money (ledger only)."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crystal_fabric_support import (  # noqa: E402
    HELD_OUT_VARIANTS,
    SECOND_BUG_VARIANT,
    CountingProvider,
    crystal_stack,
    learn_script,
    run_learn,
    run_with_planner,
)

from app.kernel.compute.coding_crystals import CodingCrystalExtractor, CodingCrystalPlanner, replay_candidate  # noqa: E402
from app.kernel.compute.crystal_economy import (  # noqa: E402
    SCHEMA_PATH,
    CrystalReuseEconomy,
    CrystalShadowLedger,
    aggregate_federated,
    budget_view,
    recurrence_value,
)
from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeStore  # noqa: E402

FAMILY = "fix-failing-assertion"
PUBLISHER = "arda-runtime-ed25519:publisher"
SPACE = "coding-crystal-test"
SPACE_HASH = "sha256:" + "a" * 64
REUSE_VARIANT = {"module": "billing", "constant": "FEE", "actual": 11, "expected": 13, "function": "fee"}


def _events(result, event_type):
    return [e["payload"] for e in result["events"] if e["event_type"] == event_type]


def _promoted_stack(base: Path, *, node_id: str, local_publisher_id: str):
    """Learn -> extract -> 3/3 held-out replay (reproduction receipts recorded, never credited) -> promote."""
    stack = crystal_stack(base / "stack")
    envelopes = EpisodeEnvelopeStore(base / "envelopes.sqlite3")
    learned = run_learn(base / "learn", base / "envelopes.sqlite3")
    candidate = CodingCrystalExtractor().extract(learned["envelope"], learned["observations"], registry=stack["registry"])
    stack["registry"].add_candidate(candidate)
    ledger = CrystalShadowLedger(base / "shadow.sqlite3", local_node_id=node_id, local_publisher_id=local_publisher_id)
    ledger.bind_space(candidate.crystal_id, space_id=SPACE, space_manifest_hash=SPACE_HASH, publisher_id=PUBLISHER)
    economy = CrystalReuseEconomy(ledger, envelope_store=envelopes, local_user_id="user-1")
    replay_planner = CodingCrystalPlanner(stack["registry"], stack["authority"], stack["ledger"],
                                          replay_candidate_id=candidate.crystal_id, economy=economy)
    reproductions = []

    def run_variant(variant):
        result = run_with_planner(base / f"replay-{variant['module']}", replay_planner, variant=variant)
        reproductions.append(result)
        return result["final"]["state"] == "completed" and result["provider"].calls == 0

    assert replay_candidate(stack["registry"], candidate, list(HELD_OUT_VARIANTS), run_variant).promoted
    planner = CodingCrystalPlanner(stack["registry"], stack["authority"], stack["ledger"], economy=economy)
    return {"stack": stack, "candidate": candidate, "learned": learned, "ledger": ledger, "economy": economy,
            "planner": planner, "reproductions": reproductions, "base": base}


@pytest.fixture(scope="module")
def consumer(tmp_path_factory):
    """Node B reuses a crystal published by another identity; it witnessed every reuse locally."""
    world = _promoted_stack(tmp_path_factory.mktemp("consumer"), node_id="node-b", local_publisher_id="arda:node-b")
    script = learn_script(REUSE_VARIANT["module"], REUSE_VARIANT["constant"], REUSE_VARIANT["actual"], REUSE_VARIANT["expected"])
    world["baseline"] = run_with_planner(world["base"] / "baseline", None, variant=REUSE_VARIANT, provider=CountingProvider(script))
    world["reuse"] = run_with_planner(world["base"] / "reuse", world["planner"], variant=REUSE_VARIANT,
                                      provider=CountingProvider(script))
    return world


def _receipt(world):
    event = _events(world["reuse"], "agent.crystal.reduction_receipt")[0]
    rows = [e for e in world["ledger"].export()["receipts"] if e["receipt_id"] == event["receipt_id"]]
    return event, rows[0]


def test_every_reuse_emits_schema_valid_receipt_from_measured_budgets(consumer):
    event, receipt = _receipt(consumer)
    jsonschema.validate(receipt, json.loads(SCHEMA_PATH.read_text()))
    assert receipt["provenance"]["kind"] == "reuse" and receipt["provenance"]["measurement"] == "episode_envelope_budget"
    learned = consumer["learned"]["envelope"]
    assert receipt["baseline_route"]["budget"] == budget_view(learned.budget)
    assert receipt["baseline_route"]["baseline_source"] == "local_envelope"
    assert receipt["optimized_route"]["budget"] == budget_view(consumer["reuse"]["envelope"].budget)
    assert receipt["optimized_route"]["budget"]["model_turns"] == 0
    assert receipt["displacement"]["provider_calls_avoided"] == learned.budget["model_turns"]
    # The scripted planner reports no provider usage: tokens are estimated, flagged, and never counted.
    assert receipt["displacement"]["tokens_estimated"] is True
    assert receipt["displacement"]["provider_tokens_avoided"] == 0 and receipt["displacement"]["tokens_avoided"] == 0
    assert receipt["displacement"]["counterfactual"] is False
    assert receipt["provenance"]["transferable"] is False and receipt["provenance"]["financial_value"] is None


def test_credit_is_max_zero_vk_and_attributed_to_publishing_space(consumer):
    event, receipt = _receipt(consumer)
    expected = recurrence_value(receipt["baseline_route"]["budget"], receipt["optimized_route"]["budget"])
    assert event["credited"] is True and event["units"] == pytest.approx(expected["credit"])
    assert expected["credit"] == max(0.0, expected["v_k"]) and expected["tokens_counted"] is False
    account = next(a for a in consumer["ledger"].balances()["accounts"] if a["publisher_id"] == PUBLISHER)
    assert account["space_id"] == SPACE and account["verified_reuses"] == 1
    assert account["distinct_consumers"] == 1 and "consumers" not in account
    assert consumer["ledger"].balances()["redeemable"] is False


def test_reproduction_runs_record_evidence_but_earn_nothing(consumer):
    kinds = [e["kind"] for e in consumer["ledger"].entries(crystal_id=consumer["candidate"].crystal_id)]
    assert kinds.count("reproduction") == 3
    assert all(e["units"] == 0 for e in consumer["ledger"].entries() if e["kind"] == "reproduction")


def test_duplicate_and_remote_claims_earn_nothing(consumer):
    _, receipt = _receipt(consumer)
    assert consumer["ledger"].account_reuse(receipt, crystal_status="promoted")["reason"] == "duplicate_reuse"
    remote = CrystalShadowLedger(consumer["base"] / "other.sqlite3", local_node_id="node-c")
    assert remote.account_reuse(receipt, crystal_status="promoted")["reason"] == "remote_claim_not_locally_witnessed"


def test_ratings_are_bounded_multipliers_from_the_verified_reuser_only(consumer):
    event, _ = _receipt(consumer)
    ledger = consumer["ledger"]
    with pytest.raises(PermissionError):
        ledger.rate(event["receipt_id"], rater_node="node-b", rater_user="someone-else", stars=5)
    with pytest.raises(PermissionError):
        ledger.rate("space_receipt_" + "0" * 20, rater_node="node-b", rater_user="user-1", stars=5)
    rated = ledger.rate(event["receipt_id"], rater_node="node-b", rater_user="user-1", stars=5)
    assert rated["multiplier"] == 1.5 and rated["units"] == pytest.approx(0.5 * event["units"])
    with pytest.raises(PermissionError):
        ledger.rate(event["receipt_id"], rater_node="node-b", rater_user="user-1", stars=1)
    assert ledger.verify_chain()["valid"] is True


def test_publisher_cannot_earn_or_rate_on_its_own_crystal(tmp_path):
    world = _promoted_stack(tmp_path, node_id="node-a", local_publisher_id=PUBLISHER)
    reuse = run_with_planner(tmp_path / "self-reuse", world["planner"], variant=REUSE_VARIANT)
    event = _events(reuse, "agent.crystal.reduction_receipt")[0]
    assert event["credited"] is False and event["reason"] == "self_dealing" and event["units"] == 0
    with pytest.raises(PermissionError):
        world["ledger"].rate(event["receipt_id"], rater_node="node-a", rater_user="user-1", stars=5)


def test_demotion_claws_back_credit_and_blocks_further_ratings(tmp_path):
    world = _promoted_stack(tmp_path, node_id="node-b", local_publisher_id="arda:node-b")
    ok = run_with_planner(tmp_path / "ok", world["planner"], variant=REUSE_VARIANT)
    credited = _events(ok, "agent.crystal.reduction_receipt")[0]
    assert credited["credited"] is True and credited["units"] > 0
    failing = run_with_planner(tmp_path / "second-bug", world["planner"], variant=SECOND_BUG_VARIANT)
    assert _events(failing, "agent.crystal.aborted")[-1]["reason"] == "postcondition_failed"
    ledger = world["ledger"]
    kinds = [e["kind"] for e in ledger.entries()]
    assert "false_reuse" in kinds and "clawback" in kinds
    account = next(a for a in ledger.balances()["accounts"] if a["publisher_id"] == PUBLISHER)
    assert account["units"] == pytest.approx(0.0) and account["clawbacks"] == 1
    with pytest.raises(PermissionError):
        ledger.rate(credited["receipt_id"], rater_node="node-b", rater_user="user-1", stars=5)
    assert ledger.clawback(world["candidate"].crystal_id, reason="again")["already"] is True


def test_quarantined_crystal_reuse_is_not_credited(consumer):
    _, receipt = _receipt(consumer)
    fresh = CrystalShadowLedger(consumer["base"] / "fresh.sqlite3", local_node_id="node-b")
    assert fresh.account_reuse(receipt, crystal_status="quarantined")["reason"] == "not_locally_reproduced_and_promoted"


def test_tampered_ledger_and_sybil_federation_are_rejected(consumer, tmp_path):
    export = consumer["ledger"].export()
    aggregate = aggregate_federated([export, {**export, "node_id": "sybil-node"}, export], attested_nodes={"node-b"})
    assert aggregate["publishers"][PUBLISHER] == pytest.approx(
        sum(e["units"] for e in export["entries"] if e["publisher_id"] == PUBLISHER))
    reasons = {r["reason"] for r in aggregate["rejected"]}
    assert {"node_not_attested", "duplicate_entry"} <= reasons
    same_operator = aggregate_federated([export], attested_nodes={"node-b"},
                                        controller_of=lambda identity: "byron" if identity in {"node-b", PUBLISHER} else identity)
    assert PUBLISHER not in same_operator["publishers"]
    copy = tmp_path / "copy.sqlite3"
    copy.write_bytes(Path(consumer["ledger"].path).read_bytes())
    with sqlite3.connect(copy) as c:
        c.execute("UPDATE entries SET units = units + 100 WHERE kind='reuse'")
    assert CrystalShadowLedger(copy, local_node_id="node-b").verify_chain()["valid"] is False


def test_consumer_without_local_baseline_uses_publisher_signed_measured_budget(consumer, tmp_path):
    economy = CrystalReuseEconomy(CrystalShadowLedger(tmp_path / "s.sqlite3", local_node_id="node-z"),
                                  envelope_store=EpisodeEnvelopeStore(tmp_path / "empty.sqlite3"))
    budget, digest, source, verified = economy._baseline(consumer["candidate"])
    assert source == "publisher_signed_envelope" and digest == consumer["candidate"].source_envelope_digest
    assert budget == dict(consumer["candidate"].learned_budget) and verified is True
