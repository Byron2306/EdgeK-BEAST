import unittest,tempfile,concurrent.futures
from pathlib import Path
from ledger import Ledger
class Tests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory(); self.p=Path(self.tmp.name)/'ledger.db'; self.l=Ledger(self.p,100)
 def tearDown(self): self.l.db.close(); self.tmp.cleanup()
 def test_concurrent(self):
    def f(i):
      l=Ledger(self.p,100)
      try: l.change('reserve',str(i),10); return 1
      except ValueError: return 0
      finally: l.db.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as e: self.assertEqual(sum(e.map(f,range(40))),10)
    self.assertEqual(self.l.snapshot()['held'],100)
 def test_uncertain(self):
    self.l.change('reserve','a',80); self.l.change('dispatch','a'); l=Ledger(self.p,100)
    try:
      self.assertEqual(l.snapshot()['held'],80)
      with self.assertRaises(ValueError): l.change('cancel','a')
      with self.assertRaises(ValueError): l.change('reserve','b',21)
    finally: l.db.close()
 def test_settlement(self):
    self.l.change('reserve','a',80); self.l.change('dispatch','a'); s=self.l.change('settle','a',30); self.assertEqual(s['available'],70)
    with self.assertRaises(ValueError): self.l.change('settle','a',30)
 def test_overrun(self):
    self.l.change('reserve','a',80); self.l.change('dispatch','a'); self.assertTrue(self.l.change('settle','a',110)['overrun'])
    with self.assertRaises(ValueError): self.l.change('reserve','b',1)
 def test_cancel(self):
    self.l.change('reserve','a',80); self.assertEqual(self.l.change('cancel','a')['available'],100)
    with self.assertRaises(ValueError): self.l.change('reserve','a',1)
 def test_tamper(self):
    self.l.change('reserve','a',80); self.l.db.execute("UPDATE events SET body='{}' WHERE seq=2")
    with self.assertRaises(ValueError): self.l.snapshot()
 def test_budget(self):
    with self.assertRaises(ValueError): Ledger(self.p,101)
 def test_live(self):
    with self.assertRaises(ValueError): Ledger(self.p,100,False)
 def test_invalid(self):
    for a in [True,-1,0,1.2,101]:
      with self.assertRaises(ValueError): self.l.change('reserve','a',a)
if __name__=='__main__': unittest.main()
