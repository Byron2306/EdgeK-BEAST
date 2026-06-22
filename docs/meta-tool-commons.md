# Meta Tool Commons

The Meta Tool Commons is BEAST's opt-in coordination layer for tool and skill
capability evidence. It is not a universal leaderboard and it does not install
shared tools automatically.

## Flow

1. Capability Exchange produces privacy-allowlisted outcome evidence.
2. Commons validates the evidence hash and deduplicates it.
3. Rankings are scoped to capability version, schema hash, task class, and role.
4. Global evidence acts as a prior; local evidence remains the stronger signal.
5. Promotion candidates are staged with pinned schemas and risk classes.
6. Local BEAST policy and explicit user approval decide whether to adopt them.

The Commons never accepts prompts, source code, file paths, secrets, or API
tokens. One contributor is capped per capability and context so repeated reports
from one node cannot dominate a ranking.

## Candidate Adoption

Shared candidates are advisory. Adoption defaults to dry-run and requires all of:

- a supported tool, skill, or meta-tool recipe kind;
- a `sha256:` schema pin;
- a locally acceptable risk class;
- `approved=true` and `dry_run=false` at the local BEAST instance.

Approved recipes enter the existing skill registry with Commons provenance. The
Commons does not execute a candidate during adoption.

## Surfaces

- `GET /edgek/meta-tool-commons`
- `POST /edgek/meta-tool-commons/ingest`
- `POST /edgek/meta-tool-commons/rank`
- `POST /edgek/meta-tool-commons/candidates`
- `POST /edgek/meta-tool-commons/adopt`
- `GET /edgek/meta-tool-commons/snapshot`
- MCP tool: `beast_meta_tool_commons`

Integrity-hashed snapshots can transport advisory rankings between BEAST nodes.
They preserve schema and context boundaries and still require local approval for
candidate adoption.
