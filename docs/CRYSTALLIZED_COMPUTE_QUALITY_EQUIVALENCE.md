# Crystallized Compute Quality Equivalence

## Question

For the same sealed coding task and budget, is a crystallized BEAST route at
least as good as an ephemeral agentic coding route? Passing tests alone is a
necessary floor, not a quality verdict.

## Comparator

Each held-out task is run in paired, randomized order from an identical clean
checkout:

| Lane | Allowed inputs | Prohibited inputs |
| --- | --- | --- |
| ephemeral baseline | same task envelope, local model/tools, time/token budget | BEAST crystals, prior route traces, hidden reference patch |
| crystallized | same task envelope, approved crystals/tools, local verifier | provider/model calls after admission, hidden reference patch |
| fallback | same task envelope after an intentional safe refusal | crystal execution |

The crystal route may not use a broader context window, extra model calls, or
an origin-produced patch supplied as a hidden input. All source, tool, model,
and retrieval traces are retained for audit but removed from grading packets.

## Quality floor and scorecard

Every response must meet all hard gates: build/integration tests, security
scans, no secret leakage, lint/type checks where applicable, and no unrelated
file changes. Failed hard gates score zero.

Blind reviewers score surviving patches on a 1–5 rubric: correctness,
maintainability, minimality, API/backwards compatibility, operational safety,
and explanation/diagnostic usefulness. Use at least one independent human
reviewer; an LLM judge can be supplementary only and must not be the origin
model or a BEAST route component.

## Required statistics

- paired pass/fail difference and exact McNemar test;
- paired median score difference with bootstrap confidence interval;
- per-dimension score deltas and inter-rater agreement;
- regressions, abstentions, fallback rate, and unsafe admissions;
- total cost: origin amortization, retrieval, verification, CPU/RAM/I/O,
  latency, and all model/tool calls.

The crystal route is quality-equivalent only when the lower confidence bound
for its paired quality difference is no worse than the preregistered margin,
all safety gates pass, and no hidden-input audit failure exists. It is better
only when the lower confidence bound is positive; speed/call avoidance cannot
substitute for this.

## Anti-gaming controls

- blind lane identity and randomize presentation order;
- grade diffs and test results, not BEAST receipts or prose claims;
- use fresh repository clones and sealed test cases;
- add adversarial maintenance changes after the initial patch;
- compare against a time/token matched ephemeral agent, not an intentionally
  weakened baseline;
- publish every failed, refused, and fallback task.

## Relation to compound proof

For a compound crystal DAG, score both the final patch and the quality of its
intermediate typed outputs: correct task classification, appropriate tool
selection, context sufficiency, and refusal behavior. This exposes a system
that merely replays a final patch while claiming agentic reasoning.
