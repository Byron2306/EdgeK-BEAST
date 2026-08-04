# C4-X Truth Arena · truth-arena-live-rds-forge-provider-rag-001

- Receipt: `sha256:a1e80850606cc0154c7e5d093e4f91908f0deee827e8ea89fcc0fdfb25a3bd64`
- Source C4-X receipt: `sha256:12bf8237e00f656e8f3873843f516441c2aee870a22edc0b8c455cb40ae2301a`
- Truth winner: `beast_c4x` (186 points)
- Held-out cases: `12`
- Topology shapes: `4`
- Operational domains: `8`
- External RAG enabled: `True`
- BEAST custody gate pass: `True`
- Compute mixed into truth: `False`
- KV runtime measurements supplied: `True`
- RAG War lanes: `15`
- Best RAG semantic accuracy: `1.0`

## Truth scoreboard

- `beast_c4x`: 186/192 semantic=12/12 proof=12/12 custody=12/12 visual_custody=10/12 providers=0
- `beast_capability_composition_rule_engine`: 96/192 semantic=12/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `external_rag_retrieval`: 91/192 semantic=11/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `rule_engine_text_only`: 66/192 semantic=6/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `cached_named_template`: 36/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `model_generated_multimodal_stub`: 23/192 semantic=1/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=24
- `beast_topology_graph_adapter`: 21/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `beast_generation_provider_boundary`: 18/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=24
- `beast_local_semantic_cache`: 18/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `knowledge_graph_topology_only`: 18/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `rag_nearest_exemplar`: 18/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0

## Compute reuse / KV War

- Runtime-native KV measurements supplied: `True`
- Synthetic KV public credit: `False`
- Covered KV cases: `['exact_repeated_prefix']`
- Missing KV case count: `15`
- `kv_forge_ml_kem_transport`: class=hypothesis engine=sglang cold=Nonems warm=Nonems cached_tokens=0 passed=[] failed=['cache_transported_to_second_node']
- `kv_llamacpp_prompt_cache`: class=observed_engine_local_prefix_cache engine=llama.cpp cold=13616.182ms warm=226.166333ms cached_tokens=962 passed=['exact_repeated_prefix'] failed=[]
- `kv_llamacpp_restart_boundary`: class=observed_restart_boundary engine=llama.cpp cold=9479.907ms warm=192.818ms cached_tokens=642 passed=[] failed=['engine_process_restarted']

## RAG War

- Best semantic accuracy: `1.0`
- Aurora pgvector corpus-poor best: `0.0`
- Aurora pgvector seeded best: `1.0`
- Aurora pgvector seed gain: `1.0`
- Custody boundary: RAG semantic success does not imply proof-first execution or artifact custody
- `rag_pgvector_rag_real_run_002_external_rag_retrieval`: retriever=aurora_pgvector corpus=live_pgvector_corpus_poor semantic=0/12 accuracy=0.0 chunks=0 proof=0 custody=0
- `rag_pgvector_rag_real_run_005_external_rag_retrieval`: retriever=aurora_pgvector corpus=live_pgvector_seeded_operational_patterns semantic=12/12 accuracy=1.0 chunks=12 proof=0 custody=0
- `rag_2026_08_03t_c4x_external_oracle_topology_domain_inrepo_cached_named_template`: retriever=cached_template_reference corpus=reference_or_local semantic=0/12 accuracy=0.0 chunks=0 proof=0 custody=0
- `rag_2026_08_03t_c4x_external_rag_smoke_cached_named_template`: retriever=cached_template_reference corpus=reference_or_local semantic=0/12 accuracy=0.0 chunks=0 proof=0 custody=0
- `rag_pgvector_rag_real_run_002_cached_named_template`: retriever=cached_template_reference corpus=reference_or_local semantic=0/12 accuracy=0.0 chunks=0 proof=0 custody=0
- `rag_pgvector_rag_real_run_005_cached_named_template`: retriever=cached_template_reference corpus=reference_or_local semantic=0/12 accuracy=0.0 chunks=0 proof=0 custody=0
- `rag_2026_08_03t_c4x_external_rag_smoke_external_rag_retrieval`: retriever=external_rag_command corpus=smoke_adapter semantic=0/12 accuracy=0.0 chunks=0 proof=0 custody=0
- `rag_2026_08_03t_c4x_external_oracle_topology_domain_inrepo_beast_local_semantic_cache`: retriever=local_semantic_cache corpus=reference_or_local semantic=0/12 accuracy=0.0 chunks=0 proof=0 custody=0
- `rag_2026_08_03t_c4x_external_rag_smoke_beast_local_semantic_cache`: retriever=local_semantic_cache corpus=reference_or_local semantic=0/12 accuracy=0.0 chunks=0 proof=0 custody=0
- `rag_pgvector_rag_real_run_002_beast_local_semantic_cache`: retriever=local_semantic_cache corpus=reference_or_local semantic=0/12 accuracy=0.0 chunks=0 proof=0 custody=0
- `rag_pgvector_rag_real_run_005_beast_local_semantic_cache`: retriever=local_semantic_cache corpus=reference_or_local semantic=0/12 accuracy=0.0 chunks=0 proof=0 custody=0
- `rag_2026_08_03t_c4x_external_oracle_topology_domain_inrepo_rag_nearest_exemplar`: retriever=nearest_exemplar_reference corpus=reference_or_local semantic=0/12 accuracy=0.0 chunks=0 proof=0 custody=0
- `rag_2026_08_03t_c4x_external_rag_smoke_rag_nearest_exemplar`: retriever=nearest_exemplar_reference corpus=reference_or_local semantic=0/12 accuracy=0.0 chunks=0 proof=0 custody=0
- `rag_pgvector_rag_real_run_002_rag_nearest_exemplar`: retriever=nearest_exemplar_reference corpus=reference_or_local semantic=0/12 accuracy=0.0 chunks=0 proof=0 custody=0
- `rag_pgvector_rag_real_run_005_rag_nearest_exemplar`: retriever=nearest_exemplar_reference corpus=reference_or_local semantic=0/12 accuracy=0.0 chunks=0 proof=0 custody=0

