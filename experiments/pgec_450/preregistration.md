# PGEC 450-Observation Preregistration

## Study purpose

This study tests whether BEAST can transform repeated, verified agentic inference into bounded reusable capability while preserving verification quality and refusing unsafe recurrence. The primary local route is Ollama; NVIDIA NIM is the principal external control route.

## Frozen factorial design

\[
6\;\text{task families}\times5\;\text{routes}\times5\;\text{occurrence points}\times3\;\text{lanes}=450\;\text{observations}
\]

### Task families

1. `schema_validation`
2. `provider_alias_normalization`
3. `patch_compilation`
4. `syntax_check`
5. `route_diagnostics`
6. `secret_redaction`

### Routes

1. `ollama`
2. `nvidia_nim`
3. `mistral`
4. `cohere`
5. `groq`

### Occurrence points

`O1`, `O2`, `O3`, `O5`, and `O10`.

### Lanes

- **Raw:** provider output without BEAST repair or recurrence.
- **Governed, no compilation:** BEAST output governance and verification, but no crystal recurrence.
- **Full PGEC:** governance, candidate accumulation, admissibility checks, recurrence, refusal, and revalidation.

## Confirmatory contrasts

1. Full PGEC versus governed no-compilation for verified completion and hidden-pass outcomes.
2. Full PGEC versus governed no-compilation for provider-call count.
3. Ollama full PGEC versus NVIDIA NIM full PGEC for verified completion, refusal correctness, and recurrence eligibility.
4. Safe recurrence cases versus drift cases for false reuse and correct refusal.

## Primary equations

\[
\mathrm{VCR}=\frac{N_{visible\;pass\land hidden\;pass}}{N_{evaluable}}
\]

\[
\mathrm{QPCCD}=\frac{N_{quality\;preserved\land fewer\;provider\;calls}}{N_{paired\;evaluable}}
\]

\[
\mathrm{FRR}=\frac{N_{incorrect\;recurrences}}{N_{recurrence\;attempts}}
\]

\[
\mathrm{CRR}=\frac{N_{unsafe\;cases\;refused}}{N_{unsafe\;cases}}
\]

\[
\mathrm{URR}=\frac{N_{safe\;cases\;refused}}{N_{safe\;cases}}
\]

False reuse is a redline and must remain zero for a successful safety claim.

## Mutation interpretation

Occurrence does not itself define mutation. Any mutation condition must be recorded independently as `none`, `cosmetic`, `semantic_adjacent`, `structural_tool_schema`, or `breaking_target_test`. The core 450 cells remain the frozen factorial matrix; mutation analyses are stratified annotations, not post hoc cell replacements.

## Data retention

Each observation must preserve its plan row, provider request metadata, response digest or approved raw response, verifier results, recurrence decision, fingerprint, receipts, exclusion state, and artifact integrity hash. Secrets and unrelated repository content must be redacted.

## Stopping and exclusions

No route, task, occurrence, or lane may be removed because of an unfavourable result. Missing credentials or unavailable endpoints are recorded as `not_configured` or `unavailable`, not silently replaced. Confirmatory analysis begins only after the frozen matrix ledger is sealed.
