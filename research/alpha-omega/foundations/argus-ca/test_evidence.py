import unittest, copy
from evidence import *
class Tests(unittest.TestCase):
 def setUp(self):
    self.k=Ed25519PrivateKey.generate(); self.reg={'a':('meter',self.k.public_key())}; self.r=sign(self.k,'c','a','meter',0,'',{'calls':1}); self.head=digest(self.r)
 def verify(self,rows): return verify_chain(rows,self.reg,'c',1,self.head)
 def test_valid(self): self.assertEqual(self.verify([self.r]),self.head)
 def test_mutation(self):
    r=copy.deepcopy(self.r); r['body']['payload']['calls']=0
    with self.assertRaises(Exception): self.verify([r])
 def test_truncation(self):
    with self.assertRaises(ValueError): self.verify([])
 def test_replay(self):
    with self.assertRaises(ValueError): self.verify([self.r,self.r])
 def test_wrong_key(self):
    with self.assertRaises(Exception): self.verify([sign(Ed25519PrivateKey.generate(),'c','a','meter',0,'',{})])
 def test_wrong_role(self):
    with self.assertRaises(ValueError): self.verify([sign(self.k,'c','a','judge',0,'',{})])
 def test_wrong_campaign(self):
    with self.assertRaises(ValueError): self.verify([sign(self.k,'other','a','meter',0,'',{})])
 def test_exam(self):
    c,s=commit_case('x',{'input':2},4); self.assertTrue(examine(c,s,'x',{'input':2},4)['passed']); self.assertFalse(examine(c,s,'x',{'input':2},5)['passed'])
 def test_changed_answer(self):
    c,s=commit_case('x',{},4); s['expected']=5
    with self.assertRaises(ValueError): examine(c,s,'x',{},5)
 def test_wrong_case(self):
    c,s=commit_case('x',{},4)
    with self.assertRaises(ValueError): examine(c,s,'y',{},4)
 def test_wrong_public(self):
    c,s=commit_case('x',{},4)
    with self.assertRaises(ValueError): examine(c,s,'x',{'changed':1},4)
if __name__=='__main__': unittest.main()
