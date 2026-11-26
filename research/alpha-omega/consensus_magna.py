"""Read-only historical census. Candidate decisions are not scientific authorization."""
import argparse,hashlib,json,re,random,statistics,math
from pathlib import Path

def sha(p):
    with p.open("rb") as f: return hashlib.file_digest(f,"sha256").hexdigest()

def census(home):
    reports=[]
    for root in sorted(home.glob("BEAST-*")):
        for folder in (root,root/"evidence"):
            m=folder/"evidence.sha256"
            if not m.is_file(): continue
            entries={}; errors=[]
            for line in m.read_text().splitlines():
                match=re.fullmatch(r"([0-9a-f]{64}) [ *](.+)",line)
                if not match:
                    errors.append("unsupported manifest line");continue
                h,n=match.groups(); p=folder/n
                if Path(n).is_absolute() or ".." in Path(n).parts or not p.resolve().is_relative_to(folder.resolve()):
                    errors.append("unsafe path "+n);continue
                n=str(p.relative_to(folder))
                if n in entries: errors.append("duplicate "+n);continue
                entries[n]=h
                if not p.is_file() or sha(p)!=h: errors.append("missing or changed "+n)
            summaries={}
            if not errors and entries:
                for n in entries:
                    if Path(n).name in ("summary.json","policy-summary.json","acceptance.json","negative-adjudication.json","source-commit.txt"):
                        try:
                            summaries[n]=json.loads((folder/n).read_text()) if n.endswith(".json") else (folder/n).read_text().strip()
                        except (ValueError,OSError) as e: errors.append("parse "+n+": "+str(e))
            reports.append(dict(root=str(folder),manifest_sha256=sha(m),entries=len(entries),errors=errors,status="HASH_CONSISTENT" if entries and not errors else "REFUSE",summaries=summaries,external_authenticity=False))
    return reports

def paired(rows,baseline,candidate,draws=10000,seed=20261126):
    """Normalized rows: configuration, encounter, policy, wall_ns. No imputation."""
    cells={}
    for r in rows:
        if r["policy"] not in (baseline,candidate): continue
        k=(str(r["configuration"]),str(r["encounter"]))
        v=r["wall_ns"]
        if type(v) is not int or v<=0: raise ValueError("invalid wall time")
        d=cells.setdefault(k,{})
        if r["policy"] in d: raise ValueError("duplicate trial")
        d[r["policy"]]=v
    clusters={}
    for (config,encounter),d in cells.items():
        if set(d)!={baseline,candidate}: raise ValueError("unpaired trial")
        a,b=clusters.setdefault(config,[0,0]);clusters[config]=[a+d[baseline],b+d[candidate]]
    g=[clusters[k] for k in sorted(clusters)]
    if not g: raise ValueError("empty comparison")
    a=sum(x[0] for x in g);b=sum(x[1] for x in g)
    rng=random.Random(seed); samples=[]
    for _ in range(draws):
        s=rng.choices(g,k=len(g));samples.append(1-sum(x[1] for x in s)/sum(x[0] for x in s))
    samples.sort()
    return dict(baseline=baseline,candidate=candidate,clusters=len(g),pairs=len(cells),speedup=a/b,time_saving=1-b/a,interval=[samples[int(.025*(draws-1))],samples[math.ceil(.975*(draws-1))]],draws=draws,seed=seed,exploratory=True)

def candidate():
    # Design hypotheses from prior campaign discussion; not automatically proven by census.
    items=[
      ("crystallis","CORE_CANDIDATE","exact identity and verified result; otherwise fresh compute"),
      ("hereditas","CORE_CANDIDATE","compatible lineage and dependency validation"),
      ("mycelium","CORE_CANDIDATE","select reuse level; bounded memory"),
      ("sapientia","CORE_CANDIDATE","calibrate cost-aware selection before exam"),
      ("historia","CONDITIONAL","stable workloads; calibration only"),
      ("lattice","CONDITIONAL","verified composition and ordering"),
      ("exogenesis","CONDITIONAL","authenticated admission; no automatic promotion"),
      ("mercurial","CONDITIONAL","measured net transport benefit and authority"),
      ("migration","EXPERIMENTAL","require actual exposure and matched benefit"),
      ("xdp","SPECIALIST","supported hardware and matched end-to-end benefit"),
      ("native_kv","EXPERIMENTAL","engine provenance and compatibility required"),
      ("sovereign","MANDATORY","fail closed on missing authority"),
      ("argus","MANDATORY","account all costs and independent correctness"),
      ("primitive","MANDATORY","fallback and matched comparator")]
    return dict(schema="beast.optim us.candidate.v1".replace(" ",""),status="PROVISIONAL_NOT_FROZEN",capabilities=[dict(name=n,disposition=d,activation=a,evidence_adjudicated=False) for n,d,a in items],scientific_authorization=False,paid_execution_authorized=False,blockers=["RAW_TRIAL_RECONSTRUCTION_REQUIRED","CROSS_CAMPAIGN_ADJUDICATION_REQUIRED","NATIVE_INTEGRATION_REQUIRED","INDEPENDENT_AUTHORITY_REQUIRED","PREREGISTRATION_REQUIRED"])

def main():
    p=argparse.ArgumentParser();p.add_argument("--home",type=Path,default=Path.home());p.add_argument("--out",type=Path,required=True);p.add_argument("--normalized-trials",type=Path);a=p.parse_args()
    reports=census(a.home)
    if not reports: raise SystemExit("No sealed campaigns found")
    comparisons=[]
    if a.normalized_trials:
        rows=[json.loads(l) for l in a.normalized_trials.read_text().splitlines() if l.strip()]
        for policy in sorted({r["policy"] for r in rows}-{"SAPIENTIA"}):
            comparisons.append(paired(rows,policy,"SAPIENTIA"))
    a.out.mkdir(parents=True,exist_ok=False)
    for name,obj in [("census.json",reports),("paired-statistics.json",comparisons),("OPTIMISED-BEAST.json",candidate())]:
        (a.out/name).write_text(json.dumps(obj,indent=2,allow_nan=False))
    files=sorted(a.out.iterdir())
    (a.out/"evidence.sha256").write_text("".join(sha(f)+"  ./"+f.name+"\n" for f in files))
    print(json.dumps(dict(manifests=len(reports),consistent=sum(r["status"]=="HASH_CONSISTENT" for r in reports),refused=sum(r["status"]=="REFUSE" for r in reports),comparisons=len(comparisons),status="CENSUS_COMPLETE_CANDIDATE_ONLY",output=str(a.out)),indent=2))
if __name__=="__main__": main()