## Provider evidence lanes

- `provider_fitness_cerebras_openai_gpt-oss-120b_cerebras`: provider=cerebras model=openai/gpt-oss-120b:cerebras calls=2 clean=0 rescued=1 avoided=0 negative=2
- `provider_fitness_gemini_gemini-2.5-flash`: provider=gemini model=gemini-2.5-flash calls=2 clean=0 rescued=1 avoided=0 negative=2
- `provider_fitness_groq_llama-3.1-8b-instant`: provider=groq model=llama-3.1-8b-instant calls=2 clean=0 rescued=1 avoided=0 negative=2
- `provider_fitness_huggingface_openai_gpt-oss-120b`: provider=huggingface model=openai/gpt-oss-120b calls=2 clean=0 rescued=1 avoided=0 negative=2
- `provider_fitness_openrouter_gptoss_openai_gpt-oss-120b`: provider=openrouter_gptoss model=openai/gpt-oss-120b calls=2 clean=0 rescued=1 avoided=0 negative=2
- `provider_matrix_tournament`: provider=multi_provider_registry model=configured_provider_inventory calls=17 clean=2 rescued=0 avoided=0 negative=15
- `provider_omni_live_nvidia_nim_full_beast`: provider=nvidia_nim model= calls=24 clean=0 rescued=24 avoided=0 negative=0
- `provider_omni_live_nvidia_nim_raw`: provider=nvidia_nim model= calls=4 clean=0 rescued=0 avoided=0 negative=0
- `provider_teach_replay_generation_gauntlet`: provider=hf model=chat:gemini|image:hf calls=0 clean=5 rescued=0 avoided=6 negative=0

## Custody hard gates

- `beast_c4x`: pass=True failures=none
- `beast_capability_composition_rule_engine`: pass=False failures=semantic_without_proof_first, semantic_without_artifact_custody
- `beast_generation_provider_boundary`: pass=False failures=none
- `beast_local_semantic_cache`: pass=False failures=none
- `beast_topology_graph_adapter`: pass=False failures=none
- `cached_named_template`: pass=False failures=none
- `external_rag_retrieval`: pass=False failures=semantic_without_proof_first, semantic_without_artifact_custody
- `knowledge_graph_topology_only`: pass=False failures=none
- `model_generated_multimodal_stub`: pass=False failures=semantic_without_proof_first, semantic_without_artifact_custody
- `rag_nearest_exemplar`: pass=False failures=none
- `rule_engine_text_only`: pass=False failures=semantic_without_proof_first, semantic_without_artifact_custody

## Boundary

Three-front arena over the C4-X independent-oracle benchmark. Truth points are separate from raw compute measurements and hard custody/security gates. KV runtime credit is withheld unless runtime-native measurements are supplied; synthetic bytes are not accepted as public KV proof.
