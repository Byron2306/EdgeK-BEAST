import unittest
from pecunia import *
class Tests(unittest.TestCase):
 def setUp(self):
    self.s=['a','b']; self.o=[dict(lane=l,task=t,success=True) for l in ('control','beast') for t in self.s]; self.e=[dict(id='1',lane='beast',task=None,category='acquisition',actual=10,shadow=20),dict(id='2',lane='control',task='a',category='execution',actual=6,shadow=2),dict(id='3',lane='control',task='b',category='execution',actual=6,shadow=2)]
 def run_account(self): return account(self.s,self.e,self.o)
 def test_break_even(self): self.assertEqual(self.run_account()['observed_sustained_break_even'],{'actual':2,'shadow':None})
 def test_upfront(self): self.assertEqual(self.run_account()['totals']['beast'],[10,20])
 def test_duplicate(self):
    self.e.append(self.e[0]); self.assertRaises(ValueError,self.run_account)
 def test_missing(self):
    self.o.pop(); self.assertRaises(ValueError,self.run_account)
 def test_failure(self):
    self.o[-1]['success']=False; self.assertEqual(self.run_account()['cost_per_success']['beast'],['10','20'])
 def test_zero(self):
    for r in self.o: r['success']=False
    self.assertEqual(self.run_account()['cost_per_success']['beast'],[None,None])
 def test_negative(self):
    self.e[0]['actual']=-1; self.assertRaises(ValueError,self.run_account)
 def test_boolean(self):
    self.e[0]['actual']=True; self.assertRaises(ValueError,self.run_account)
 def test_allocation(self): self.assertEqual(allocate(10,{'a':1,'b':1,'c':1}),{'a':4,'b':3,'c':3})
 def test_depreciation(self): self.assertEqual(depreciation(100,20,100,25),20)
 def test_depreciation_invalid(self): self.assertRaises(ValueError,depreciation,100,20,100,101)
 def test_no_authority(self): self.assertFalse(self.run_account()['scientific_authorization'])
 def test_reversal(self):
    self.e[0]['actual']=1; self.e.append(dict(id='4',lane='beast',task='b',category='retention',actual=20,shadow=0)); self.assertIsNone(self.run_account()['observed_sustained_break_even']['actual'])
