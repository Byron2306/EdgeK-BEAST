# BEAST Mirror Architecture Gap Audit

Generated: 2026-06-17

## Read

The input governance systems are real and richer than the current live coding prompt uses. BEAST has:

- `ContextPacketBuilder`: bounded evidence, included/excluded records, semantic/artifact memory, handoff hashes.
- `OllamaScout`: economized task envelope, retrieved/ranked chunks, exact context, tool menu, Chronicle summary, forensic context, decision contract.
- `CompressionPipeline`: AST/JSON/text compression, chunks, evidence envelopes, Chronicle writes.
- `InsightCompiler`: ranked evidence, current-task markup, cloud handoff precheck.
- MCP runtime tools: `beast_prepare_handoff`, `beast_build_context_packet`, `beast_openclaw_plan`.
- Output governance: provider profiles, output contracts, Action IR, ref packets, resolver, compiler, evidence.

But the live coding flow is not fully mirrored. The input side is evidence-packet oriented; the output side is action-compiler oriented; the bridge between them is currently hand-built per flow.

## Main Break

`draft_source_patch_plan` reads selected files directly, builds snippets, adds the output schema/reference packet, and sends that to the provider. It does not build a context packet, use the Ollama scout packet, include ranked chunks, include tool menu, include Chronicle/forensic signals, or preserve a handoff hash in the output contract.

The ordinary live turn has the same shape: it calls `prepare_handoff` and records that the handoff exists, but then sends selected raw snippets in chat history instead of sending the governed handoff packet as the provider input.

So the flow is currently:

```text
input governance runs beside the provider prompt
output governance runs after the provider response
```

What the mirror architecture wants is:

```text
input governance constructs the provider world
output governance constrains the provider command
both share packet IDs, refs, hashes, evidence, and policies
```

## Consequence Seen In Live Tests

NIM received an output Action IR contract, but not the full input-governed world. Its prompt still had a locally assembled reference packet and task JSON, not a unified mirrored packet. It learned `file_ref`/`anchor_ref`, which is progress, but it still tried to write source-shaped `new` payloads.

That is a sign the output side is asking for “tiny commands,” while the input side is not yet giving it a tiny command vocabulary derived from local evidence and tools.

## Missing Pieces

1. A single provider handoff object

There should be one object that combines:

- context packet
- scout decision contract
- output profile
- Action IR schema
- reference packet
- allowed paths
- local transform/tool menu
- verification contract
- Chronicle/evidence IDs

Right now these are separate products.

2. Shared references across input and output

Input context has evidence IDs and handoff hashes. Output references have `F1`, `A19`, etc. Those should be one ref namespace:

- file refs
- evidence refs
- chunk refs
- tool refs
- action refs
- verification refs

3. Local transform vocabulary

NIM should not be asked to emit source snippets for known local edits. The Action IR should allow semantic local transforms:

- `add_provider_record`
- `set_default_model`
- `add_provider_alias`
- `update_route_card`
- `run_verifier`
- `ask_for_context`

Then BEAST compiles those transforms locally.

4. Output gate as MCP/interceptor peer

Input has interception layers and MCP governance. Output gate should publish the same kind of interception/evidence event:

- raw provider output
- parse status
- schema status
- ref resolution status
- diff compile status
- verification status
- fallback recommendation

5. End-to-end mirror tests

Current tests verify individual pieces. Missing test:

```text
task envelope -> context packet/scout packet -> provider prompt -> Action IR -> resolver -> compiler -> diff preview -> verify -> Chronicle
```

## Recommended Repair

Add `app/kernel/provider_handoff.py` as the mirror bridge.

It should expose:

```python
build_provider_handoff(
    root,
    objective,
    allowed_paths,
    provider,
    task_envelope=None,
    insight_packet=None,
    scout_packet=None,
)
```

and return:

```json
{
  "kind": "beast.provider_handoff.v1",
  "input": {
    "context_packet": {},
    "scout_contract": {},
    "ranked_chunks": [],
    "evidence_refs": []
  },
  "output": {
    "profile": {},
    "schema": {},
    "instructions": [],
    "references": {},
    "allowed_actions": []
  },
  "verify": {},
  "trace": {
    "handoff_hash": "...",
    "provider": "nvidia_nim"
  }
}
```

Then `/sourceplan` and the benchmark live path should call this instead of constructing prompt JSON ad hoc.

That is the missing mirror: not more isolated governance, but one object where input governance and output governance meet.
