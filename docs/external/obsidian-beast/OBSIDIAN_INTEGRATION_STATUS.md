# Obsidian BEAST blueprint integration status

The blueprint is useful as a product and interaction specification, not as a
second execution spine. Existing BEAST primitives remain authoritative.

| Blueprint concept | Current BEAST surface | Status |
|---|---|---|
| 369 Mission Kernel | Mission/SourcePlan/Policy Gate | partial; add explicit stop rules |
| Chainflow | PREC lifecycle, Chronicle, verification, crystallization | partial; expose a nine-step UI stepper |
| TwinSwarm | Agents, verifier lanes, governed executor | partial; builder/challenger role binding remains |
| Obsidian Mirror | Evidence Graph, Chronicle, Memory | implemented in separate stores; unify mission links |
| Blackline Bus | Crystal Bus + runtime event bus | implemented locally; ARDA appraisal binding added |
| Stone Ledger | rollback snapshots and durable evidence | partial; rollback orchestrator now exists |
| Black Seal | content hashes, signatures, sealed capsules | implemented for governed artifacts |
| Two-Brain Memory | active memory and reflective crystallization | partial; promotion requires verified candidates |
| Canaries / Sphinx Gate | Seraph, policy gates, route damping | partial; UI exposure remains |
| PulseOps / Night Watch | scheduler and Commons Job Choir | contract/backend surfaces exist; UI pending |
| Skill Vault | SkillRegistry and promotion loop | implemented with approval boundary |

## Immediate implementation order

1. Add a visible Chainflow stepper to Mission/Studio.
2. Bind TwinSwarm builder/challenger roles to agent sessions.
3. Link active and reflective memory entries to mission/evidence IDs.
4. Surface canary, route-damping, and PulseOps state in Commons Forge.
5. Keep all blueprint-only names as aliases or UI labels; do not create a
   parallel policy or execution authority.
