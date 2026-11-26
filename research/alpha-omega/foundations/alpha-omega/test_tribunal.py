import unittest, copy
from tribunal import alpha,omega,digest,load
class Test(unittest.TestCase):
 def setUp(self):
  self.p=load('constitution.json'); self.s=[dict(id='1',lane='beast_full',task='t',lineage='l',provider='ollama',model='fixture')]; self.c=alpha(self.p); self.c['schedule_sha256']=digest(self.s); self.r=[dict(self.s[0],verified=True,cash_micros=0,shadow_micros=10,calls=0)]
 def test_valid(self): self.assertEqual(omega(self.p,self.c,self.s,self.r)['scientific_verdict'],'INDETERMINATUM')
 def test_missing(self): self.assertRaises(ValueError,omega,self.p,self.c,self.s,[])
 def test_duplicate(self): self.assertRaises(ValueError,omega,self.p,self.c,self.s,self.r*2)
 def test_mutation(self): self.r[0]['model']='other'; self.assertRaises(ValueError,omega,self.p,self.c,self.s,self.r)
 def test_spend(self): self.r[0]['cash_micros']=1; self.assertRaises(ValueError,omega,self.p,self.c,self.s,self.r)
 def test_failed(self): self.r[0]['verified']=False; self.assertIsNone(omega(self.p,self.c,self.s,self.r)['totals']['beast_full']['shadow_per_success_micros'])
 def test_plan(self): self.p['paid_execution_authorized']=True; self.assertRaises(ValueError,alpha,self.p)
 def test_schedule(self): self.s[0]['task']='other'; self.assertRaises(ValueError,omega,self.p,self.c,self.s,self.r)
if __name__=='__main__': unittest.main()
