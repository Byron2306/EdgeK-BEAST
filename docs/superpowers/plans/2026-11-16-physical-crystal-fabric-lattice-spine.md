# Physical Crystal Fabric — Lattice Spine (governed, fail-closed composition graph)

**Claim boundary:** this delivery builds a governed, fail-closed composition graph. PGEC Appendix B lists "General
multi-crystal composition is safe and useful" as *Emerging implementation; not yet established by broad evidence*.
PGEC §8.1 item 4 (compound experiential compilation, where every stage may refuse independently) is the target. Nothing
here claims composition is proven safe or useful. Composite *execution* uses the existing D6 session machinery. An
end-to-end composite benchmark is not part of this delivery.

## Sources
- **PGEC:**
  - eq. 2 K = (P, Θ, Gₖ, Q, Γ, 𝒱, 𝒜, Δ). The authority envelope 𝒜 is eq. 3.
  - §2.4 Promotion Sovereignty; §3.3 similarity never confers authority; eq. 6 V_K.
  - §8.1(4) compound compilation; §8.2 composition risk and exchange without hidden authority; Appendix B.
- **IEI v0.9:**
  - §7.12.1 / Table 15: the D9 router, where similarity only nominates.
  - §7.13.1 false hits → demotion and credit reversal; §7.13.2 chain-witnessed ledger; §7.13.3 internal credits only; §9.
- Operator rulings 2026-11-16, covering the lattice spine, the premium formula and the eligibility rules.

## Model
- **Lattice nodes:**
  - Promoted coding crystals (`kind=crystal`).
  - Composites (`kind=composite`, `component_ids`, at least 2 distinct children).
  - Edges use `crystal_hypergraph.EDGE_TYPES`: child `COMPOSES_WITH` composite, composite `DERIVED_FROM` children,
    composite `VERIFIED_BY` verifier receipt, and `SUPERSEDES` / `FAILED_UNDER` on demotion.
  - Persisted in SQLite under `.beast/crystals/crystal_lattice.sqlite3`. Every node and edge row is validated through
    a `CrystalHypergraph` before commit.
- **Witnessing:** every mutation (add, admit, refuse, demote) appends to the existing `CrystalLatticeLedger`
  (checkpoint payload `crystal_lattice_spine_mutation`) and to the existing `CrystalChainLedger`
  (`crystal_lattice_spine_<op>` block). There is no second ledger. If witnessing fails, the SQLite transaction rolls
  back. `GET /edgek/crystal-lattice` already shows the ledger head. A read-only `GET /edgek/crystal-lattice/spine`
  exposes nodes and edges; it takes effect on the next gateway restart, and 8101 is not restarted.
- **Authority:** A_C is the set of reviewed tool_ids in C's steps. For a composite, A_L = ⋂ A_Ci (PGEC eq. 3; §8.2 no
  hidden authority). Every composite step must stay inside A_L.
- **Contracts:** `CodingCrystalCandidate` and `EpisodeEnvelope` gain `component_ids`, `authority` and
  `composite_verification`. Empty values are excluded from the digest, so existing crystal and envelope digests are
  unchanged.

## Admission (PGEC §2.4, §8.1(4))
`admit_composite` returns ADMIT, REFUSE, REVALIDATE or ESCALATE:
- **REFUSE:**
  - fewer than 2 distinct children (one-child wrapper);
  - an unknown child, a child that is demoted or not a lattice node;
  - a cycle;
  - authority exceeding ⋂ A_Ci;
  - an invalid candidate;
  - a composite verifier that failed (fewer than 3/3 held-out variants).
- **REVALIDATE:** a child is promoted in the registry but its lattice record digest or source envelope no longer
  matches.
- **ESCALATE:** no composite verifier result, children joined by a `CONFLICTS_WITH` edge, or a missing operator
  approval (`approved_by`).
- **ADMIT:** all children are verified, the composite verifier passed, authority is the intersection and an operator
  approved. The composite is then promoted in the D6 registry with its own replay receipt.

## Demotion (IEI §7.13.1)
- Demoting C walks upward through every composite containing C (transitively), demotes each in the lattice and the
  registry, and witnesses each step.
- **Economy:**
  - Demoting a child claws back the child's credits and every ancestor's premium.
  - Demoting L claws back only L's premium; the children keep theirs.

## Credits (D7 shadow ledger; PGEC eq. 6; operator formula 2026-11-16)
Per verified composite reuse:
- **V_L:** measured from the composite reuse envelope against the composite's measured baseline.
- **Child credit:** max(0, V_Ci), where V_Ci = the child's measured baseline cost minus a step-proportional share of the
  composite's measured reuse cost (attribution rule recorded on the entry). Each child is subject to its own
  refusal rules (promoted, not clawed, not self-dealing).
- **Cap:** if Σ child credits > max(0, V_L), the children are scaled pro rata to V_L and no premium is paid.
- **Premium:** otherwise the premium is S = max(0, V_L − Σ max(0, V_Ci)), paid to the lattice publisher.
- **Premium refused when:**
  - there are fewer than 2 distinct children;
  - the lattice publisher's controller owns every child;
  - the consumer shares a controller with the lattice publisher.
- **Ratings:** applied to children as a 0.5x–1.5x multiplier, rated once by the receipt's consumer. The total for a
  receipt is capped at V_L: any overflow first reduces the premium (with a witnessed negative adjustment), then
  truncates the rating delta. **Credits never exceed the measured V_L.**
- Shadow ledger only: non-financial, non-transferable, non-redeemable.

## Router (D9)
`CodingCrystalRouter(lattice=...)` nominates only lattice-admitted nodes and prefers the highest admitted composite for
the task family. The lattice node digest becomes a fingerprint on both sides. Similarity only nominates; D6 activation
gates decide.

## Tasks
1. Extend the contracts (candidate and envelope): composite fields, digest-stable when empty, validation, `compose()`.
2. `crystal_lattice_spine.py`: `CrystalLattice` (persist, hypergraph validation, witnessing), `admit_composite`,
   `demote` cascade.
3. D7 economy: `account_composite_reuse`, `rate_composite`, and the cascade clawback helper.
4. Router: point it at the spine.
5. Tests:
   - two-child admission needs both children and the composite to pass;
   - authority intersection;
   - child demotion cascades and claws back;
   - one-child wrapper refused;
   - self-composition earns no premium;
   - credits ≤ V_L.
6. Verification: scoped suites, Ruff, `git diff --check`.
