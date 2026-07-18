from app.kernel.compute.interference_buckets import classify

def test_pressure_and_trust_select_interference_bucket():
    assert classify(cpu_pressure=.9,memory_pressure=0,io_pressure=0).bucket == "constrained"
    assert classify(cpu_pressure=.9,memory_pressure=.9,io_pressure=.9,trust="operator").bucket == "protected"
    assert classify(cpu_pressure=0,memory_pressure=0,io_pressure=0,trust="quarantine").bucket == "quarantine"
