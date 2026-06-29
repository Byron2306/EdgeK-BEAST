#!/usr/bin/env python3
"""Generate 10k identities and pressure-test deterministic anti-gaming rules."""
import json, random, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from app.kernel.commons_anti_gaming import CommonsAntiGaming

rng=random.Random(1337); signups=[]; swaps=[]; malicious=set()
for i in range(10_000):
    user=f"user_{i:05d}"; source=f"source_{i:05d}"
    signups.append({"user_id":user,"source_hash":source})
    for _ in range(rng.randint(0,3)): swaps.append({"user_id":user,"from_asset":"BEASTCOIN","to_asset":"CRYSTAL","amount_in":rng.randint(10,300)})
for cluster in range(50):
    source=f"sybil_{cluster}"
    for offset in range(5):
        user=f"user_{cluster*5+offset:05d}"; malicious.add(user); signups[cluster*5+offset]["source_hash"]=source
        for n in range(24): swaps.append({"user_id":user,"from_asset":"BEASTCOIN" if n%2==0 else "CRYSTAL","to_asset":"CRYSTAL" if n%2==0 else "BEASTCOIN","amount_in":600})
report=CommonsAntiGaming().analyze(signup_events=signups,swaps=swaps,claims=[],ledger_balanced=True)
flagged={x["user_id"] for x in report["flagged_accounts"]}; tp=len(flagged&malicious); fp=len(flagged-malicious)
receipt={**report,"simulation":{"identities":10_000,"events":len(signups)+len(swaps),"malicious":len(malicious),"true_positives":tp,"false_positives":fp,"recall":round(tp/len(malicious),6),"false_positive_rate":round(fp/(10_000-len(malicious)),6)},"success":tp==len(malicious) and fp==0}
path=ROOT/"benchmarks/results/commons_anti_gaming_stress_latest.json"; path.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n"); print(json.dumps(receipt["simulation"]|{"success":receipt["success"]},indent=2))
