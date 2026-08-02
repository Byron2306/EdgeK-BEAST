"""Bounded publication progress stream."""
from __future__ import annotations
from collections import deque
from threading import Condition
from time import monotonic
class ProgressStream:
    def __init__(self, capacity: int=256): self.capacity=capacity; self._q=deque(maxlen=capacity); self._cv=Condition(); self._seq=0; self.dropped=0
    def publish(self,event_type:str,**payload):
        with self._cv:
            if len(self._q)==self.capacity: self.dropped+=1
            self._seq+=1; item={"sequence":self._seq,"event_type":event_type,"monotonic":monotonic(),"payload":payload}
            self._q.append(item); self._cv.notify_all(); return item
    def snapshot(self,since:int=0):
        with self._cv: return [x for x in self._q if x["sequence"]>since]
