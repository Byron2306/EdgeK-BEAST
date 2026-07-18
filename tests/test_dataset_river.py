from app.kernel.commons.dataset_river import DatasetRiver


def test_dataset_river_shards_deterministically():
    records, lineage = DatasetRiver().stream([{"i": i} for i in range(6)], dataset_digest="sha256:"+"a"*64, shard_index=1, shard_count=2, privacy_label="restricted")
    assert [row["i"] for row in records] == [1,3,5]
    assert lineage.record_count == 3 and lineage.privacy_label == "restricted"


def test_dataset_river_lazy_cursor_verifies_without_materializing_source():
    river=DatasetRiver(); rows=[{"id":1},{"id":2},{"id":3}]; seen=[]
    def source():
        for row in rows: seen.append(row["id"]); yield row
    cursor=river.stream_lazy(source(),dataset_digest=river.digest(rows),shard_index=1,shard_count=2)
    assert seen==[]
    assert list(cursor)==[{"id":2}]
    assert cursor.receipt().record_count==1 and seen==[1,2,3]
