from app.kernel.evidence.release_chain import ReleaseChain


def test_release_chain_links_all_stages_and_detects_digest_drift():
    chain = ReleaseChain()
    commit = chain.record("commit", {"source_digest": "sha256:src"})
    build = chain.record("build", {"artifact_digest": "sha256:ok"}, parent=commit)
    verify = chain.record("verification", {"artifact_digest": "sha256:ok"}, parent=build)
    chain.record("deployment", {"approved_digest": "sha256:ok", "deployed_digest": "sha256:bad", "two_person_approval": True}, parent=verify)
    assert len(chain.audit("approved_digest_mismatch")) == 1


def test_release_chain_audits_privileged_changes():
    chain = ReleaseChain()
    chain.record("commit", {"privileged": True, "source_digest": "sha256:x"})
    assert len(chain.audit("privileged_changes")) == 1

