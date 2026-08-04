# C4-X external breakthrough benchmark · pgvector-rag-real-run-001

- Receipt: `sha256:70a5d06444d331ce47249dcb16d9ecae2389d8796bbf34c406b2fc4658af9e8b`
- Engine freeze digest: `sha256:fe6836990bd6f6513046bca25f35b9367294aa9819e37ffbdc6dbe7994e3fa82`
- Evaluator seed: `pgvector-rag-real-run-001`
- Held-out cases: `12`
- Cross-modal families: `3`
- Independent semantic oracle: `True`
- Randomized topology shapes: `5`
- Held-out operational domains: `8`
- Randomized service names: `23`
- BEAST semantic correct: `12/12`
- BEAST artifact custody valid: `12/12`
- BEAST provider calls used: `0`
- Baselines compared: `10`
- Baseline scope: `local_reference_adapters_plus_existing_in_repo_beast_subsystems_plus_external_rag_command_not_third_party_public_execution`
- Third-party verifier ready: `True`
- BEAST beats all baselines: `True`
- Breakthrough protocol pass: `True`

## Randomization coverage

- Topology shapes: `{"direct": 4, "fan_in_with_anchor": 3, "fan_out_with_anchor": 3, "mesh_noise_with_anchor": 1, "transitive_with_direct_anchor": 1}`
- Operational domains: `{"campus_lms": 1, "clinic_scheduler": 1, "emergency_dispatch": 1, "farm_sensor_grid": 1, "library_search": 2, "microgrid_control": 2, "robotics_cell": 1, "water_station": 3}`

## System scores

- `beast_c4x`: total=192, semantic=12/12, custody=12/12, providers=0
- `rag_nearest_exemplar`: total=27, semantic=0/12, custody=0/12, providers=0
- `cached_named_template`: total=36, semantic=0/12, custody=0/12, providers=0
- `rule_engine_text_only`: total=64, semantic=7/12, custody=0/12, providers=0
- `knowledge_graph_topology_only`: total=27, semantic=0/12, custody=0/12, providers=0
- `model_generated_multimodal_stub`: total=3, semantic=0/12, custody=0/12, providers=24
- `beast_local_semantic_cache`: total=15, semantic=0/12, custody=0/12, providers=0
- `beast_capability_composition_rule_engine`: total=80, semantic=11/12, custody=0/12, providers=0
- `beast_topology_graph_adapter`: total=40, semantic=2/12, custody=0/12, providers=0
- `beast_generation_provider_boundary`: total=3, semantic=0/12, custody=0/12, providers=24
- `external_rag_retrieval`: total=36, semantic=0/12, custody=0/12, providers=0

## Boundary

Reference external-breakthrough benchmark scaffold. Held-out cases are generated after engine freeze from an evaluator seed. Semantic scoring uses an independent oracle derived only from scenario facts, policies, rules, topology metadata, and temporal flags before BEAST execution. Baseline adapters are transparent local references and should be replaced by independent public implementations for third-party claims.
