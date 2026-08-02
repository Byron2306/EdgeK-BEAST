from app.kernel.agents.phase_e_learning import Archivist, Scribe


def test_scribe_classifies_verified_episode_without_promotion():
    episode = Scribe().compile_episode(
        task_class="code_change",
        events=[{"role": "hermes", "decision": "route"}] * 4,
        verification={"status": "passed"},
        critic={"status": "passed"},
    )

    assert "execution_candidate" in episode["classifications"]
    assert "skill_candidate" in episode["classifications"]
    assert episode["promotion_candidate"] is True
    assert episode["promotion_authorized"] is False


def test_archivist_emits_hashed_causal_packet():
    episode = Scribe().compile_episode(
        task_class="test_repair",
        events=[{"role": "verifier", "decision": "failed"}],
        verification={"status": "failed"},
    )
    archived = Archivist().archive(episode, verification={"status": "failed"})

    assert archived["packet"]["beast_object_type"] == "unified_crystallized_compute_evidence_packet"
    assert archived["packet"]["packet_hash"].startswith("sha256:")
    assert archived["packet"]["negative_cases"]
    assert archived["promotion_authorized"] is False
