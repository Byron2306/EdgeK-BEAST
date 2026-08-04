# C4-X Truth Arena · truth-arena-live-rds-forge-provider-002

- Receipt: `sha256:607bf3113353d6839b95e08c006ddfb01f35f80ca07b0a987060d386225d5306`
- Source C4-X receipt: `sha256:56b80ff2e0760f24d66519ad0a7c5f5094b3a20dc294cfc1855c9baf103f798f`
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
- `external_rag_retrieval`: 96/192 semantic=12/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `rule_engine_text_only`: 61/192 semantic=5/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `cached_named_template`: 36/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `beast_topology_graph_adapter`: 32/192 semantic=1/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `model_generated_multimodal_stub`: 26/192 semantic=1/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=24
- `beast_generation_provider_boundary`: 21/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=24
- `beast_local_semantic_cache`: 21/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `knowledge_graph_topology_only`: 21/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0
- `rag_nearest_exemplar`: 21/192 semantic=0/12 proof=0/12 custody=0/12 visual_custody=0/12 providers=0

## Compute reuse / KV War

- Runtime-native KV measurements supplied: `True`
- Synthetic KV public credit: `False`
- Covered KV cases: `['exact_repeated_prefix']`
- Missing KV case count: `15`
- `kv_forge_ml_kem_transport`: class=hypothesis engine=sglang cold=Nonems warm=Nonems cached_tokens=0 passed=[] failed=['cache_transported_to_second_node']
- `kv_llamacpp_prompt_cache`: class=observed_engine_local_prefix_cache engine=llama.cpp cold=13616.182ms warm=226.166333ms cached_tokens=962 passed=['exact_repeated_prefix'] failed=[]
- `kv_llamacpp_restart_boundary`: class=observed_restart_boundary engine=llama.cpp cold=9479.907ms warm=192.818ms cached_tokens=642 passed=[] failed=['engine_process_restarted']

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
- `beast_topology_graph_adapter`: pass=False failures=semantic_without_proof_first, semantic_without_artifact_custody
- `cached_named_template`: pass=False failures=none
- `external_rag_retrieval`: pass=False failures=semantic_without_proof_first, semantic_without_artifact_custody
- `knowledge_graph_topology_only`: pass=False failures=none
- `model_generated_multimodal_stub`: pass=False failures=semantic_without_proof_first, semantic_without_artifact_custody
- `rag_nearest_exemplar`: pass=False failures=none
- `rule_engine_text_only`: pass=False failures=semantic_without_proof_first, semantic_without_artifact_custody

## Boundary

Three-front arena over the C4-X independent-oracle benchmark. Truth points are separate from raw compute measurements and hard custody/security gates. KV runtime credit is withheld unless runtime-native measurements are supplied; synthetic bytes are not accepted as public KV proof.
