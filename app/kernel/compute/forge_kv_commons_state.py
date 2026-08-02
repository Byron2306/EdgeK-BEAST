"""Payload-free Commons contribution read model."""
from __future__ import annotations
from collections import Counter
class CommonsContributionState:
    def __init__(self): self._items=[]
    def record(self,receipt): self._items.append(dict(receipt))
    def state(self):
        statuses=Counter(str(x.get('status') or 'unknown') for x in self._items)
        return {'beast_object_type':'forge_kv_commons_state','authority':'read_only','contributions':len(self._items),'statuses':dict(statuses),'recent':tuple({k:v for k,v in x.items() if k not in {'token','credentials','payload'}} for x in self._items[-20:])}
