# C4-X external breakthrough benchmark · pgvector-rag-real-run-003

- Receipt: `sha256:2638d817cdf559720db2ffa37cd14a94542ad9dc382927f5eeb2292b4a302ef1`
- Engine freeze digest: `sha256:fe6836990bd6f6513046bca25f35b9367294aa9819e37ffbdc6dbe7994e3fa82`
- Evaluator seed: `pgvector-rag-real-run-003`
- Held-out cases: `12`
- Cross-modal families: `3`
- Independent semantic oracle: `True`
- Randomized topology shapes: `4`
- Held-out operational domains: `7`
- Randomized service names: `22`
- BEAST semantic correct: `12/12`
- BEAST artifact custody valid: `12/12`
- BEAST provider calls used: `0`
- Baselines compared: `10`
- Baseline scope: `local_reference_adapters_plus_existing_in_repo_beast_subsystems_plus_external_rag_command_not_third_party_public_execution`
- Third-party verifier ready: `True`
- BEAST beats all baselines: `True`
- Breakthrough protocol pass: `True`

## Randomization coverage

- Topology shapes: `{"fan_in_with_anchor": 4, "fan_out_with_anchor": 1, "mesh_noise_with_anchor": 4, "transitive_with_direct_anchor": 3}`
- Operational domains: `{"campus_lms": 1, "clinic_scheduler": 2, "emergency_dispatch": 2, "farm_sensor_grid": 3, "library_search": 2, "microgrid_control": 1, "robotics_cell": 1}`

## System scores

- `beast_c4x`: total=191, semantic=12/12, custody=12/12, providers=0
- `rag_nearest_exemplar`: total=36, semantic=0/12, custody=0/12, providers=0
- `cached_named_template`: total=36, semantic=0/12, custody=0/12, providers=0
- `rule_engine_text_only`: total=52, semantic=4/12, custody=0/12, providers=0
- `knowledge_graph_topology_only`: total=36, semantic=0/12, custody=0/12, providers=0
- `model_generated_multimodal_stub`: total=16, semantic=1/12, custody=0/12, providers=24
- `beast_local_semantic_cache`: total=24, semantic=0/12, custody=0/12, providers=0
- `beast_capability_composition_rule_engine`: total=76, semantic=10/12, custody=0/12, providers=0
- `beast_topology_graph_adapter`: total=46, semantic=2/12, custody=0/12, providers=0
- `beast_generation_provider_boundary`: total=12, semantic=0/12, custody=0/12, providers=24
- `external_rag_retrieval`: total=84, semantic=12/12, custody=0/12, providers=0

## Boundary

Reference external-breakthrough benchmark scaffold. Held-out cases are generated after engine freeze from an evaluator seed. Semantic scoring uses an independent oracle derived only from scenario facts, policies, rules, topology metadata, and temporal flags before BEAST execution. Baseline adapters are transparent local references and should be replaced by independent public implementations for third-party claims.
