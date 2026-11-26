import unittest
from judicium import evaluate

def fixture(n=40,bc=50,bs=True):
    s=[dict(task=str(i),cluster=str(i)) for i in range(n)]
    r=[dict(**x,lane=l,success=True if l=='control' else bs,cost_micros=100 if l=='control' else bc) for x in s for l in ('control','beast')]
    return s,r
class Tests(unittest.TestCase):
    def run_case(self,*args): return evaluate(*fixture(*args),draws=1000)
    def test_win(self): self.assertEqual(self.run_case()['verdict'],'THRESHOLDS_SUPPORTED')
    def test_loss(self): self.assertEqual(self.run_case(40,110)['verdict'],'THRESHOLDS_CONTRADICTED')
    def test_zero_success(self): self.assertIsNone(self.run_case(40,1,False)['cost_per_success_saving'])
    def test_small(self): self.assertEqual(self.run_case(5)['verdict'],'INDETERMINATUM')
    def test_duplicate(self):
        s,r=fixture(); self.assertRaises(ValueError,evaluate,s,r+[r[0]])
    def test_missing(self):
        s,r=fixture(); self.assertRaises(ValueError,evaluate,s,r[:-1])
    def test_wrong_cluster(self):
        s,r=fixture(); r[0]['cluster']='wrong'; self.assertRaises(ValueError,evaluate,s,r)
    def test_bad_cost(self):
        s,r=fixture(); r[0]['cost_micros']=True; self.assertRaises(ValueError,evaluate,s,r)
    def test_failed_cost(self):
        s,r=fixture(); r[1]['success']=False; self.assertEqual(evaluate(s,r,draws=1000)['totals']['beast_cost_micros'],2000)
    def test_cluster_dependence(self):
        s,r=fixture();
        for x in s+r: x['cluster']='one'
        self.assertEqual(evaluate(s,r,draws=1000)['verdict'],'INDETERMINATUM')
    def test_reproducible(self): self.assertEqual(self.run_case(),self.run_case())
    def test_no_authorization(self): self.assertFalse(self.run_case()['scientific_authorization'])
