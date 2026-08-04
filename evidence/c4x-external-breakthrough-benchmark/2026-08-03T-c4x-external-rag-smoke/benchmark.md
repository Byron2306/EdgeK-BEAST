# C4-X external breakthrough benchmark · 2026-08-03T-c4x-external-rag-smoke

- Receipt: `sha256:aff38840472c54871f791df4b155dfac59ba52f7a79aa6ee5f7297094cae3001`
- Engine freeze digest: `sha256:fe6836990bd6f6513046bca25f35b9367294aa9819e37ffbdc6dbe7994e3fa82`
- Evaluator seed: `outsider-external-rag-smoke-2026-08-03`
- Held-out cases: `12`
- Cross-modal families: `3`
- Independent semantic oracle: `True`
- Randomized topology shapes: `5`
- Held-out operational domains: `6`
- Randomized service names: `24`
- BEAST semantic correct: `12/12`
- BEAST artifact custody valid: `12/12`
- BEAST provider calls used: `0`
- Baselines compared: `10`
- Baseline scope: `local_reference_adapters_plus_existing_in_repo_beast_subsystems_plus_external_rag_command_not_third_party_public_execution`
- Third-party verifier ready: `True`
- BEAST beats all baselines: `True`
- Breakthrough protocol pass: `True`

## Randomization coverage

- Topology shapes: `{"direct": 1, "fan_in_with_anchor": 2, "fan_out_with_anchor": 1, "mesh_noise_with_anchor": 5, "transitive_with_direct_anchor": 3}`
- Operational domains: `{"campus_lms": 1, "clinic_scheduler": 2, "farm_sensor_grid": 3, "microgrid_control": 3, "robotics_cell": 2, "water_station": 1}`

## System scores

- `beast_c4x`: total=192, semantic=12/12, custody=12/12, providers=0
- `rag_nearest_exemplar`: total=36, semantic=0/12, custody=0/12, providers=0
- `cached_named_template`: total=36, semantic=0/12, custody=0/12, providers=0
- `rule_engine_text_only`: total=52, semantic=4/12, custody=0/12, providers=0
- `knowledge_graph_topology_only`: total=36, semantic=0/12, custody=0/12, providers=0
- `model_generated_multimodal_stub`: total=24, semantic=3/12, custody=0/12, providers=24
- `beast_local_semantic_cache`: total=24, semantic=0/12, custody=0/12, providers=0
- `beast_capability_composition_rule_engine`: total=80, semantic=11/12, custody=0/12, providers=0
- `beast_topology_graph_adapter`: total=45, semantic=1/12, custody=0/12, providers=0
- `beast_generation_provider_boundary`: total=12, semantic=0/12, custody=0/12, providers=24
- `external_rag_retrieval`: total=24, semantic=0/12, custody=0/12, providers=0

## Boundary

Reference external-breakthrough benchmark scaffold. Held-out cases are generated after engine freeze from an evaluator seed. Semantic scoring uses an independent oracle derived only from scenario facts, policies, rules, topology metadata, and temporal flags before BEAST execution. Baseline adapters are transparent local references and should be replaced by independent public implementations for third-party claims.
