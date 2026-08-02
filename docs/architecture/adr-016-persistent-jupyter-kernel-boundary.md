# ADR-016: Persistent Jupyter kernel boundary

## Status

Accepted

## Context

One-shot Python execution is useful for a quick cell but does not preserve variables, imports, execution counts, or notebook-style iteration. BEAST now ships Jupyter and IPython tooling, so the desktop needs a kernel lifecycle without exposing ZMQ ports or child-process handles to the renderer.

## Decision

Run a workspace-scoped BEAST Python Jupyter kernel behind a Python JSON-lines relay. Electron main owns relay lifecycle, forwards structured execution requests, imposes cell/output/time limits, and creates an execution digest. The renderer receives only a narrow start/request/stop IPC contract.

## Trade-offs

The first kernel supports Python, persistent execution state, normalized Jupyter MIME bundles, `.ipynb` output persistence, and trust-aware rendering for text, HTML, Markdown, JSON, PNG/JPEG, and SVG outputs. Interactive widgets and full VS Code notebook contribution APIs remain future work. The kernel uses local loopback transport internally; this is contained within the main-process boundary and never exposed to the renderer.

## Consequences

- Positive: repeated cells share state and are materially closer to VS Code notebooks.
- Negative: the Jupyter bundle increases the desktop payload and a kernel can execute user-provided code.
- Mitigation: startup is explicit, the workspace is recorded, cells have bounded size/time/output, and every result gets a digest receipt.
