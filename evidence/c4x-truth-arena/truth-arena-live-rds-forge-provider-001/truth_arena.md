# C4-X Truth Arena · truth-arena-live-rds-forge-provider-001

- Receipt: `sha256:aa02ac8682a769c2002c5d1aa48f84d1a7a91a98f959a47243a149f6540e9e41`
- Source C4-X receipt: `sha256:d8f3bb491e770ed114f4d1d47a844b8310a221585b642ce8d01c070e411391e5`
- Truth winner: `beast_c4x` (189 points)
- Held-out cases: `12`
- Topology shapes: `4`
- Operational domains: `6`
- External RAG enabled: `True`
- BEAST custody gate pass: `True`
- Compute mixed into truth: `False`
- KV runtime measurements supplied: `True`

## Truth scoreboard

- `beast_c4x`: 189/192 semantic=12/12 proof=12/12 custody=12/12 visual_custody=11/12 providers=0
- `beast_capability_composition_rule_engine`: 96/192 semantic=12/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `external_rag_retrieval`: 91/192 semantic=11/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `rule_engine_text_only`: 61/192 semantic=5/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `cached_named_template`: 36/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `beast_topology_graph_adapter`: 32/192 semantic=1/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `model_generated_multimodal_stub`: 26/192 semantic=1/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=24
- `beast_generation_provider_boundary`: 21/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=24
- `beast_local_semantic_cache`: 21/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `knowledge_graph_topology_only`: 21/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `rag_nearest_exemplar`: 21/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0

## Custody hard gates

- `beast_c4x`: pass=True failures=none
- `beast_capability_composition_rule_engine`: pass=False failures=semantic_without_proof_first, semantic_without_artifact_custody
- `beast_generation_provider_boundary`: pass=False failures=none
- `beast_local_semantic_cache`: pass=False failures=none
- `beast_topology_graph_adapter`: pass=False failures=semantic_without_proof_first, semantic_without_artifact_custody
- `cached_named_template`: pass=False failures=none
- `external_rag_retrieval`: pass=False failures=semantic_without_proof_first, semantic_without_artifact_custody
- `knowledge_graph_topology_only`: pass=False failures=none
- `model_generated_multimodal_stub`: pass=False failures=semantic_without_proof_first, semantic_without_artifact_custody
- `rag_nearest_exemplar`: pass=False failures=none
- `rule_engine_text_only`: pass=False failures=semantic_without_proof_first, semantic_without_artifact_custody

## Boundary

Three-front arena over the C4-X independent-oracle benchmark. Truth points are separate from raw compute measurements and hard custody/security gates. KV runtime credit is withheld unless runtime-native measurements are supplied; synthetic bytes are not accepted as public KV proof.
