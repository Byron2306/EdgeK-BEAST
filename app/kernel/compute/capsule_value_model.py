from __future__ import annotations
import time
class CapsuleValueModel:
    def score(self, entry, *, recompilation_cost_ms:float, memory_cost_per_mb_second:float=0.00001):
        remaining=max(0.0,(entry.expires_ns-time.time_ns())/1e9)
        avoided=max(0.0,recompilation_cost_ms)*max(1,entry.predicted_reuse_count)
        residency=(entry.size_bytes/(1024*1024))*remaining*memory_cost_per_mb_second
        debt=max(0.0,entry.preparation_cost_ms)+residency
        return {'gross_avoided_ms':avoided,'estimated_cost_ms':debt,'net_value_ms':avoided-debt,'retain_recommended':avoided>=debt}
