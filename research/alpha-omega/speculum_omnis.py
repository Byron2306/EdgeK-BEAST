"""Static read-only dashboard; local hash consistency is not external authenticity."""
import argparse,hashlib,json,html,re,stat
from pathlib import Path

def inspect(root):
    root=Path(root).resolve(strict=True)
    manifest=root/"evidence.sha256"
    if manifest.is_symlink(): raise ValueError("symlink manifest")
    entries={}
    for line in manifest.read_text().splitlines():
        m=re.fullmatch(r"([0-9a-f]{64}) [ *](.+)",line)
        if not m: raise ValueError("invalid manifest")
        h,name=m.groups(); p=root/name
        if Path(name).is_absolute() or ".." in Path(name).parts or p.resolve()!=p.absolute() or not p.is_file(): raise ValueError("unsafe path")
        name=str(p.relative_to(root))
        if name in entries or name=="evidence.sha256": raise ValueError("duplicate or self reference")
        with p.open("rb") as f: actual=hashlib.file_digest(f,"sha256").hexdigest()
        if actual!=h: raise ValueError("hash mismatch: "+name)
        entries[name]=h
    if not entries: raise ValueError("empty manifest")
    actual={str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p!=manifest}
    if actual!=set(entries): raise ValueError("unsealed files or missing entries")
    records={}
    for name in sorted(entries):
        if name.endswith(".json"):
            records[name]=json.loads((root/name).read_text())
    def summary(name,r):
        if not isinstance(r,dict): return {"type":type(r).__name__}
        keys=("status","defect","original_acceptance","counts","controls","correct","scientific_authorization","paid_execution_authorized","independent_custody","independent_principal","worlds")
        out={k:r[k] for k in keys if k in r}
        if "observation" in r:
            o=r["observation"];out["resources"]={k:o.get(k) for k in ("wall_ns","user_cpu_seconds","kernel_cpu_seconds","peak_rss_kib","energy_status","exit_code")}
        if name=="retis.json":
            out["transfers"]=len(r["rows"]);out["payload_bytes"]=sum(x["payload_received"] for x in r["rows"]);out["wire_bytes"]=None
        if "receipts" in r: out["receipt_count"]=len(r["receipts"])
        if "ledger" in r: out["ledger"]=r["ledger"]
        return out
    return dict(root=str(root),manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),verified_files=len(entries),records={n:summary(n,r) for n,r in records.items()},external_authenticity=False)

def render(reports):
    esc=html.escape
    cards=[]
    for r in reports:
        body="".join("<details open><summary>"+esc(n)+"</summary><pre>"+esc(json.dumps(v,indent=2))+"</pre></details>" for n,v in r["records"].items())
        cards.append("<section><h2>"+esc(Path(r["root"]).parent.name)+"</h2><p>"+str(r["verified_files"])+" files hash-verified · external authenticity unestablished</p><small>"+esc(r["manifest_sha256"])+"</small>"+body+"</section>")
    return """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SPECULUM OMNIS</title><style>body{background:#101722;color:#e2e8f0;font:16px system-ui;margin:0;padding:32px}main{max-width:1100px;margin:auto}h1{letter-spacing:.08em}section{background:#182334;border:1px solid #35445a;border-radius:12px;padding:20px;margin:20px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;color:#b8d4df}small{overflow-wrap:anywhere}summary{cursor:pointer;padding:8px 0}aside{border:1px solid #b58a48;padding:16px;border-radius:8px}</style><main><h1>SPECULUM OMNIS</h1><aside>OFFLINE EVIDENCE ONLY · PAID EXECUTION CLOSED · SCIENTIFIC AUTHORIZATION FALSE</aside>"""+ "".join(cards)+"</main></html>"

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",required=True);p.add_argument("roots",nargs="+");a=p.parse_args()
    out=Path(a.out).resolve()
    if any(out==Path(r).resolve() or Path(r).resolve() in out.parents for r in a.roots): raise ValueError("output inside sealed evidence")
    reports=[inspect(r) for r in a.roots]
    out.mkdir(parents=True,exist_ok=False)
    (out/"index.html").write_text(render(reports))
    (out/"inventory.json").write_text(json.dumps(dict(reports=reports,scientific_authorization=False,paid_execution_authorized=False),indent=2))
    print(json.dumps(dict(roots=len(reports),verified_files=sum(r["verified_files"] for r in reports),output=str(out))))
