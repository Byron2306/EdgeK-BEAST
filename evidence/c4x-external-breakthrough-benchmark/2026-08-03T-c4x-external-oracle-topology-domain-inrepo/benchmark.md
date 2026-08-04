# C4-X external breakthrough benchmark · 2026-08-03T-c4x-external-oracle-topology-domain-inrepo

- Receipt: `sha256:3bfef0ebbf40485fa88e6e33fdc0be3001603b9a58b395c847e3006b91da969e`
- Engine freeze digest: `sha256:fe6836990bd6f6513046bca25f35b9367294aa9819e37ffbdc6dbe7994e3fa82`
- Evaluator seed: `outsider-oracle-topology-domain-2026-08-03`
- Held-out cases: `12`
- Cross-modal families: `3`
- Independent semantic oracle: `True`
- Randomized topology shapes: `4`
- Held-out operational domains: `6`
- Randomized service names: `23`
- BEAST semantic correct: `12/12`
- BEAST artifact custody valid: `12/12`
- BEAST provider calls used: `0`
- Baselines compared: `9`
- Baseline scope: `local_reference_adapters_plus_existing_in_repo_beast_subsystems_not_third_party_competitors`
- Third-party verifier ready: `True`
- BEAST beats all baselines: `True`
- Breakthrough protocol pass: `True`

## Randomization coverage

- Topology shapes: `{"fan_in_with_anchor": 6, "fan_out_with_anchor": 3, "mesh_noise_with_anchor": 1, "transitive_with_direct_anchor": 2}`
- Operational domains: `{"emergency_dispatch": 1, "farm_sensor_grid": 1, "library_search": 2, "microgrid_control": 3, "robotics_cell": 3, "water_station": 2}`

## System scores

- `beast_c4x`: total=190, semantic=12/12, custody=12/12, providers=0
- `rag_nearest_exemplar`: total=39, semantic=0/12, custody=0/12, providers=0
- `cached_named_template`: total=36, semantic=0/12, custody=0/12, providers=0
- `rule_engine_text_only`: total=48, semantic=3/12, custody=0/12, providers=0
- `knowledge_graph_topology_only`: total=39, semantic=0/12, custody=0/12, providers=0
- `model_generated_multimodal_stub`: total=27, semantic=3/12, custody=0/12, providers=24
- `beast_local_semantic_cache`: total=27, semantic=0/12, custody=0/12, providers=0
- `beast_capability_composition_rule_engine`: total=84, semantic=12/12, custody=0/12, providers=0
- `beast_topology_graph_adapter`: total=35, semantic=0/12, custody=0/12, providers=0
- `beast_generation_provider_boundary`: total=15, semantic=0/12, custody=0/12, providers=24

## Boundary

Reference external-breakthrough benchmark scaffold. Held-out cases are generated after engine freeze from an evaluator seed. Semantic scoring uses an independent oracle derived only from scenario facts, policies, rules, topology metadata, and temporal flags before BEAST execution. Baseline adapters are transparent local references and should be replaced by independent public implementations for third-party claims.
