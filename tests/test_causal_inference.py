from app.kernel.compute.causal_inference import infer_edges

def test_causal_edges_require_explicit_resource_evidence():
    edges=infer_edges([{"id":"read","writes":"artifact"},{"id":"verify","reads":"artifact"}])
    assert any(edge.source=="read" and edge.target=="verify" and edge.reason=="reads" for edge in edges)
