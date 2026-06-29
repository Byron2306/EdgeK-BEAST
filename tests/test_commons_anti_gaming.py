from app.kernel.networking.commons_anti_gaming import CommonsAntiGaming

def test_sybil_wash_cluster_is_frozen_without_flagging_normal_user():
    signups=[{"user_id":f"bad{i}","source_hash":"same"} for i in range(5)]+[{"user_id":"good","source_hash":"unique"}]
    swaps=[{"user_id":f"bad{i}","from_asset":"BEASTCOIN" if n%2 else "CRYSTAL","amount_in":600} for i in range(5) for n in range(24)]
    report=CommonsAntiGaming().analyze(signup_events=signups,swaps=swaps,claims=[])
    flagged={x["user_id"]:x for x in report["flagged_accounts"]}
    assert all(flagged[f"bad{i}"]["action"]=="freeze" for i in range(5))
    assert "good" not in flagged
