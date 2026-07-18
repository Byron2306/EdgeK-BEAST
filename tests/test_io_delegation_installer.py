from pathlib import Path


def test_io_delegation_overrides_accounting_and_user_manager_delegate_list():
    root = Path(__file__).resolve().parents[1]
    user_service = (root / "deploy/systemd/user@.service.d/90-beast-io-delegation.conf").read_text()
    per_user_slice = (root / "deploy/systemd/user-.slice.d/90-beast-io-delegation.conf").read_text()
    assert "Delegate=cpu memory pids io" in user_service
    assert "IOAccounting=yes" in user_service
    assert "IOAccounting=yes" in per_user_slice


def test_installer_copies_all_three_hierarchy_overrides():
    source = Path("scripts/install_beast_io_delegation.py").read_text()
    assert "user.slice.d" in source
    assert "user-.slice.d" in source
    assert "user@.service.d" in source
    assert "--verify" in source
    assert "beast-io-delegation-verify" in source
    assert '"--property=Delegate=io"' in source


def test_live_proof_selects_kernel_attributed_io_stat_device():
    source = Path("scripts/run_mission_isolation_proof.py").read_text()
    assert 'cursor / "io.stat"' in source
    assert 'os.stat("/")' not in source
