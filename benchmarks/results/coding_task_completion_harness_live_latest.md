# Coding Task Completion Harness

Generated at: `2026-06-17T10:17:39Z`

Live OpenAI-compatible provider task-completion A/B. Each lane receives a prompt, provider returns JSON operations, pytest determines completion.

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
- `prompt_token_reduction_percent`: `96.7572`
- `raw_prompt_tokens`: `34723`
- `beast_prompt_tokens`: `1126`

## Lane Results

### raw_live
- Completed: `False`
- Return code: `1`
- Prompt tokens: `34723`
- Files changed: `app/cli/api.py, app/kernel/provider_registry.py`
- Reason: live provider operations applied but pytest failed

```text
.F.                                                                      [100%]
=================================== FAILURES ===================================
___________________ test_beast_auto_resolves_concrete_models ___________________

    def test_beast_auto_resolves_concrete_models():
        api = BeastApiClient()
    
        assert api._chat_model_for_provider("codex", "beast-auto") == "gpt-5-codex"
        assert api._chat_model_for_provider("openai", "beast-auto") == "gpt-4o-mini"
        assert api._chat_model_for_provider("nvidia-nim", "beast-auto") == "meta/llama-3.1-70b-instruct"
        assert api._chat_model_for_provider("local-nim", "beast-auto") == "local-nim-model"
>       assert api._chat_model_for_provider("litellm", "beast-auto") == "litellm/ollama"
E       AssertionError: assert 'ollama' == 'litellm/ollama'
E         
E         - litellm/ollama
E         + ollama

tests/test_provider_contracts.py:20: AssertionError
=========================== short test summary info ============================
FAILED tests/test_provider_contracts.py::test_beast_auto_resolves_concrete_models
1 failed, 2 passed in 0.02s
```

### beast_live
- Completed: `True`
- Return code: `0`
- Prompt tokens: `1126`
- Files changed: `app/cli/api.py, app/kernel/provider_registry.py`
- Reason: live provider returned scoped operations; pytest verified result

```text
...                                                                      [100%]
3 passed in 0.01s
```
