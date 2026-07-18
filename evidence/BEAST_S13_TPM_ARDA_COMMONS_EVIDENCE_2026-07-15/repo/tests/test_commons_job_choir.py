from app.kernel.commons.job_choir import CommonsJobChoir, NodeAdvertisement


def test_commons_job_vertical_slice():
    choir = CommonsJobChoir(); artifact = choir.publish("model", {"revision": "v1", "chunks": ["x"]}, "sig")
    node = NodeAdvertisement("node-1", "verified", ("cpu",), 0.8, 0.9)
    assert choir.score(node, required="cpu") > 0
    receipt = choir.witness("job-1", node, artifact, b"output")
    assert receipt.verified and receipt.output_digest.startswith("sha256:")

