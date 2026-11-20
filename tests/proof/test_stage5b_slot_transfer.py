from contextlib import contextmanager

import pytest

from scripts.proof.run_stage5b_slot_transfer import run_trial


class FakeWorker:
    def __init__(self, pid, directory, role, no_op=False, changed_output=False):
        self.pid, self.directory, self.role = pid, directory, role
        self.no_op, self.changed_output = no_op, changed_output
        self.restored = False
        self.calls = 0

    def completion(self, prompt):
        self.calls += 1
        reused = (self.restored and not self.no_op) or (self.role == "donor" and self.calls > 1)
        return {"cache_n": 642 if reused else 0, "prompt_n": 7 if reused else 649,
                "prompt_ms": 31.0 if reused else 1400.0,
                "content_sha256": "x" if not self.changed_output else "different",
                "tokens_sha256": "y", "output_tokens": 8}

    def slot(self, action):
        path = self.directory / "stage5b-slot.bin"
        if action == "save":
            path.write_bytes(b"mock-slot")
            return {"n_saved": 645, "n_written": 9}
        assert self.calls == 0
        assert path.read_bytes() == b"mock-slot"
        self.restored = True
        return {"n_restored": 645, "n_read": 9}


def workers(no_op=False, changed_output=False):
    seen = []

    @contextmanager
    def start(role, directory, log):
        directory.mkdir(exist_ok=True)
        worker = FakeWorker(100 + len(seen), directory, role, no_op,
                            changed_output and role == "restored")
        seen.append(worker)
        yield worker

    return start, seen


@pytest.mark.parametrize("no_op,changed_output,verified", [
    (False, False, True), (True, False, False), (False, True, False),
])
def test_stage5b_distinguishes_acknowledgement_from_consumption(tmp_path, no_op, changed_output, verified):
    backend, seen = workers(no_op, changed_output)
    result = run_trial(tmp_path, 1, backend)
    assert result["transfer"]["sha256_match"] is True
    assert result["restore"]["n_restored"] == 645
    assert result["checks"]["destination_consumed_cache"] is not no_op
    assert result["checks"]["output_equivalent"] is not changed_output
    assert result["validated"] is verified
    assert len({w.pid for w in seen}) == 3
    assert all(w.calls == 1 for w in seen if w.role != "donor")


def test_corrupt_copy_is_rejected_before_any_receiver_runs(tmp_path, monkeypatch):
    from scripts.proof import run_stage5b_slot_transfer as runner

    backend, seen = workers()
    monkeypatch.setattr(runner.shutil, "copyfile", lambda _src, dst: dst.write_bytes(b"bad-bytes"))
    with pytest.raises(ValueError, match="size or digest"):
        run_trial(tmp_path, 1, backend)
    assert [w.role for w in seen] == ["donor"]


def test_pinned_slot_and_completion_http_contract():
    import json
    import httpx
    from scripts.proof.run_stage5b_slot_transfer import FILENAME, Worker

    def response(request):
        if request.url.path == "/slots/0":
            assert request.url.params["action"] == "restore"
            assert json.loads(request.content) == {"filename": FILENAME}
            return httpx.Response(200, json={"id_slot": 0, "filename": FILENAME, "n_restored": 645, "n_read": 9})
        body = json.loads(request.content)
        assert request.url.path == "/completion"
        assert body["id_slot"] == 0 and body["return_tokens"] and body["cache_prompt"]
        return httpx.Response(200, json={"content": "hello", "tokens": [1, 2],
                                        "timings": {"cache_n": 642, "prompt_n": 7, "prompt_ms": 35}})

    with httpx.Client(transport=httpx.MockTransport(response), trust_env=False) as client:
        worker = Worker(17, 11446, client)
        assert worker.slot("restore")["n_restored"] == 645
        record = worker.completion("input")
        assert record["cache_n"] == 642 and record["output_tokens"] == 2
