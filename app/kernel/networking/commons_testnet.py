"""Local non-financial BEASTCOIN testnet accounts, wallets, and ledger."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.kernel.networking.commons_anti_gaming import CommonsAntiGaming


def now() -> datetime:
    return datetime.now(timezone.utc)


class CommonsTestnet:
    ASSETS = {"BEASTCOIN", "CRYSTAL"}
    RATE = 10  # 10 BEASTCOIN atomic units per CRYSTAL atomic unit

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path(__file__).resolve().parents[2] / "data/commons_testnet.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init(self):
        with self.connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS accounts(user_id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,display_name TEXT NOT NULL,password_hash TEXT NOT NULL,salt TEXT NOT NULL,created_at TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires_at TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ledger(entry_id TEXT PRIMARY KEY,tx_id TEXT NOT NULL,account_id TEXT NOT NULL,asset TEXT NOT NULL,amount INTEGER NOT NULL,kind TEXT NOT NULL,reference TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS ledger_account_idx ON ledger(account_id,created_at);
            CREATE TABLE IF NOT EXISTS credit_claims(evidence_fingerprint TEXT PRIMARY KEY,credit_id TEXT UNIQUE NOT NULL,user_id TEXT NOT NULL,space_id TEXT NOT NULL,units INTEGER NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS swaps(swap_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,from_asset TEXT NOT NULL,to_asset TEXT NOT NULL,amount_in INTEGER NOT NULL,amount_out INTEGER NOT NULL,fee INTEGER NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS signup_events(source_hash TEXT NOT NULL,day TEXT NOT NULL,user_id TEXT NOT NULL,PRIMARY KEY(source_hash,day,user_id));
            """)

    @staticmethod
    def _password(password: str, salt: bytes) -> str:
        return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()

    def signup(self, email: str, display_name: str, password: str, source: str = "local_test") -> Dict[str, Any]:
        email = email.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("valid email required")
        if len(password) < 12 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            raise ValueError("password requires at least 12 characters, a letter, and a number")
        salt = secrets.token_bytes(16); user_id = "user_" + uuid.uuid4().hex[:20]; created = now().isoformat()
        source_hash=hashlib.sha256(source.encode()).hexdigest(); day=now().date().isoformat()
        try:
            with self.connect() as c:
                if c.execute("SELECT COUNT(*) FROM signup_events WHERE source_hash=? AND day=?",(source_hash,day)).fetchone()[0]>=3:
                    raise ValueError("daily signup faucet limit reached for this source")
                issued=-(c.execute("SELECT COALESCE(SUM(amount),0) FROM ledger WHERE account_id='system_treasury' AND asset='BEASTCOIN' AND kind='genesis_faucet'").fetchone()[0])
                if issued>=1_000_000: raise ValueError("global testnet faucet cap reached")
                c.execute("INSERT INTO accounts VALUES(?,?,?,?,?,?,1)",(user_id,email,display_name.strip()[:80],self._password(password,salt),salt.hex(),created))
                self._post(c,user_id,"BEASTCOIN",1000,"genesis_faucet","one_per_account")
                c.execute("INSERT INTO signup_events VALUES(?,?,?)",(source_hash,day,user_id))
        except sqlite3.IntegrityError as exc:
            raise ValueError("account already exists") from exc
        return {"user_id":user_id,"email":email,"display_name":display_name.strip()[:80],"created_at":created}

    def login(self, email: str, password: str) -> Dict[str, Any]:
        with self.connect() as c:
            row=c.execute("SELECT * FROM accounts WHERE email=? AND active=1",(email.strip().lower(),)).fetchone()
            if not row or not hmac.compare_digest(row["password_hash"],self._password(password,bytes.fromhex(row["salt"]))):
                raise ValueError("invalid credentials")
            token=secrets.token_urlsafe(32); expires=now()+timedelta(hours=12)
            c.execute("DELETE FROM sessions WHERE expires_at<?",(now().isoformat(),))
            c.execute("INSERT INTO sessions VALUES(?,?,?,?)",(hashlib.sha256(token.encode()).hexdigest(),row["user_id"],expires.isoformat(),now().isoformat()))
        return {"token":token,"expires_at":expires.isoformat(),"account":self.account(row["user_id"])}

    def authenticate(self, token: str) -> Dict[str, Any]:
        digest=hashlib.sha256(token.encode()).hexdigest()
        with self.connect() as c:
            row=c.execute("SELECT user_id FROM sessions WHERE token_hash=? AND expires_at>?",(digest,now().isoformat())).fetchone()
        if not row: raise ValueError("authentication required")
        return self.account(row["user_id"])

    def logout(self, token: str):
        with self.connect() as c: c.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))

    def account(self,user_id:str)->Dict[str,Any]:
        with self.connect() as c: row=c.execute("SELECT user_id,email,display_name,created_at FROM accounts WHERE user_id=?",(user_id,)).fetchone()
        if not row: raise ValueError("account not found")
        return dict(row)

    def _post(self,c,user_id,asset,amount,kind,reference):
        tx="tx_"+uuid.uuid4().hex; stamp=now().isoformat()
        for account,value in (("system_treasury",-int(amount)),(user_id,int(amount))):
            c.execute("INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?)",("entry_"+uuid.uuid4().hex,tx,account,asset,value,kind,reference,stamp))
        return tx

    def wallet(self,user_id:str)->Dict[str,Any]:
        with self.connect() as c:
            balances={row["asset"]:int(row["balance"]) for row in c.execute("SELECT asset,SUM(amount) balance FROM ledger WHERE account_id=? GROUP BY asset",(user_id,))}
            rows=[dict(x) for x in c.execute("SELECT tx_id,asset,amount,kind,reference,created_at FROM ledger WHERE account_id=? ORDER BY created_at DESC LIMIT 50",(user_id,))]
        return {"beast_object_type":"beastcoin_testnet_wallet","network":"BEAST_TESTNET_LOCAL","financial_value":None,"balances":{a:balances.get(a,0) for a in sorted(self.ASSETS)},"ledger":rows,"claim_boundary":"Mock units are non-financial, non-transferable outside this local testnet, and not redeemable for money."}

    def claim_credit(self,user_id:str,credit:Dict[str,Any])->Dict[str,Any]:
        fingerprint=str(credit.get("evidence_fingerprint") or ""); credit_id=str(credit.get("credit_id") or "")
        if not fingerprint or not credit_id: raise ValueError("verified credit evidence required")
        units=max(1,int(credit.get("credit_units") or 0))
        try:
            with self.connect() as c:
                c.execute("INSERT INTO credit_claims VALUES(?,?,?,?,?,?)",(fingerprint,credit_id,user_id,str(credit.get("space_id") or ""),units,now().isoformat()))
                tx=self._post(c,user_id,"CRYSTAL",units,"proof_credit_mint",fingerprint)
        except sqlite3.IntegrityError as exc: raise ValueError("credit evidence already claimed") from exc
        return {"claimed":True,"credit_id":credit_id,"units":units,"asset":"CRYSTAL","tx_id":tx}

    def swap(self,user_id:str,from_asset:str,amount:int)->Dict[str,Any]:
        from_asset=from_asset.upper(); to_asset="CRYSTAL" if from_asset=="BEASTCOIN" else "BEASTCOIN"
        if from_asset not in self.ASSETS or amount<10 or amount>10000: raise ValueError("invalid or out-of-range swap")
        wallet=self.wallet(user_id); available=wallet["balances"][from_asset]
        fee=max(1,math.ceil(amount*.01)); net=amount-fee; out=net//self.RATE if from_asset=="BEASTCOIN" else net*self.RATE
        if available<amount or out<1: raise ValueError("insufficient balance")
        with self.connect() as c:
            day=now().date().isoformat(); used=c.execute("SELECT COALESCE(SUM(amount_in),0) FROM swaps WHERE user_id=? AND created_at LIKE ?",(user_id,day+"%" )).fetchone()[0]
            if used+amount>20000: raise ValueError("daily anti-gaming swap cap exceeded")
            swap_id="swap_"+uuid.uuid4().hex; stamp=now().isoformat(); tx="tx_"+uuid.uuid4().hex
            for account,asset,value in ((user_id,from_asset,-amount),("system_pool",from_asset,amount),("system_pool",to_asset,-out),(user_id,to_asset,out)):
                c.execute("INSERT INTO ledger VALUES(?,?,?,?,?,?,?,?)",("entry_"+uuid.uuid4().hex,tx,account,asset,value,"mock_swap",swap_id,stamp))
            c.execute("INSERT INTO swaps VALUES(?,?,?,?,?,?,?,?)",(swap_id,user_id,from_asset,to_asset,amount,out,fee,stamp))
        return {"swap_id":swap_id,"from_asset":from_asset,"to_asset":to_asset,"amount_in":amount,"amount_out":out,"fee":fee,"rate":"10 BEASTCOIN = 1 CRYSTAL","financial_value":None}

    def pricing(self,credits:list[Dict[str,Any]])->Dict[str,Any]:
        rows=[]
        for credit in credits:
            try: age=max(0,(now()-datetime.fromisoformat(credit["created_at"])).total_seconds()/86400)
            except Exception: age=0
            decay=round(.5**(age/90),6); units=int(credit.get("credit_units") or 0)
            rows.append({"credit_id":credit.get("credit_id"),"space_id":credit.get("space_id"),"nominal_units":units,"age_days":round(age,3),"decay_multiplier":decay,"effective_units":round(units*decay,3),"expires_after_days":365})
        return {"beast_object_type":"beastcoin_long_term_credit_pricing","half_life_days":90,"credits":rows,"rules":["proof evidence mints once","90-day value half-life","365-day expiry candidate","demotion freezes new minting","false suppression triggers review/clawback candidate"],"financial_value":None}

    def audit(self)->Dict[str,Any]:
        with self.connect() as c:
            invariants={row["asset"]:int(row["total"]) for row in c.execute("SELECT asset,SUM(amount) total FROM ledger GROUP BY asset")}
            accounts=c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]; claims=c.execute("SELECT COUNT(*) FROM credit_claims").fetchone()[0]; swaps=c.execute("SELECT COUNT(*) FROM swaps").fetchone()[0]
            signup_rows=[dict(x) for x in c.execute("SELECT source_hash,user_id,day FROM signup_events")]; swap_rows=[dict(x) for x in c.execute("SELECT user_id,from_asset,to_asset,amount_in,created_at FROM swaps")]; claim_rows=[dict(x) for x in c.execute("SELECT user_id,space_id,units,created_at FROM credit_claims")]
        balanced=all(v==0 for v in invariants.values())
        pressure=CommonsAntiGaming().analyze(signup_events=signup_rows,swaps=swap_rows,claims=claim_rows,ledger_balanced=balanced)
        return {"beast_object_type":"beastcoin_testnet_anti_gaming_audit","accounts":accounts,"credit_claims":claims,"swaps":swaps,"double_entry_asset_totals":invariants,"double_entry_balanced":balanced,"large_scale_analysis":pressure,"controls":["unique email","scrypt passwords","hashed expiring sessions","three signup grants per source/day","global faucet cap","unique evidence fingerprint and credit id","integer atomic units","double-entry ledger","per-user daily swap cap","bounded swap size","owner-bound credit claims","Sybil clusters","wash-cycle detection","velocity and concentration scoring","non-financial local testnet only"]}
