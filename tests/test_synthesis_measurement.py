from app.kernel.compute.synthesis_measurement import (
    MeasurementObservation,
    MeasurementRoute,
    run_synthesis_measurement_protocol,
)


def _obs(route, index=0, **overrides):
    values = {
        "route": route,
        "case_id": f"{route.value}:{index}",
        "resolved": True,
        "correct": True,
        "false_reuse": False,
        "unsupported_assumptions": 0,
        "stale_reuse_rejected": index % 2 == 0,
        "latency_ms": 10.0 + index,
        "cpu_ms": 2.0,
        "memory_bytes": 1024,
        "tokens": 8,
        "provider_calls": 1 if route in {MeasurementRoute.RAW_LOCAL_MODEL, MeasurementRoute.RAG_PLUS_MODEL} else 0,
    }
    values.update(overrides)
    return MeasurementObservation(**values)


def test_synthesis_measurement_protocol_covers_all_required_routes():
    observations = tuple(
        _obs(route, index)
        for route in MeasurementRoute
        for index in range(3)
    )

    report = run_synthesis_measurement_protocol(observations, minimum_cases_per_route=3)

    assert report.passed is True
    assert not report.notes
    assert {item.route for item in report.route_measurements} == set(MeasurementRoute)
    meaning = next(item for item in report.route_measurements if item.route is MeasurementRoute.MEANING_CRYSTALS)
    assert meaning.provider_calls == 0
    assert meaning.cache_invalidation_correctness == 1.0


def test_synthesis_measurement_protocol_flags_false_reuse_and_unsupported_assumptions():
    observations = tuple(
        _obs(route, 0, false_reuse=route is MeasurementRoute.BEAST_CACHE, unsupported_assumptions=1 if route is MeasurementRoute.RAW_LOCAL_MODEL else 0)
        for route in MeasurementRoute
    )

    report = run_synthesis_measurement_protocol(observations)

    assert report.passed is False
    assert "false reuse observed" in report.notes
    assert "unsupported assumptions observed" in report.notes
