# Coding Agent A/B Harness

Generated at: `2026-06-17T10:02:36Z`

Synthetic, intentionally overloaded prompt-surface benchmark. It measures pre-invocation context/tool reduction, not verified task completion.

## Provider Contracts

- `codex`: `ok` model=`gpt-5-codex` backend=`openai_compatible` route=`openai_compatible`
- `openai`: `ok` model=`gpt-4o-mini` backend=`openai_compatible` route=`openai_compatible`
- `litellm`: `ok` model=`litellm/ollama` backend=`litellm` route=`litellm`
- `openrouter`: `ok` model=`litellm/openrouter/auto` backend=`litellm` route=`litellm`
- `nvidia_nim`: `ok` model=`meta/llama-3.1-70b-instruct` backend=`openai_compatible` route=`openai_compatible`
- `local_nim`: `ok` model=`local-nim-model` backend=`openai_compatible` route=`openai_compatible`
- `ollama`: `ok` model=`llama3.2:3b` backend=`ollama` route=`ollama`

## Summary

- `scenario_count`: `3`
- `median_raw_prompt_tokens`: `40474`
- `median_beast_prompt_tokens`: `476`
- `median_prompt_token_reduction_percent`: `98.8239`
- `total_prompt_token_reduction_percent`: `98.9606`
- `median_orientation_step_reduction`: `15`
- `mean_success_score_delta`: `0.2744`

## Scenarios

### provider_model_wiring
- Raw tokens: `40474`
- BEAST tokens: `486`
- Token reduction: `98.7992%`
- Orientation step reduction: `15`
- Success score delta: `0.265`

### context_economy_regression
- Raw tokens: `59426`
- BEAST tokens: `396`
- Token reduction: `99.3336%`
- Orientation step reduction: `18`
- Success score delta: `0.2933`

### approval_gated_patch_flow
- Raw tokens: `30757`
- BEAST tokens: `476`
- Token reduction: `98.4524%`
- Orientation step reduction: `14`
- Success score delta: `0.265`
