"""Benchmark-only shared corpus, lexical/latent-vector ranking, and Memory Hull controls."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import time

MAX_BYTES = 1800
TOP_K = 3
CHUNK_LINES = 14
MAX_CHUNK_CHARS = 390
VECTOR_RANK = 24


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def _terms(text):
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return re.findall(r"[a-z][a-z0-9]+", text.lower())


def corpus_for(root, paths):
    corpus = []
    for path in sorted(set(paths)):
        if not path.endswith(".py") or path == "test_public.py":
            continue
        source = root / path
        if Path(path).is_absolute() or not source.resolve().is_relative_to(root.resolve()):
            raise ValueError("corpus input escapes fixture")
        lines = source.read_text(encoding="utf-8").splitlines()
        for start in range(0, len(lines), CHUNK_LINES):
            chunk = {"path": path, "line": start + 1,
                     "excerpt": "\n".join(lines[start:start + CHUNK_LINES])[:MAX_CHUNK_CHARS]}
            if chunk["excerpt"].strip():
                corpus.append({"id": digest(chunk), **chunk})
    return corpus


def _scores(corpus, query, arm):
    terms = set(_terms(query))
    docs = [Counter(_terms(f"{d['path']} {d['excerpt']}")) for d in corpus]
    df = Counter(term for doc in docs for term in doc)
    n = len(docs)
    if not n:
        return []
    if arm == "lexical":
        average = sum(map(lambda doc: sum(doc.values()), docs)) / n
        return [
            sum(math.log1p((n - df[t] + 0.5) / (df[t] + 0.5)) * doc[t] * 2.2
                / (doc[t] + 1.2 * (0.25 + 0.75 * sum(doc.values()) / average))
                for t in terms if doc[t])
            if doc and average else 0 for doc in docs
        ]

    import numpy as np

    vocab = sorted(df, key=lambda t: (-df[t], t))[:768]
    if not vocab:
        return [0] * n
    weights = np.array([math.log((1 + n) / (1 + df[t])) + 1 for t in vocab])
    x = np.array([[math.log1p(doc[t]) for t in vocab] for doc in docs]) * weights
    q = np.array([float(t in terms) for t in vocab]) * weights
    # True low-rank vectors learned from this frozen corpus, no neural model,
    # hosted embedding requests, or lexical fallback.
    values, vectors = np.linalg.eigh(x @ x.T)
    chosen = [i for i in range(n - 1, -1, -1) if values[i] > 1e-8][:VECTOR_RANK]
    if not chosen:
        return [0] * n
    basis = (vectors[:, chosen].T @ x) / np.sqrt(values[chosen])[:, None]
    document_vectors, query_vector = x @ basis.T, q @ basis.T
    denominator = np.linalg.norm(document_vectors, axis=1) * np.linalg.norm(query_vector)
    return np.divide(document_vectors @ query_vector, denominator,
                     out=np.zeros(n), where=denominator > 1e-12).tolist()


BACKENDS = {"file_list": "none", "lexical": "bm25", "vector": "local_lsa_tfidf_cosine"}


def build_retrieval(root: Path, paths: list[str], arm: str, query: str) -> dict:
    backend = BACKENDS[arm]
    start = time.perf_counter()
    corpus = corpus_for(root, paths)
    corpus_sha = digest(corpus)
    chunks = []
    if arm != "file_list":
        scores = _scores(corpus, query, arm)
        for i in sorted(range(len(scores)), key=lambda i: (-round(scores[i], 10), i)):
            if len(chunks) == TOP_K or scores[i] < 1e-8:
                break
            if len(encode([*chunks, corpus[i]])) <= MAX_BYTES:
                chunks.append(corpus[i])
    return {"backend": backend, "corpus_sha256": corpus_sha, "corpus_chunks": len(corpus),
            "query_sha256": digest(query), "chunks": chunks,
            "chunk_bytes": len(encode(chunks)) if chunks else 0,
            "seconds": round(time.perf_counter() - start, 6)}


def scoped_recall(hull, query, repo, revision):
    rows = hull.search(query, section="tasks", limit=16)
    expected = {f"repo:{repo}", f"revision:{revision}"}
    output, excluded = [], []
    for row in rows:
        tags = {tag for tag in row["policy_tags"] if tag.startswith(("repo:", "revision:"))}
        if tags == expected and row["verified"]:
            output.append(row["residue_id"])
        else:
            excluded.append(row["residue_id"])
    return output, excluded


def memory_controls():
    from app.kernel.storage.memory_hull import MemoryHull

    with tempfile.TemporaryDirectory(prefix="beast-stage2-memory-") as tmp:
        hull = MemoryHull(Path(tmp) / "vault")
        cases = {
            "current": ("alpha", "r2"), "stale": ("alpha", "r1"),
            "other_repo": ("beta", "r2"), "tampered": ("alpha", "r2"),
        }
        rows = {name: hull.write_residue(task="compatibility memo", decision=f"fixture {name}",
                                        policy_tags=[f"repo:{repo}", f"revision:{rev}"])
                for name, (repo, rev) in cases.items()}
        Path(rows["tampered"]["markdown_path"]).write_text("changed after signing")
        eligible, excluded = scoped_recall(hull, "compatibility memo", "alpha", "r2")
        checks = {
            "current_accepted": eligible == [rows["current"]["residue_id"]],
            "stale_excluded": rows["stale"]["residue_id"] in excluded,
            "other_repo_excluded": rows["other_repo"]["residue_id"] in excluded,
            "tampered_not_returned": rows["tampered"]["residue_id"] not in {*eligible, *excluded},
        }
        return {"schema": "beast.stage2.memory_controls.v1", "passed": all(checks.values()), "checks": checks,
                "claim_boundary": "Offline isolated Memory Hull fixture, no model effect or production policy claim."}


if __name__ == "__main__":
    report = memory_controls()
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["passed"] else 1)
