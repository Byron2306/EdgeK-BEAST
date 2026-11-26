"""Offline authority admission prototype. Trust pins must arrive out of band."""
import sqlite3,json,sys,tempfile
from pathlib import Path
from evidence import digest,verify_chain,sign
from resurrectio import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

class Custodia:
    def __init__(self,path,registry,pin):
        if digest(registry)!=pin: raise ValueError("registry pin mismatch")
        self.registry=json.loads(json.dumps(registry))
        self.pin=pin
        self.db=sqlite3.connect(path,timeout=30,isolation_level=None)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS trust(pin TEXT PRIMARY KEY)")
        self.db.execute("CREATE TABLE IF NOT EXISTS admissions(campaign TEXT PRIMARY KEY, head TEXT NOT NULL, count INTEGER NOT NULL, evidence TEXT NOT NULL)")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            rows=self.db.execute("SELECT pin FROM trust").fetchall()
            if not rows: self.db.execute("INSERT INTO trust VALUES(?)",(pin,))
            elif rows!=[(pin,)]: raise ValueError("persistent trust mismatch")
            self.db.commit()
        except BaseException:
            self.db.rollback();self.db.close();raise
    def close(self): self.db.close()
    def admit(self,campaign,rows,commitment,commitment_pin):
        if digest(commitment)!=commitment_pin: raise ValueError("commitment pin mismatch")
        if commitment["campaign"]!=campaign or commitment["registry_pin"]!=self.pin: raise ValueError("campaign binding")
        if not rows or type(commitment["count"]) is not int or commitment["count"]<=0: raise ValueError("empty evidence")
        registry={n:(v["role"],Ed25519PublicKey.from_public_bytes(bytes.fromhex(v["key"]))) for n,v in self.registry.items()}
        verify_chain(rows,registry,campaign,commitment["count"],commitment["head"])
        if any(e["body"]["observer"]!=commitment["observer"] for e in rows): raise ValueError("observer mismatch")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("INSERT INTO admissions VALUES(?,?,?,?)",(campaign,commitment["head"],len(rows),json.dumps(rows,sort_keys=True)))
            self.db.commit()
        except BaseException:
            self.db.rollback();raise
        return {"status":"ADMITTED_OFFLINE","campaign":campaign,"head":commitment["head"],"paid_execution_authorized":False,"scientific_authorization":False}

def selftest():
    k=Ed25519PrivateKey.generate()
    reg={"examiner":{"role":"exam","key":k.public_key().public_bytes_raw().hex()}}
    pin=digest(reg); rows=[sign(k,"test","examiner","exam",0,"",{"passed":True})]
    commit=dict(campaign="test",registry_pin=pin,count=1,head=digest(rows[0]),observer="examiner")
    cp=digest(commit)
    def refused(f):
        try: f()
        except (ValueError,sqlite3.IntegrityError): return True
        return False
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"custody.db"; c=Custodia(p,reg,pin)
        controls={"valid":c.admit("test",rows,commit,cp)["status"]=="ADMITTED_OFFLINE"}
        controls["replay"]=refused(lambda:c.admit("test",rows,commit,cp))
        controls["commitment_mutation"]=refused(lambda:c.admit("test",rows,dict(commit,count=2),cp))
        controls["empty"]=refused(lambda:c.admit("test",[],commit,cp))
        controls["campaign_substitution"]=refused(lambda:c.admit("other",rows,commit,cp))
        c.close();c=Custodia(p,reg,pin)
        controls["restart_replay"]=refused(lambda:c.admit("test",rows,commit,cp))
        c.close()
        other={"examiner":{"role":"exam","key":Ed25519PrivateKey.generate().public_key().public_bytes_raw().hex()}}
        controls["registry_substitution"]=refused(lambda:Custodia(p,other,pin))
        controls["repinned_registry"]=refused(lambda:Custodia(p,other,digest(other)))
    return dict(controls=controls,independent_custody=False,external_pin_provisioning_tested=False,scientific_authorization=False,paid_execution_authorized=False)
if __name__=="__main__":
    r=selftest();print(json.dumps(r,indent=2));sys.exit(0 if all(r["controls"].values()) else 2)
