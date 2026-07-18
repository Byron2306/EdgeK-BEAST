from app.kernel.execution.rollback_orchestrator import RollbackOrchestrator

def test_failed_verification_rolls_back():
    calls=[]
    receipt=RollbackOrchestrator().run("op",snapshot=lambda _:"snap:1",apply=lambda _:{"changed":True},verify=lambda _p,_e:{"healthy":False},rollback=lambda *_:calls.append(True))
    assert receipt.status=="rolled_back" and calls==[True]

def test_verified_operation_does_not_rollback():
    calls=[]
    receipt=RollbackOrchestrator().run("op",snapshot=lambda _:"snap:1",apply=lambda _:{"changed":True},verify=lambda _p,_e:{"healthy":True},rollback=lambda *_:calls.append(True))
    assert receipt.status=="verified" and calls==[]

def test_apply_exception_is_rolled_back_and_recorded():
    calls=[]
    def fail(_): raise RuntimeError("boom")
    receipt=RollbackOrchestrator().run("op",snapshot=lambda _:"snap:1",apply=fail,verify=lambda *_:{},rollback=lambda *_:calls.append(True))
    assert receipt.status=="rolled_back" and receipt.error=="boom" and calls==[True]
