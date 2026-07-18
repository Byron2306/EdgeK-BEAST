from app.kernel.commons.dataset_river import DatasetRiver
from app.kernel.commons.job_choir import CommonsJobChoir, NodeAdvertisement


def test_job_witness_binds_dataset_lineage():
    _, lineage = DatasetRiver().stream([{"x": 1}], dataset_digest="sha256:"+"a"*64)
    choir=CommonsJobChoir(); artifact=choir.publish("model", {"v": 1}, "sig")
    receipt=choir.witness("job", NodeAdvertisement("n", "verified", ("cpu",), 1, 1), artifact, b"out", lineage=lineage)
    assert receipt.dataset_digest == lineage.dataset_digest
    assert receipt.dataset_shard == "0/1"

