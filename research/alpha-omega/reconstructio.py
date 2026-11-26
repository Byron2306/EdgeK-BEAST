import argparse,json,re,collections
from pathlib import Path
from consensus_magna import sha,paired,census

def verify(folder):
    m=folder/"evidence.sha256"; entries={}; errors=[]
    for line in m.read_text().splitlines():
        match=re.fullmatch(r"([0-9a-f]{64}) [ *](.+)",line)
        if not match: errors.append("unsupported line");continue
        h,n=match.groups(); p=folder/n
        if ".." in Path(n).parts or not p.resolve().is_relative_to(folder.resolve()):
            errors.append("outside manifest root: "+n);continue
        key=str(p.resolve().relative_to(folder.resolve()))
        if key in entries: errors.append("duplicate: "+key);continue
        entries[key]=h
        if not p.is_file() or sha(p)!=h: errors.append("missing or changed: "+key)
    return dict(root=str(folder),manifest_sha256=sha(m),entries=len(entries),errors=errors,status="HASH_CONSISTENT" if entries and not errors else "REFUSE"),entries

def reconstruct(s):
    receipt,entries=verify(s)
    if receipt["status"]!="HASH_CONSISTENT": raise ValueError("SAPIENTIA integrity")
    for n in ("trials.jsonl","oracle.jsonl","protocol.json"):
        if n not in entries: raise ValueError("unsealed input "+n)
    protocol=json.loads((s/"protocol.json").read_text())
    rows=[json.loads(l) for l in (s/"trials.jsonl").read_text().splitlines()]
    policies=set(protocol["policies"])
    expected={(c,e,p) for c in range(128) for e in range(3) for p in policies}
    seen=set(); normalized=[]; groups=collections.defaultdict(list); cells={}
    for r in rows:
        k=(r["config"],r["encounter"],r["policy"])
        if k not in expected or k in seen: raise ValueError("unexpected or duplicate trial")
        seen.add(k)
        if type(r["total_ns"]) is not int or r["total_ns"]<=0 or r["verified_roots"]!=r["context"][0]: raise ValueError("invalid trial")
        groups[r["policy"]].append(r);cells[k]=r
        normalized.append(dict(configuration=k[0],encounter=k[1],policy=k[2],wall_ns=r["total_ns"]))
    if seen!=expected or len(rows)!=4992: raise ValueError("incomplete trials")
    oracle={}
    for l in (s/"oracle.jsonl").read_text().splitlines():
        r=json.loads(l);k=(r["config"],r["encounter"])
        if k in oracle or set(r["runs"])!=set("ABCDEFGH"): raise ValueError("oracle coverage")
        oracle[k]=r
    if set(oracle)!={(c,e) for c,e,p in expected}: raise ValueError("incomplete oracle")
    base=sum(r["total_ns"] for r in groups["TABULA_RASA"])
    metrics={}
    for p,rs in sorted(groups.items()):
        total=sum(r["total_ns"] for r in rs)
        metrics[p]=dict(speedup=base/total,total_ns=total,verified_roots=sum(r["verified_roots"] for r in rs),probe_ns=sum(r["probe_ns"] for r in rs),migrated_entries=sum(r["migrated_entries"] for r in rs),material_losses_5pct=sum(r["total_ns"]>1.05*cells[(r["config"],r["encounter"],"TABULA_RASA")]["total_ns"] for r in rs))
    comparisons=[paired(normalized,"TABULA_RASA",p) for p in sorted(policies-{"TABULA_RASA"})]
    ablations=[paired(normalized,"SAPIENTIA",p) for p in sorted(policies-{"SAPIENTIA"})]
    return dict(source=receipt,metrics=metrics,comparisons=comparisons,ablations=ablations,oracle_cells=len(oracle),material_loss_definition="greater than 5% above matched TABULA_RASA",exploratory=True,native=False,economic_claims=False)

def main():
    p=argparse.ArgumentParser();p.add_argument("--home",type=Path,default=Path.home());p.add_argument("--sapientia",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    reports=[]
    for root in sorted(a.home.glob("BEAST-*")):
        for folder in (root,root/"evidence"):
            if (folder/"evidence.sha256").is_file(): reports.append(verify(folder)[0])
    result=reconstruct(a.sapientia)
    a.out.mkdir(parents=True,exist_ok=False)
    for n,obj in [("census-reconciled.json",reports),("sapientia-reconstructed.json",result)]:
        (a.out/n).write_text(json.dumps(obj,indent=2,allow_nan=False))
    (a.out/"evidence.sha256").write_text("".join(sha(f)+"  ./"+f.name+"\n" for f in sorted(a.out.iterdir())))
    print(json.dumps(dict(manifests=len(reports),consistent=sum(r["status"]=="HASH_CONSISTENT" for r in reports),refused=[dict(root=r["root"],errors=len(r["errors"]),sample=r["errors"][:2]) for r in reports if r["status"]=="REFUSE"],metrics=result["metrics"],comparisons=result["comparisons"],ablations=result["ablations"],scientific_authorization=False),indent=2))
if __name__=="__main__":main()
