import pytest

from app.kernel.commons.tpm_attestation import TpmChallengeLedger, fail_closed_result
from app.kernel.integration.tpm_validation import (
    combine_measurement_reconciliations,
    compare_replayed_pcrs,
    compare_vendor_pcr_baseline,
    parse_hp_history_pcr_baselines,
    replay_ima_ascii_measurements,
)


def test_tpm_challenge_is_durable_bound_and_one_use(tmp_path):
    ledger = TpmChallengeLedger(tmp_path / "challenges.sqlite3")
    challenge = ledger.issue("node-windows-1", now=100.0, ttl_seconds=60.0)

    restored = TpmChallengeLedger(tmp_path / "challenges.sqlite3").get(challenge.challenge_id)
    assert restored == challenge
    with pytest.raises(PermissionError, match="binding mismatch"):
        ledger.consume(challenge.challenge_id, node_id="other-node", nonce=challenge.nonce, now=110.0)

    ledger.consume(challenge.challenge_id, node_id=challenge.node_id, nonce=challenge.nonce, now=110.0)
    with pytest.raises(PermissionError, match="already been consumed"):
        ledger.consume(challenge.challenge_id, node_id=challenge.node_id, nonce=challenge.nonce, now=111.0)


def test_expired_tpm_challenge_cannot_be_consumed(tmp_path):
    ledger = TpmChallengeLedger(tmp_path / "challenges.sqlite3")
    challenge = ledger.issue("node-1", now=100.0, ttl_seconds=1.0)
    with pytest.raises(PermissionError, match="expired"):
        ledger.consume(challenge.challenge_id, node_id=challenge.node_id, nonce=challenge.nonce, now=102.0)


def test_new_challenge_supersedes_prior_active_challenge(tmp_path):
    ledger = TpmChallengeLedger(tmp_path / "challenges.sqlite3")
    first = ledger.issue("node-1", now=100.0)
    second = ledger.issue("node-1", now=101.0)
    assert ledger.get(first.challenge_id).state == "superseded"
    assert ledger.get(second.challenge_id).state == "issued"
    assert ledger.snapshot(now=102.0)["superseded"] == 1


def test_tpm_admission_is_derived_only_from_verifier_facts():
    bundle = {
        "challenge_id": "challenge-1",
        "node_id": "node-windows-1",
        "platform": "windows",
        "attestation": "verified",  # self-reported labels carry no weight
    }
    denied = fail_closed_result(bundle, quote_valid=True, ek_public_matches_certificate=True)
    assert denied.eligible_for_commons is False
    assert "ak_not_credential_activated" in denied.reasons

    accepted = fail_closed_result(
        bundle,
        quote_valid=True,
        ek_public_matches_certificate=True,
        ek_chain_valid=True,
        ak_credential_activated=True,
        secure_boot_accepted=True,
        event_log_replay_valid=True,
        nonce_consumed=True,
    )
    assert accepted.eligible_for_commons is True
    assert accepted.reasons == ()


def test_event_log_replay_requires_exact_coverage_and_values():
    digest_a = "0x" + "a" * 64
    digest_b = "0x" + "b" * 64
    exact = compare_replayed_pcrs({0: digest_a, 7: digest_b}, {0: digest_a, 7: digest_b}, (0, 7))
    assert exact["valid"] is True

    uncovered = compare_replayed_pcrs({0: digest_a}, {0: digest_a, 7: digest_b}, (0, 7))
    assert uncovered["valid"] is False
    assert uncovered["uncovered_pcrs"] == [7]

    mismatch = compare_replayed_pcrs({0: digest_a}, {0: digest_b}, (0,))
    assert mismatch["valid"] is False
    assert mismatch["mismatched_pcrs"] == [0]


def test_ima_replay_extends_template_hashes_and_combines_sources():
    first = "11" * 32
    second = "22" * 32
    replay = replay_ima_ascii_measurements(
        f"10 {first} ima-ng sha256:{'aa' * 32} /first\n"
        f"10 {second} ima-ng sha256:{'bb' * 32} /second\n"
    )
    expected = __import__("hashlib").sha256(
        __import__("hashlib").sha256(bytes(32) + bytes.fromhex(first)).digest()
        + bytes.fromhex(second)
    ).hexdigest()
    assert replay["pcrs"][10] == expected
    assert replay["event_counts"][10] == 2

    combined = combine_measurement_reconciliations(
        (0, 10),
        {"source": "firmware", "matched_pcrs": [0], "mismatched_pcrs": []},
        {"source": "ima", "matched_pcrs": [10], "mismatched_pcrs": []},
    )
    assert combined["valid"] is True
    assert combined["matched_by"] == {"0": ["firmware"], "10": ["ima"]}


def test_hp_history_vendor_pcr_baseline_can_satisfy_pcr0():
    history = """
Version 01.11.00

FIXES:
- General bug fixes.

    V72 PCR0 (TPM2.0) = 0886E6FC01B4B9C8FC427EB494C7FA477032D56991529621FE3E9865F532E92F

Version 01.10.00
    V72 PCR0 (TPM2.0) = F4B64A5BAB2446C08C741DF7C0C35256579DB3F97DFF6C1C5CDBABC767191D5C
"""
    baseline = parse_hp_history_pcr_baselines(
        history, bios_version="V72 Ver. 01.11.00"
    )
    assert baseline == {
        0: "0886e6fc01b4b9c8fc427eb494c7fa477032d56991529621fe3e9865f532e92f"
    }

    compared = compare_vendor_pcr_baseline(
        baseline,
        {
            0: "0x0886E6FC01B4B9C8FC427EB494C7FA477032D56991529621FE3E9865F532E92F"
        },
        (0,),
    )
    assert compared["valid"] is True
    assert compared["matched_pcrs"] == [0]


def test_combined_measurement_accepts_vendor_pcr0_and_ima_pcr10():
    combined = combine_measurement_reconciliations(
        (0, 10),
        {
            "source": "firmware_event_log",
            "matched_pcrs": [],
            "mismatched_pcrs": [0],
        },
        {
            "source": "vendor_pcr_baseline",
            "matched_pcrs": [0],
            "mismatched_pcrs": [],
        },
        {
            "source": "ima_runtime_measurements",
            "matched_pcrs": [10],
            "mismatched_pcrs": [],
        },
    )
    assert combined["valid"] is True
    assert combined["matched_by"] == {
        "0": ["vendor_pcr_baseline"],
        "10": ["ima_runtime_measurements"],
    }
    assert combined["mismatched_by"] == {"0": ["firmware_event_log"]}
