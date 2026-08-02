from app.kernel.agents.tiny_model_conductor import TinyModelConductor, TinyModelState


def test_tiny_model_conductor_exposes_one_deterministic_sequence():
    conductor = TinyModelConductor()
    observed = []
    for _ in TinyModelConductor.STEPS:
        observed.append(conductor.complete_current()["state"])

    assert tuple(observed) == TinyModelConductor.expected_states()
    assert conductor.next().state is TinyModelState.COMPLETED
    assert conductor.next().allowed_next_tools == ()
