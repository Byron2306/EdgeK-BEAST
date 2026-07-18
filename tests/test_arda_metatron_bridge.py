from app.kernel.compute.port_conflict_crystal import PortConflictRepairCrystal
from app.kernel.integration.arda_metatron_bridge import ArdaMetatronBridge
from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
import base64
import time


def plan():
    return PortConflictRepairCrystal().plan(requested_port=8005, listener=None, lease_match=False, process_start_verified=False, health_ok=False)


def test_both_systems_must_authorize_before_effect():
    called = []
    bridge = ArdaMetatronBridge(arda_authorize=lambda _: True, metatron_authorize=lambda _: False, evidence=None)
    result = bridge.authorize_and_execute(plan(), execute=lambda: called.append(True) or {"status": "bound"})
    assert result.executed is False
    assert called == []


def test_authorized_cross_system_effect_is_recorded():
    bridge = ArdaMetatronBridge(arda_authorize=lambda _: True, metatron_authorize=lambda _: True)
    result = bridge.authorize_and_execute(plan(), execute=lambda: {"status": "bound"})
    assert result.executed is True
    assert result.evidence_node_id.startswith("sha256:")


def test_one_use_capabilities_bind_to_canonical_request_and_execute(tmp_path):
    ledger = OneUseCapabilityLedger(path=tmp_path / "capabilities.sqlite3", require_verifier=False)

    def decision(authority):
        def authorize(request):
            return {
                "allowed": True,
                "capability": {
                    "capability_id": f"cap:{authority}:1",
                    "request_digest": request["request_digest"],
                    "authority": authority,
                    "expires_at": time.time() + 60,
                    "nonce": f"nonce:{authority}",
                    "signature": base64.b64encode(b"test-profile-signature").decode(),
                },
            }
        return authorize

    bridge = ArdaMetatronBridge(
        arda_authorize=decision("arda"), metatron_authorize=decision("metatron"),
        capability_ledger=ledger,
    )
    result = bridge.authorize_and_execute(plan(), execute=lambda: {"status": "bound"})
    assert result.arda_allowed is True
    assert result.metatron_allowed is True
    assert result.executed is True
