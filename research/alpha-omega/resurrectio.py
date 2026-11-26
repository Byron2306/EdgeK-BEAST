"""RESURRECTIO: durable offline custody using the original ARGUS ledger."""
import sys
from pathlib import Path
from contextlib import contextmanager
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
ROOT=Path(__file__).resolve().parent
for name in ("argus-genesis","argus-ca"):
    sys.path.insert(0,str(ROOT/"foundations"/name))
from ledger import Ledger
from evidence import sign,verify_chain,digest
from provider_canon_simulacrum import Tariff,Usage

SCENARIOS=("normal","lost","interrupted","substitution","malformed","overrun")

class Custody:
    def __init__(self,path,budget,campaign,billing_public):
        self.path=path
        self.budget=budget
        self.campaign=campaign
        self.public=billing_public
    @contextmanager
    def ledger(self):
        l=Ledger(self.path,self.budget)
        try: yield l
        finally: l.db.close()
    def snapshot(self):
        with self.ledger() as l: return l.snapshot()
    def dispatch(self,identity,scenario):
        if scenario not in SCENARIOS: raise ValueError("unknown scenario")
        with self.ledger() as l:
            l.change("reserve",identity,40)
            return l.change("dispatch",identity)
    def settle(self,identity,receipt):
        b=receipt["body"]
        p=b["payload"]
        verify_chain([receipt],{"billing":("settlement",self.public)},self.campaign,1,digest(receipt))
        if b["observer"]!="billing" or p.get("execution")!=identity or set(p)!={"execution","charge"}:
            raise ValueError("settlement binding")
        with self.ledger() as l: return l.change("settle",identity,p["charge"])

def bill(key,campaign,identity,charge):
    return sign(key,campaign,"billing","settlement",0,"",dict(execution=identity,charge=charge))

def simulate(custody,key,identity,scenario,answer):
    custody.dispatch(identity,scenario)
    if scenario=="lost": return None
    charge=Tariff(2,1,4).price(Usage(10,4,3))
    if scenario=="overrun": charge+=100
    receipt=bill(key,custody.campaign,identity,charge)
    custody.settle(identity,receipt)
    return dict(answer=answer if scenario in ("normal","overrun") else None,receipt=receipt)

def strict_schedule(tasks,seed,lanes=("control","beast")):
    from fortuna import schedule
    if tuple(lanes)!=("control","beast"): raise ValueError("invalid lanes")
    return schedule(tasks,seed,lanes)

if __name__=="__main__":
    import unittest,tempfile
    class Controls(unittest.TestCase):
        def test_restart_and_signature(self):
            with tempfile.TemporaryDirectory() as d:
                k=Ed25519PrivateKey.generate()
                p=Path(d)/"ledger.db"
                c=Custody(p,100,"campaign",k.public_key())
                c.dispatch("a","lost")
                c=Custody(p,100,"campaign",k.public_key())
                self.assertEqual(c.snapshot()["held"],40)
                with self.assertRaises(Exception):
                    c.settle("a",bill(Ed25519PrivateKey.generate(),"campaign","a",0))
                self.assertEqual(c.snapshot()["held"],40)
                c.settle("a",bill(k,"campaign","a",28))
                self.assertEqual(c.snapshot()["spent"],28)
                with self.assertRaises(ValueError): c.settle("a",bill(k,"campaign","a",28))
        def test_invalid(self):
            with tempfile.TemporaryDirectory() as d:
                k=Ed25519PrivateKey.generate()
                c=Custody(Path(d)/"ledger.db",100,"campaign",k.public_key())
                with self.assertRaises(ValueError): c.dispatch("a","unknown")
                self.assertEqual(c.snapshot()["held"],0)
                with self.assertRaises(ValueError): strict_schedule([],7,("","beast"))
    unittest.main(verbosity=2)
