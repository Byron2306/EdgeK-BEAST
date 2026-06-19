# Coding Task Completion Harness

Generated at: `2026-06-17T10:10:21Z`

Verified deterministic task-completion A/B. Each lane edits an isolated broken workspace; pytest determines completion.

## Provider Contracts

- `codex`: `ok` model=`gpt-5-codex` backend=`openai_compatible`
- `openai`: `ok` model=`gpt-4o-mini` backend=`openai_compatible`
- `nvidia_nim`: `ok` model=`meta/llama-3.1-70b-instruct` backend=`openai_compatible`
- `local_nim`: `ok` model=`local-nim-model` backend=`openai_compatible`
- `litellm`: `ok` model=`litellm/ollama` backend=`litellm`
- `openrouter`: `ok` model=`litellm/openrouter/auto` backend=`litellm`
- `ollama`: `ok` model=`llama3.2:3b` backend=`ollama`

## Summary

- `raw_completed`: `False`
- `beast_completed`: `True`
- `beast_won`: `True`
- `both_completed`: `False`
- `prompt_token_reduction_percent`: `99.3271`
- `raw_prompt_tokens`: `17537`
- `beast_prompt_tokens`: `118`

## Lane Results

### raw
- Completed: `False`
- Return code: `1`
- Prompt tokens: `17537`
- Files changed: `none`
- Reason: raw lane exceeded context budget before identifying the focused edit (17537>8000)

```text
[100%]
=================================== FAILURES ===================================
____________________________ test_codex_is_routable ____________________________

    def test_codex_is_routable():
        records = {record.provider_id: record for record in ProviderRegistry().records()}
    
>       assert records["codex"].backend == "openai_compatible"
               ^^^^^^^^^^^^^^^^
E       KeyError: 'codex'

tests/test_provider_contracts.py:8: KeyError
___________________ test_beast_auto_resolves_concrete_models ___________________

    def test_beast_auto_resolves_concrete_models():
        api = BeastApiClient()
    
>       assert api._chat_model_for_provider("codex", "beast-auto") == "gpt-5-codex"
E       AssertionError: assert '' == 'gpt-5-codex'
E         
E         - gpt-5-codex

tests/test_provider_contracts.py:16: AssertionError
=========================== short test summary info ============================
FAILED tests/test_provider_contracts.py::test_codex_is_routable - KeyError: '...
FAILED tests/test_provider_contracts.py::test_beast_auto_resolves_concrete_models
2 failed, 1 passed in 0.02s
```

### beast
- Completed: `True`
- Return code: `0`
- Prompt tokens: `118`
- Files changed: `app/cli/api.py, app/kernel/provider_registry.py`
- Reason: BEAST lane used focused task packet and verified the repair

```text
...                                                                      [100%]
3 passed in 0.01s
```
