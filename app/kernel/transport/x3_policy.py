from .x3_contracts import TransportMode
def choose_mode(metrics,min_delivery=.999,max_p99_us=5000.0):
    candidates=[]
    by={m.mode:m for m in metrics}
    for mode in (TransportMode.AF_XDP_ZERO_COPY,TransportMode.AF_XDP_COPY,TransportMode.UDP_FALLBACK):
        m=by.get(mode)
        if not m: continue
        m.validate()
        if m.delivery_ratio>=min_delivery and m.p99_latency_us<=max_p99_us:
            candidates.append((m.cpu_user_seconds+m.cpu_system_seconds,m.p99_latency_us,-m.delivery_ratio,mode))
    if candidates: return min(candidates)[3]
    if TransportMode.UDP_FALLBACK in by: return TransportMode.UDP_FALLBACK
    raise RuntimeError("no governed transport mode available")
