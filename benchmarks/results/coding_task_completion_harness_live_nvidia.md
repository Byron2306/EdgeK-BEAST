# Coding Task Completion Harness

Generated at: `2026-06-17T10:15:54Z`

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
- `beast_completed`: `False`
- `beast_won`: `False`
- `both_completed`: `False`
- `prompt_token_reduction_percent`: `97.1258`
- `raw_prompt_tokens`: `34723`
- `beast_prompt_tokens`: `998`

## Lane Results

### raw_live
- Completed: `False`
- Return code: `2`
- Prompt tokens: `34723`
- Files changed: `app/cli/api.py, app/kernel/provider_registry.py`
- Reason: live provider operations applied but pytest failed

```text
587: in import_path
    importlib.import_module(module_name)
/usr/lib/python3.13/importlib/__init__.py:88: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
<frozen importlib._bootstrap>:1387: in _gcd_import
    ???
<frozen importlib._bootstrap>:1360: in _find_and_load
    ???
<frozen importlib._bootstrap>:1331: in _find_and_load_unlocked
    ???
<frozen importlib._bootstrap>:935: in _load_unlocked
    ???
/home/byron/.local/lib/python3.13/site-packages/_pytest/assertion/rewrite.py:197: in exec_module
    exec(co, module.__dict__)
tests/test_provider_contracts.py:1: in <module>
    from app.cli.api import BeastApiClient
E     File "/tmp/beast_live_task_completion_xi_pbb2l/raw_live/app/cli/api.py", line 6
E       provider_id = str(provider or "").lower().replace("-", "_")
E       ^^^^^^^^^^^
E   IndentationError: expected an indented block after function definition on line 5
=========================== short test summary info ============================
ERROR tests/test_provider_contracts.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.09s
```

### beast_live
- Completed: `False`
- Return code: `1`
- Prompt tokens: `998`
- Files changed: `none`
- Reason: live provider lane failed safely: The read operation timed out

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
