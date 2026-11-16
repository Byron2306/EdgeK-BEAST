#!/usr/bin/env python3
"""Read-only: catch who (re)loads Ollama models. Polls /api/ps; when a model appears, snapshots ss -tnp clients on :11434.

As byron, ss -p shows only byron's processes. Run under sudo to see every uid. Usage:
  .venv/bin/python scripts/ollama_load_watch.py --seconds 3600 --out .beast/ollama-load-watch.jsonl
"""
import argparse, json, subprocess, time, urllib.request


def ps(base):
    try:
        return {m["name"]: m.get("size_vram", 0) for m in json.loads(urllib.request.urlopen(base + "/api/ps", timeout=2).read())["models"]}
    except Exception:
        return {}


def clients():
    out = subprocess.run(["ss", "-tnpH", "dport = :11434 or sport = :11434"], capture_output=True, text=True, timeout=5).stdout
    return [l.split()[-1] if "users:" in l else l.split()[3] for l in out.splitlines()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:11434")
    ap.add_argument("--seconds", type=float, default=600)
    ap.add_argument("--interval", type=float, default=0.25)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    seen, end = ps(a.base), time.time() + a.seconds
    while time.time() < end:
        cur = ps(a.base)
        for m in set(cur) - set(seen):
            row = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "loaded": m, "size_vram_mib": cur[m] // 2**20, "clients": clients()}
            print(json.dumps(row), flush=True)
            if a.out:
                open(a.out, "a").write(json.dumps(row) + "\n")
        seen = cur
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
