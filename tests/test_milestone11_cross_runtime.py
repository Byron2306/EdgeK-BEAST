from app.kernel.compute.milestone11_cross_runtime import Milestone11CrossRuntimeExperiment, verify_cross_runtime_packet


class BadAdapter:
    def __init__(self, adapter_id, family):
        self.adapter_id, self.runtime_family, self.endpoint = adapter_id, family, "memory://" + family
    def generate(self, prompt, seed): return "incorrect", 5, 1


def test_cross_runtime_gate_requires_and_accepts_two_real_identity_families():
    experiment=Milestone11CrossRuntimeExperiment(seed=22)
    experiment.adapters=(BadAdapter("a","ollama"),BadAdapter("b","llama.cpp"))
    experiment._identities=lambda digest:[
        {"adapter_id":"a","runtime_family":"ollama","binary_digest":"sha256:"+"a"*64,"crystal_digest":digest,
         "runtime_version":"1","model_file_digest":"sha256:"+"c"*64,"quantization":"Q4","decoding":{"seed":22},
         "adapter_implementation_digest":"sha256:"+"d"*64,"endpoint_identity":"sha256:"+"e"*64},
        {"adapter_id":"b","runtime_family":"llama.cpp","binary_digest":"sha256:"+"b"*64,"crystal_digest":digest,
         "runtime_version":"2","model_file_digest":"sha256:"+"c"*64,"quantization":"Q4","decoding":{"seed":22},
         "adapter_implementation_digest":"sha256:"+"f"*64,"endpoint_identity":"sha256:"+"1"*64},
    ]
    packet=experiment.run(tasks=8)
    assert packet["gates"]["distinct_runtime_families"]==2
    assert packet["gates"]["milestone_11_runtime_independence_complete"] is True
    verify_cross_runtime_packet(packet)
