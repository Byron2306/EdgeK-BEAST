# C4-X external breakthrough benchmark · truth-arena-live-rds-forge-provider-002-c4x

- Receipt: `sha256:56b80ff2e0760f24d66519ad0a7c5f5094b3a20dc294cfc1855c9baf103f798f`
- Engine freeze digest: `sha256:fe6836990bd6f6513046bca25f35b9367294aa9819e37ffbdc6dbe7994e3fa82`
- Evaluator seed: `truth-arena-live-rds-forge-provider-001`
- Held-out cases: `12`
- Cross-modal families: `3`
- Independent semantic oracle: `True`
- Randomized topology shapes: `4`
- Held-out operational domains: `6`
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

- Topology shapes: `{"direct": 3, "fan_out_with_anchor": 2, "mesh_noise_with_anchor": 3, "transitive_with_direct_anchor": 4}`
- Operational domains: `{"clinic_scheduler": 3, "emergency_dispatch": 2, "farm_sensor_grid": 1, "library_search": 2, "robotics_cell": 2, "water_station": 2}`

## System scores

- `beast_c4x`: total=191, semantic=12/12, custody=12/12, providers=0
- `rag_nearest_exemplar`: total=33, semantic=0/12, custody=0/12, providers=0
- `cached_named_template`: total=36, semantic=0/12, custody=0/12, providers=0
- `rule_engine_text_only`: total=56, semantic=5/12, custody=0/12, providers=0
- `knowledge_graph_topology_only`: total=33, semantic=0/12, custody=0/12, providers=0
- `model_generated_multimodal_stub`: total=13, semantic=1/12, custody=0/12, providers=24
- `beast_local_semantic_cache`: total=21, semantic=0/12, custody=0/12, providers=0
- `beast_capability_composition_rule_engine`: total=84, semantic=12/12, custody=0/12, providers=0
- `beast_topology_graph_adapter`: total=39, semantic=1/12, custody=0/12, providers=0
- `beast_generation_provider_boundary`: total=9, semantic=0/12, custody=0/12, providers=24
- `external_rag_retrieval`: total=84, semantic=12/12, custody=0/12, providers=0

## Boundary

Reference external-breakthrough benchmark scaffold. Held-out cases are generated after engine freeze from an evaluator seed. Semantic scoring uses an independent oracle derived only from scenario facts, policies, rules, topology metadata, and temporal flags before BEAST execution. Baseline adapters are transparent local references and should be replaced by independent public implementations for third-party claims.
