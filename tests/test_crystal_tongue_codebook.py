from app.kernel.compute.crystal_tongue import compile_crystal_tongue
from app.kernel.compute.crystal_tongue_codebook import clear_shared_codebooks, compile_codebook, decode_suffix, shared_codebook


def test_codebook_round_trips_v2_packet():
    ir = compile_crystal_tongue({"task_family": "provider_normalization", "failure": "KeyError[nim]", "symbol": "normalize", "old": "value", "rules": ["strip", "lower"], "constraints": ["one_file"], "verify": "pytest", "unresolved_fields": ["new"]})
    codebook = compile_codebook(ir, tokenizer=lambda value: 1 if value.startswith("p") else len(value), tokenizer_id="test-tokenizer")
    assert codebook.stable_prefix().startswith("C2LEX|tokenizer:test-tokenizer|")
    assert decode_suffix(codebook.encode(ir), codebook) == ir


def test_tokenizer_cost_changes_alias_choice():
    ir = compile_crystal_tongue({"task": "x", "failure": "y", "symbol": "z", "old": "old"})
    codebook = compile_codebook(ir, tokenizer=lambda value: 1 if value == "p1" else 99)
    assert codebook.entries[0].code == "p1"


def test_shared_codebook_preserves_symbols_between_requests():
    clear_shared_codebooks()
    first = compile_crystal_tongue({"task": "first", "failure": "missing import", "symbol": "parse", "old": "value"})
    second = compile_crystal_tongue({"task": "second", "failure": "missing import", "symbol": "parse", "old": "other"})
    first_book, first_added, _ = shared_codebook(first, tokenizer_id="shared-test")
    second_book, second_added, reused = shared_codebook(second, tokenizer_id="shared-test")
    first_codes = {(entry.field, entry.value): entry.code for entry in first_book.entries}
    second_codes = {(entry.field, entry.value): entry.code for entry in second_book.entries}
    assert first_added > 0
    assert second_added > 0
    assert reused > 0
    assert all(second_codes[key] == code for key, code in first_codes.items())
    first_again, _, _ = shared_codebook(first, tokenizer_id="shared-test")
    assert first_again.stable_prefix() == first_book.stable_prefix()
