"""Offline provider contract rehearsal. No network transport or credentials."""
from dataclasses import dataclass
from threading import RLock
import unittest

def nat(x):
    if type(x) is not int or x < 0:
        raise ValueError("invalid integer")
    return x

@dataclass(frozen=True)
class Usage:
    input: int
    cached: int
    output: int

@dataclass(frozen=True)
class Tariff:
    # Integer micro-USD per token; synthetic rates only.
    input: int
    cached: int
    output: int
    def price(self, u):
        for x in (self.input,self.cached,self.output,u.input,u.cached,u.output):
            nat(x)
        if u.cached > u.input:
            raise ValueError("cached exceeds input")
        return (u.input-u.cached)*self.input+u.cached*self.cached+u.output*self.output

class Gateway:
    def __init__(self,budget,model,tariff):
        self.budget=nat(budget)
        self.model=model
        self.tariff=tariff
        self.rows={}
        self.lock=RLock()
    def exposure(self):
        return sum(r["charge"] if r["state"]=="settled" else r["reserve"] for r in self.rows.values())
    def dispatch(self,identity,input_limit,output_limit):
        with self.lock:
            if not identity or identity in self.rows:
                raise ValueError("duplicate or empty request")
            reserve=nat(input_limit)*max(nat(self.tariff.input),nat(self.tariff.cached))+nat(output_limit)*nat(self.tariff.output)
            if self.exposure()+reserve>self.budget:
                raise ValueError("budget refused")
            self.rows[identity]={"state":"dispatched","reserve":reserve,"limits":(input_limit,output_limit)}
    def observe(self,identity,model,usage,complete):
        with self.lock:
            r=self.rows[identity]
            if r["state"]!="dispatched":
                raise ValueError("duplicate observation")
            r["state"]="uncertain"
            if model!=self.model or type(complete) is not bool or not complete:
                return False
            try:
                quote=self.tariff.price(usage)
                if usage.input>r["limits"][0] or usage.output>r["limits"][1]:
                    return False
            except (ValueError,AttributeError,TypeError):
                return False
            r["quote"]=quote
            return True
    def settle(self,identity,charge):
        # Simulator-only billing authority. Real adapter must authenticate settlement.
        with self.lock:
            nat(charge)
            r=self.rows[identity]
            if r["state"] not in ("dispatched","uncertain"):
                raise ValueError("duplicate settlement")
            r.update(state="settled",charge=charge,overrun=charge>r["reserve"],
                     discrepancy="quote" in r and r["quote"]!=charge)

class Simulacrum:
    def __init__(self,gateway):
        self.g=gateway
    def run(self,identity,scenario):
        self.g.dispatch(identity,10,5)
        usage=Usage(10,4,3)
        charge=self.g.tariff.price(usage)
        if scenario=="lost":
            return False
        model="substitute" if scenario=="substitution" else self.g.model
        if scenario=="malformed":
            usage=Usage(10,11,3)
        ok=self.g.observe(identity,model,usage,scenario!="interrupted")
        self.g.settle(identity,charge+100 if scenario=="overrun" else charge)
        return ok

class Controls(unittest.TestCase):
    def setUp(self):
        self.g=Gateway(100,"mock",Tariff(2,1,4))
        self.s=Simulacrum(self.g)
    def test_normal(self):
        self.assertTrue(self.s.run("a","normal"))
        self.assertEqual(self.g.exposure(),28)
    def test_lost(self):
        self.assertFalse(self.s.run("a","lost"))
        self.assertEqual(self.g.exposure(),40)
        self.g.settle("a",28)
        self.assertEqual(self.g.exposure(),28)
    def test_interrupted(self):
        self.assertFalse(self.s.run("a","interrupted"))
        self.assertEqual(self.g.exposure(),28)
    def test_substitution(self):
        self.assertFalse(self.s.run("a","substitution"))
    def test_malformed(self):
        self.assertFalse(self.s.run("a","malformed"))
    def test_duplicate(self):
        self.s.run("a","normal")
        with self.assertRaises(ValueError): self.g.settle("a",28)
        with self.assertRaises(ValueError): self.g.dispatch("a",10,5)
    def test_overrun(self):
        self.s.run("a","overrun")
        self.assertTrue(self.g.rows["a"]["overrun"])
        self.assertTrue(self.g.rows["a"]["discrepancy"])
        with self.assertRaises(ValueError): self.g.dispatch("b",10,5)
    def test_contention(self):
        from concurrent.futures import ThreadPoolExecutor
        def attempt(i):
            try:
                self.g.dispatch(str(i),10,5)
                return 1
            except ValueError: return 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt,range(40))),2)
    def test_bool(self):
        with self.assertRaises(ValueError): self.g.dispatch("a",True,5)

if __name__=="__main__":
    unittest.main(verbosity=2)
