"""Offline reservation ledger. No network or paid execution authority."""
import sqlite3, json, hashlib, contextlib

def canon(x): return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def sha(x): return hashlib.sha256(canon(x).encode()).hexdigest()
def check(ok,msg):
    if not ok: raise ValueError(msg)
def money(x): return type(x) is int and 0<=x<=10**15
class Ledger:
    def __init__(self,path,budget,simulation=True):
        check(simulation is True,'offline simulation only'); check(money(budget),'invalid budget')
        self.db=sqlite3.connect(path,timeout=30,isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL'); self.db.execute('PRAGMA synchronous=FULL')
        with self.tx():
            self.db.execute('CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY CHECK(id=1), budget INTEGER NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, body TEXT NOT NULL, digest TEXT NOT NULL)')
            self.db.execute('INSERT OR IGNORE INTO config VALUES(1,?)',(budget,))
            check(self.db.execute('SELECT budget FROM config').fetchone()[0]==budget,'budget mismatch')
            if not self.db.execute('SELECT 1 FROM events LIMIT 1').fetchone(): self.append({'op':'genesis','budget':budget})
    @contextlib.contextmanager
    def tx(self):
        self.db.execute('BEGIN IMMEDIATE')
        try: yield; self.db.execute('COMMIT')
        except BaseException: self.db.execute('ROLLBACK'); raise
    def append(self,b):
        last=self.db.execute('SELECT seq,digest FROM events ORDER BY seq DESC LIMIT 1').fetchone(); n,p=last or (0,'')
        self.db.execute('INSERT INTO events VALUES(?,?,?)',(n+1,canon(b),sha([n+1,p,b])))
    def replay(self):
        budget=self.db.execute('SELECT budget FROM config').fetchone()[0]; state={}; prev=''; spent=0; held=0; n=0
        for seq,body,h in self.db.execute('SELECT * FROM events ORDER BY seq'):
            b=json.loads(body); n+=1; check(seq==n and h==sha([n,prev,b]),'chain mismatch'); prev=h
            op=b['op']
            if n==1: check(b=={'op':'genesis','budget':budget},'genesis mismatch'); continue
            i=b['id']; a=b['amount']; check(money(a),'invalid amount')
            if op=='reserve':
                check(i not in state and a>0 and spent+held+a<=budget,'invalid reservation'); state[i]=['held',a]; held+=a
            elif op=='dispatch':
                check(state.get(i)==['held',a],'invalid dispatch'); state[i]=['uncertain',a]
            elif op=='cancel':
                check(state.get(i)==['held',a],'invalid cancellation'); held-=a; state[i]=['cancelled',a]
            elif op=='settle':
                check(i in state and state[i][0]=='uncertain','invalid settlement'); cap=state[i][1]; held-=cap; spent+=a; state[i]=['settled',a]
            else: raise ValueError('unknown operation')
        check(n>0,'missing genesis')
        return dict(budget=budget,spent=spent,held=held,available=budget-spent-held,head=prev,events=n,requests=state,overrun=spent+held>budget)
    def change(self,op,i,a=None):
        check(isinstance(i,str) and 0<len(i)<=256,'invalid id')
        with self.tx():
            s=self.replay(); r=s['requests'].get(i)
            if op=='reserve': check(r is None and money(a) and 0<a<=s['available'],'reservation refused')
            elif op in ('dispatch','cancel'): check(r is not None and r[0]=='held','not held'); a=r[1]
            elif op=='settle': check(r is not None and r[0]=='uncertain' and money(a),'settlement refused')
            else: raise ValueError('unknown operation')
            self.append(dict(op=op,id=i,amount=a)); return self.replay()
    def snapshot(self):
        with self.tx(): return self.replay()
