from app.kernel.compute.crystal_frontier_crucible import *
def task(tier="C1",eligible=True): return SealedTask("t1","repair",tier,"sha256:repo","sha256:spec","sha256:verify",eligible)
def run(lane,ok,eligible=True): return CrucibleRun("t1",lane,lane,ok,"sha256:patch",ApplicabilityDecision(eligible,.9),0,0,0,1,{"tests":True,"security":True},"sha256:image","model","sha256:tools","policy")
def test_manifest_blinding_and_public_projection():
 h=CrucibleHypotheses(); m=SealedTaskFoundry(h).manifest([task()],branch_digest="b",lattice_digest="l",policy_digest="p")
 packet,key=BlindReviewChamber().packet([run("frontier_native",True),run("crystal_only",True)],seed=3)
 assert m["manifest_digest"].startswith("sha256:") and all("lane" not in x for x in packet) and set(key.values())=={"frontier_native","crystal_only"}
def test_statistics_requires_both_confidence_levels_and_abstention():
 h=CrucibleHypotheses(noninferiority_margin=.05,safe_false_execution_max=.1); e=StatisticalEvidenceEngine(seed=2)
 stats=e.evaluate([task("C1",True),SealedTask("t2","novel","C5","r","s","v",False)], [run("frontier_native",True),run("crystal_only",True),run("frontier_native",True),CrucibleRun("t2","crystal_only","x",False,"p",ApplicabilityDecision(False,.1),0,0,0,1,{"tests":True},"i","m","t","p")],h)
 assert stats["h1_quality_parity"] is True and stats["h3_safe_abstention"] is True
def test_lane_controller_abstains_or_falls_back_without_verified_crystal(tmp_path):
    c=AgentLaneController(); d=ApplicabilityDecision(False,.8,disqualifiers=("state drift",))
    assert c.direct("crystal_only",d,crystal_verified=False).action=="abstain"
    assert c.direct("crystal_hybrid",d,crystal_verified=False).action=="fallback"
    v=HiddenVerifierVault(); digest=v.commit(tmp_path,"t1",b"secret verifier")
    assert v.verify(tmp_path,"t1",digest) is True
def test_sensorium_recorder_rejects_incomplete_crystal_evidence(tmp_path):
 r=run("crystal_only",True)
 try: SensoriumRunRecorder().record(tmp_path,r)
 except ValueError: pass
 else: raise AssertionError("crystal run without attestation/IR must fail")
 complete=CrucibleRun("t1","crystal_only","complete",True,"patch",ApplicabilityDecision(True,.9),0,0,0,1,{"tests":True},"image","model","tools","policy","ir","lattice","attestation","sensorium",True)
 assert SensoriumRunRecorder().record(tmp_path,complete).startswith("sha256:")
def test_dataset_gate_refuses_partial_six_lane_experiment():
 t=task(); gate=CrucibleDatasetGate()
 assert gate.validate([t],[run("frontier_native",True)])["valid"] is False
def test_power_gate_and_ablation_registry_are_preregisterable():
 assert StatisticalEvidenceEngine.required_binary_pairs(frontier_rate=.6,noninferiority_margin=.05)>=1000
 assert {item['id'] for item in preregistered_ablations()} >= {'crystals_disabled','poisoned_crystal','stale_crystal'}
def test_longitudinal_gate_requires_coverage_without_degradation():
 e=LongitudinalEvidenceEngine()
 r=e.evaluate([{'coverage':.2,'quality':.8,'safety':.99,'calibration_error':.1},{'coverage':.4,'quality':.79,'safety':.988,'calibration_error':.11}])
 assert r['h4_durable_accumulation'] is True
