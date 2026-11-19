"""Evidence that the real Effect TS runtime drives Python BEAST operations.

These tests exercise the FFI boundary end to end: Python builds effect
programs, the Node process executes them with `effect`, and leaf operations
call back into Python.
"""

from __future__ import annotations

import time

import pytest

from app.kernel.agents import effect_ts_bridge as E


@pytest.fixture(scope="module")
def bridge():
    b = E.EffectTSBridge()
    with b:
        yield b
    b.close()


def test_succeed(bridge):
    assert bridge.run(E.succeed({"a": 1})) == {"a": 1}


def test_concurrent_zip_runs_ops_in_parallel(bridge):
    def slow(args):
        time.sleep(args.get("sleep", 0.2))
        return args["label"]

    bridge.register_op("test.slow", slow)
    started = time.monotonic()
    result = bridge.run(E.zip_(E.call("test.slow", {"label": "a"}), E.call("test.slow", {"label": "b"})))
    elapsed = time.monotonic() - started

    assert result == ["a", "b"]
    assert elapsed < 0.35, f"zip was not concurrent ({elapsed:.2f}s)"


def test_retry_until_python_op_succeeds(bridge):
    attempts = {"n": 0}

    def flaky(args):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    bridge.register_op("test.flaky", flaky)
    assert bridge.run(E.retry(E.call("test.flaky"), count=5)) == "ok"
    assert attempts["n"] == 3


def test_retry_exhausted_reports_failure(bridge):
    def always_fails(args):
        raise RuntimeError("always down")

    bridge.register_op("test.down", always_fails)
    with pytest.raises(E.EffectError) as err:
        bridge.run(E.retry(E.call("test.down"), count=2))
    assert "always down" in str(err.value)


def test_timeout_interrupts_slow_python_op(bridge):
    def very_slow(args):
        time.sleep(args.get("sleep", 2.0))
        return "late"

    bridge.register_op("test.very_slow", very_slow)
    started = time.monotonic()
    with pytest.raises(E.EffectError) as err:
        bridge.run(E.timeout(E.call("test.very_slow", {"sleep": 2.0}), ms=150))
    elapsed = time.monotonic() - started

    assert err.value.tag == "TimeoutError"
    assert elapsed < 1.0, f"timeout did not interrupt ({elapsed:.2f}s)"


def test_resource_releases_even_when_use_fails(bridge):
    events = []
    bridge.register_op("test.acquire", lambda a: events.append("acquire"))
    bridge.register_op("test.release", lambda a: events.append("release"))

    def boom(args):
        raise RuntimeError("use failed")

    bridge.register_op("test.boom", boom)
    with pytest.raises(E.EffectError):
        bridge.run(
            E.resource(
                E.call("test.acquire"),
                E.call("test.release"),
                E.call("test.boom"),
            )
        )
    assert events == ["acquire", "release"]


def test_fork_and_join(bridge):
    fiber = bridge.run(E.fork(E.as_(E.sleep(80), "child-value")))
    assert fiber["fiberId"].startswith("fiber_")
    assert bridge.run(E.join(fiber["fiberId"])) == "child-value"


def test_race_returns_fastest_branch(bridge):
    bridge.register_op("test.slowish", lambda a: time.sleep(1.0) or "slow")
    result = bridge.run(E.race(E.call("test.slowish"), E.as_(E.sleep(20), "fast")))
    assert result == "fast"


def test_python_op_errors_surface_as_effect_failures(bridge):
    def rejects(args):
        raise ValueError("nope")

    bridge.register_op("test.rejects", rejects)
    with pytest.raises(E.EffectError) as err:
        bridge.run(E.call("test.rejects"))
    assert "nope" in str(err.value)


def test_unregistered_op_is_reported(bridge):
    with pytest.raises(E.EffectError) as err:
        bridge.run(E.call("test.missing"))
    assert "unregistered effect op" in str(err.value)
