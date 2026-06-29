from gateway.auth import public_provider_config
from gateway.client import resolve_model
from gateway.providers import normalize_provider
from gateway.streaming import collect_stream

def test_provider_aliases_normalize():
    assert normalize_provider('NVIDIA-NIM') == 'nvidia_nim'
    assert normalize_provider(' open ai ') == 'openai'

def test_public_config_redacts_nested_secret_material():
    public = public_provider_config({'api_key': 'secret', 'name': 'nim', 'nested': {'token': 'hide', 'safe': 3}})
    assert public['api_key_present'] is True
    assert 'api_key' not in public
    assert public['nested']['token'] == '<redacted>'
    assert public['nested']['safe'] == 3

def test_streaming_preserves_empty_chunks_and_stops_on_none():
    assert collect_stream(['alpha', '', 'omega', None, 'ignored']) == ['alpha', '', 'omega']

def test_beast_auto_uses_normalized_provider():
    assert resolve_model('NVIDIA-NIM', 'beast-auto') == 'nvidia/nemotron-3-super-120b-a12b'
