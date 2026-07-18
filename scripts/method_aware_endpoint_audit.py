"""Probe declared HTTP verbs without mutating production state.

The route-discovery audit intentionally reports 405 as inconclusive. This
helper accepts a JSON manifest of ``{"path", "method", "payload"}`` probes
and records status, response shape, and whether the endpoint was exercised
with its declared verb. Payloads must be harmless fixtures supplied by the
caller.
"""
from __future__ import annotations
import argparse, json, urllib.request, urllib.error

def probe(base: str, item: dict) -> dict:
    body = item.get("payload")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base.rstrip("/") + item["path"], data=data,
        method=item["method"].upper(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=float(item.get("timeout", 5))) as res:
            raw = res.read(); status = res.status
    except urllib.error.HTTPError as exc:
        raw = exc.read(); status = exc.code
    except Exception as exc:
        return {**item, "status": None, "classification": "transport_error", "error": str(exc)}
    try: parsed = json.loads(raw.decode()) if raw else None
    except Exception: parsed = None
    classification = "contract_response" if 200 <= status < 300 else "declared_method_reached"
    return {**item, "status": status, "classification": classification, "json": parsed is not None}

def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("manifest"); parser.add_argument("--base", default="http://127.0.0.1:8001")
    parser.add_argument("--output", required=True); args = parser.parse_args()
    items = json.loads(open(args.manifest, encoding="utf-8").read())
    results = [probe(args.base, item) for item in items]
    with open(args.output, "w", encoding="utf-8") as handle: json.dump(results, handle, indent=2, sort_keys=True)

if __name__ == "__main__": main()
