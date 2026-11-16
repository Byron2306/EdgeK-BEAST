import importlib.util
import struct
from pathlib import Path

spec = importlib.util.spec_from_file_location("x7w", Path(__file__).resolve().parents[1] / "scripts" / "beast_x7_admit_writer.py")
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


def test_layout_matches_bpf_structs():
    d = w.pack_dst("127.0.0.1", 11434)
    assert len(d) == 20 and d[10:12] == b"\xff\xff" and d[12:16] == bytes([127, 0, 0, 1])
    assert d[16:18] == struct.pack("!H", 11434) and struct.unpack("<H", d[18:20])[0] == 10
    assert w.pack_dst("::ffff:127.0.0.1", 11434) == d
    assert len(w.pack_key(42, "127.0.0.1", 11434)) == 28
    t = w.pack_token(7, 9, "989152dc08af68fb", 123)
    assert struct.unpack("<QQQQ", t) == (7, 9, 0x989152dc08af68fb, 123)


def test_dry_run_prints_commands_only(tmp_path, capsys):
    q = tmp_path / "q.jsonl"
    import json, time, os
    q.write_text(json.dumps({"pid": os.getpid(), "host": "127.0.0.1:11434", "receipt_prefix": "ab" * 8, "ttl_ms": 1000, "at": time.time()}) + "\n")
    assert w.main(["--queue", str(q)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 2 and all(l.startswith("/usr/sbin/bpftool map update pinned /sys/fs/bpf/beast/x7/") for l in out)
