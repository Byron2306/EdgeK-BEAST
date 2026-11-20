from collections import Counter

import pytest

from scripts.proof.run_stage7a_socket_continuity import accounting, run_trial


def test_stage7a_counts_application_duplicates_independently_of_client_acknowledgements():
    rows = [
        {"request_id": "a", "phase": "gap", "status": "ok"},
        {"request_id": "b", "phase": "gap", "status": "refused"},
    ]
    result = accounting(rows, ["a", "a"])
    assert result["completed"] == 1 and result["failed"] == 1
    assert result["application_duplicates"] == 1
    assert result["phases"]["gap"]["refused"] == 1


def test_plain_restart_has_refusals_during_controlled_gap(tmp_path):
    row = run_trial(tmp_path / "plain", "plain_restart", 1, gap_ms=100, gap_requests=8)
    assert row["verified"] and row["accounting"]["application_duplicates"] == 0
    assert row["accounting"]["phases"]["gap"] == {"refused": 8}
    assert row["accounting"]["phases"]["before"] == {"ok": 4}
    assert row["accounting"]["phases"]["after"] == {"ok": 4}
    assert row["replacement_pid"] != row["initial_pid"]


def test_guardian_retains_same_listener_when_seqpacket_available(tmp_path):
    row = run_trial(tmp_path / "guardian", "guardian_scm", 1, gap_ms=100, gap_requests=8)
    if row["status"] == "unavailable":
        pytest.skip(row["reason"])
    assert row["verified"]
    assert row["listener_same"] and row["signed_handoffs"] == 2
    assert row["accounting"]["phases"]["gap"] == {"ok": 8}
    assert row["accounting"]["application_duplicates"] == 0
