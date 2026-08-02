from __future__ import annotations
import threading
class SequenceLedger:
    def __init__(self): self._lock=threading.Lock(); self._sent=0; self._received=0
    def next_send(self):
        with self._lock: self._sent+=1; return self._sent
    def accept(self, seq:int):
        with self._lock:
            if seq != self._received+1: raise ValueError("sequence gap or replay")
            self._received=seq
