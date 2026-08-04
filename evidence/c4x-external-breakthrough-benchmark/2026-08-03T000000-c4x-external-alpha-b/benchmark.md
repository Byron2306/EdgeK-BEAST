# C4-X external breakthrough benchmark · 2026-08-03T000000-c4x-external-alpha-b

- Receipt: `sha256:ec2b2dbc5c4591947988052fe7843f3b549f3b29a1a9aaa0b32446996fcfdebb`
- Engine freeze digest: `sha256:fe6836990bd6f6513046bca25f35b9367294aa9819e37ffbdc6dbe7994e3fa82`
- Evaluator seed: `outsider-panel-2026-08-03-alpha`
- Held-out cases: `12`
- Cross-modal families: `3`
- Randomized service names: `24`
- BEAST semantic correct: `12/12`
- BEAST artifact custody valid: `12/12`
- BEAST provider calls used: `0`
- Baselines compared: `5`
- BEAST beats all reference baselines: `True`
- Breakthrough protocol pass: `True`

## System scores

- `beast_c4x`: total=190, semantic=12/12, custody=12/12, providers=0
- `rag_nearest_exemplar`: total=39, semantic=0/12, custody=0/12, providers=0
- `cached_named_template`: total=36, semantic=0/12, custody=0/12, providers=0
- `rule_engine_text_only`: total=48, semantic=3/12, custody=0/12, providers=0
- `knowledge_graph_topology_only`: total=39, semantic=0/12, custody=0/12, providers=0
- `model_generated_multimodal_stub`: total=27, semantic=3/12, custody=0/12, providers=24

## Boundary

Reference external-breakthrough benchmark scaffold. Held-out cases are generated after engine freeze from an evaluator seed. Baseline adapters are transparent local references and should be replaced by independent public implementations for third-party claims.
