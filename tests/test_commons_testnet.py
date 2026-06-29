import pytest

from app.kernel.networking.commons_testnet import CommonsTestnet


def test_account_wallet_swap_and_double_entry(tmp_path):
    net = CommonsTestnet(tmp_path / "testnet.db")
    account = net.signup("beast@example.com", "Beast User", "StrongPassword123")
    session = net.login("beast@example.com", "StrongPassword123")
    assert net.authenticate(session["token"])["user_id"] == account["user_id"]
    assert net.wallet(account["user_id"])["balances"]["BEASTCOIN"] == 1000

    swapped = net.swap(account["user_id"], "BEASTCOIN", 100)
    wallet = net.wallet(account["user_id"])
    assert swapped["amount_out"] == 9
    assert wallet["balances"] == {"BEASTCOIN": 900, "CRYSTAL": 9}
    with net.connect() as conn:
        totals = dict(conn.execute("SELECT asset,SUM(amount) FROM ledger GROUP BY asset").fetchall())
    assert totals == {"BEASTCOIN": 0, "CRYSTAL": 0}


def test_credit_claim_is_unique_and_pricing_decays(tmp_path):
    net = CommonsTestnet(tmp_path / "testnet.db")
    user = net.signup("proof@example.com", "Proof User", "StrongPassword123")
    credit = {"credit_id":"ccredit_1","evidence_fingerprint":"sha256:abc","space_id":"space_a","credit_units":25,"created_at":"2026-06-22T00:00:00+00:00"}
    assert net.claim_credit(user["user_id"], credit)["units"] == 25
    with pytest.raises(ValueError, match="already claimed"):
        net.claim_credit(user["user_id"], credit)
    pricing = net.pricing([credit])
    assert pricing["financial_value"] is None
    assert pricing["credits"][0]["effective_units"] <= 25


def test_auth_and_swap_limits(tmp_path):
    net = CommonsTestnet(tmp_path / "testnet.db")
    user = net.signup("limits@example.com", "Limits", "StrongPassword123")
    with pytest.raises(ValueError, match="invalid credentials"):
        net.login("limits@example.com", "wrong password")
    with pytest.raises(ValueError, match="insufficient"):
        net.swap(user["user_id"], "BEASTCOIN", 2000)
