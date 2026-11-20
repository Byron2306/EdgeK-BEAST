"""Bind the native crystal lifecycle to the Direct Coder engine."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.kernel.agents.planner_models import PlannerDecision, PlannerDecisionType
from app.kernel.compute.coder_crystal_feedback import PROFILE
from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeBuilder, RunBudgetTracker, episode_observations



class DirectCoderFamilySession:
    """Drive one promoted FamilyCrystal through the native Direct Coder tool path.

    The session never edits files itself. Resolvers may probe scratch copies, but
    admitted mutations are emitted as ordinary governed PlannerDecision objects.
    """

    LIVE_FAMILIES = frozenset({
        "fix-config-constant",
        "fix-logic-operator",
        "fix-off-by-one",
        "fix-unhandled-exception",
        "refactor-rename-symbol",
    })

    def __init__(self, crystal, registry, *, root: Path, target: str,
                 verify_command, baseline_result, engine, run_id: str):
        self.crystal = crystal
        self.registry = registry
        self.root = root
        self.target = target
        self.verify_command = list(verify_command)
        self.engine = engine
        self.run_id = run_id

        self.stage = 0
        self.pending = []
        self.waiting_for_verify = False
        self.previous_failures = self._failures(baseline_result)
        self.last_verify_marker = None
        self.done = False
        self.succeeded = False
        self.refused = False

        self.lattice_topology = None
        self.current_lattice_leaf = None
        self.compound_dag = None
        self.compound_rows = {}
        self.compound_fragments = []

        if self.crystal.component_ids:
            from app.kernel.compute import family_crystals as fc

            # Discovery already validated this topology. Reconstruct it here so
            # execution receipts are independently bound to the admitted graph.
            self.lattice_topology = fc.lattice_topology(
                self.registry,
                self.crystal,
            )

            # The proof DAG must admit envelope/evidence/plan before Direct
            # Coder is permitted to execute the first lattice mutation.
            self.compound_dag = None
            self.compound_rows = {}
            self._init_compound_dag(baseline_result)

    @staticmethod
    def _output(result):
        return "\\n".join(
            str((result or {}).get(key) or "")
            for key in ("stdout", "stderr")
        ).strip()

    @classmethod
    def _failures(cls, result):
        from app.kernel.compute import family_crystals as fc

        result = result or {}
        rc = result.get("returncode")
        if type(rc) is not int:
            return 10**9
        return fc.failure_count(cls._output(result), rc)

    def _families(self):
        return self.crystal.component_families or (self.crystal.task_family,)

    def _compound_emit(self, stage, row):
        self.engine.emit(self.run_id, "agent.compound_crystal.stage.admitted", {
            "lattice_id": self.crystal.crystal_id,
            "stage": stage,
            "proof_digest": row.get("proof_digest"),
            "output_digest": row.get("output_digest"),
            "verifier": row.get("verifier"),
        })

    def _init_compound_dag(self, baseline_result):
        """Bind the live lattice execution to the existing compound proof DAG.

        This does not replace Direct Coder execution. It makes the already-live
        execution proof-carrying before the first mutation is admitted.
        """
        if self.lattice_topology is None:
            return

        from app.kernel.compute.compound_crystallization import (
            CompoundCrystallizationDAG,
            StageReceipt,
        )

        dag = CompoundCrystallizationDAG()

        envelope = {
            "run_id": self.run_id,
            "lattice_id": self.crystal.crystal_id,
            "task_family": self.crystal.task_family,
            "target": self.target,
            "verify_command": list(self.verify_command),
            "baseline_failures": self.previous_failures,
        }
        envelope_row = StageReceipt(
            "envelope",
            {},
            envelope,
            "direct_coder_lattice_envelope_v1",
            {
                "passed": 0 < self.previous_failures < 10**9,
                "baseline_failures": self.previous_failures,
            },
        ).to_dict()
        dag.admit(envelope_row)

        topology = self.lattice_topology
        evidence = {
            "root": topology.get("root"),
            "leaves": list(topology.get("leaves") or ()),
            "leaf_count": topology.get("leaf_count"),
            "component_families": list(
                topology.get("component_families") or ()
            ),
            "expected_failures": topology.get("expected_failures"),
        }
        evidence_row = StageReceipt(
            "evidence",
            {"envelope": envelope_row["proof_digest"]},
            evidence,
            "direct_coder_lattice_topology_v1",
            {
                "passed": (
                    int(topology.get("leaf_count") or 0)
                    == len(self._families())
                    and int(topology.get("leaf_count") or 0) > 1
                ),
                "leaf_count": topology.get("leaf_count"),
            },
        ).to_dict()
        dag.admit(evidence_row, predecessors=("envelope",))

        plan = {
            "lattice_id": self.crystal.crystal_id,
            "ordered_families": list(self._families()),
            "ordered_leaves": [
                {
                    "crystal_id": leaf.get("crystal_id"),
                    "task_family": leaf.get("task_family"),
                    "parent_id": leaf.get("parent_id"),
                    "path": list(leaf.get("path") or ()),
                }
                for leaf in topology.get("leaves") or ()
            ],
            "postcondition": "independent worktree verifier reaches zero failures",
        }
        plan_row = StageReceipt(
            "plan",
            {
                "envelope": envelope_row["proof_digest"],
                "evidence": evidence_row["proof_digest"],
            },
            plan,
            "direct_coder_lattice_plan_v1",
            {
                "passed": (
                    len(plan["ordered_leaves"])
                    == len(plan["ordered_families"])
                    and all(
                        leaf["task_family"] == family
                        for leaf, family in zip(
                            plan["ordered_leaves"],
                            plan["ordered_families"],
                            strict=True,
                        )
                    )
                ),
                "stage_count": len(plan["ordered_leaves"]),
            },
        ).to_dict()
        dag.admit(
            plan_row,
            predecessors=("envelope", "evidence"),
        )

        self.compound_dag = dag
        self.compound_rows = {
            "envelope": envelope_row,
            "evidence": evidence_row,
            "plan": plan_row,
        }

        self._compound_emit("envelope", envelope_row)
        self._compound_emit("evidence", evidence_row)
        self._compound_emit("plan", plan_row)

    def _finalize_compound_dag(self, current_failures):
        if getattr(self, "compound_dag", None) is None:
            return True

        from app.kernel.compute.compound_crystallization import (
            CompoundAdmissionError,
            StageReceipt,
        )

        try:
            plan_row = self.compound_rows["plan"]

            execute = {
                "lattice_id": self.crystal.crystal_id,
                "stages_executed": len(self._families()),
                "final_failures": current_failures,
                "fragments": list(self.compound_fragments),
                "fragment_count": len(self.compound_fragments),
                "mutated_paths": sorted({
                    path
                    for item in self.compound_fragments
                    for path in item.get("paths") or ()
                }),
                "leaf_ids": [
                    leaf.get("crystal_id")
                    for leaf in self.lattice_topology.get("leaves") or ()
                ],
            }
            execute_row = StageReceipt(
                "execute",
                {"plan": plan_row["proof_digest"]},
                execute,
                "direct_coder_governed_execution_v1",
                {
                    "passed": (
                        self.stage == len(self._families()) - 1
                        and current_failures == 0
                    ),
                    "stages_executed": len(self._families()),
                },
            ).to_dict()
            self.compound_dag.admit(
                execute_row,
                predecessors=("plan",),
            )

            verification = {
                "lattice_id": self.crystal.crystal_id,
                "verify_command": list(self.verify_command),
                "final_failures": current_failures,
                "postcondition": current_failures == 0,
            }
            verify_row = StageReceipt(
                "verify",
                {
                    "execute": execute_row["proof_digest"],
                    "plan": plan_row["proof_digest"],
                },
                verification,
                "direct_coder_independent_worktree_verify_v1",
                {
                    "passed": current_failures == 0,
                    "final_failures": current_failures,
                },
            ).to_dict()
            self.compound_dag.admit(
                verify_row,
                predecessors=("execute", "plan"),
            )

        except (CompoundAdmissionError, KeyError, ValueError) as exc:
            self.engine.emit(
                self.run_id,
                "agent.compound_crystal.refused",
                {
                    "lattice_id": self.crystal.crystal_id,
                    "reason": type(exc).__name__,
                    "detail": str(exc),
                },
            )
            return False

        self.compound_rows["execute"] = execute_row
        self.compound_rows["verify"] = verify_row

        self._compound_emit("execute", execute_row)
        self._compound_emit("verify", verify_row)

        receipt = self.compound_dag.receipt()

        self.engine.emit(
            self.run_id,
            "agent.compound_crystal.completed",
            {
                "lattice_id": self.crystal.crystal_id,
                "stages": list(receipt),
                "stage_count": len(receipt),
                "final_failures": current_failures,
                "proof_digests": {
                    stage: row.get("proof_digest")
                    for stage, row in receipt.items()
                },
            },
        )
        return True

    def _latest_verify(self, state):
        observations = state.get("observations") or ()
        for index in range(len(observations) - 1, -1, -1):
            item = observations[index]
            if not isinstance(item, dict):
                continue
            if item.get("tool_id") != "worktree.verify":
                continue
            result = item.get("result")
            if isinstance(result, dict) and type(result.get("returncode")) is int:
                return index, result
        return None, None

    def _refuse(self, reason, **extra):
        self.done = True
        self.refused = True
        self.engine.emit(self.run_id, "agent.family_crystal.refused", {
            "crystal_id": self.crystal.crystal_id,
            "task_family": self.crystal.task_family,
            "stage": self.stage,
            "reason": reason,
            **extra,
        })

        if self.crystal.component_ids:
            leaf = dict(self.current_lattice_leaf or {})
            self.engine.emit(self.run_id, "agent.family_lattice.refused", {
                "lattice_id": self.crystal.crystal_id,
                "lattice_family": self.crystal.task_family,
                "stage": self.stage,
                "leaf_id": leaf.get("crystal_id"),
                "parent_id": leaf.get("parent_id"),
                "path": list(leaf.get("path") or ()),
                "reason": reason,
                **extra,
            })
        try:
            self.registry.record_negative(
                self.crystal.task_family,
                kind=reason,
                crystal_id=self.crystal.crystal_id,
            )
        except Exception:
            pass
        return None

    def _stage_crystal(self):
        if not self.crystal.component_ids:
            return self.crystal

        try:
            child_id = self.crystal.component_ids[self.stage]
            return self.registry.get(child_id)["crystal_object"]
        except (IndexError, LookupError, ValueError):
            return None

    def _build_plan(self, verify_result):
        """Resolve the current executable leaf, not merely the immediate graph child."""
        import re

        from app.kernel.compute import family_crystals as fc

        families = self._families()
        if not 0 <= self.stage < len(families):
            return None, None

        expected_family = families[self.stage]

        if self.lattice_topology is not None:
            leaves = list(self.lattice_topology.get("leaves") or ())
            if self.stage >= len(leaves):
                return None, None

            leaf = dict(leaves[self.stage])
            if leaf.get("task_family") != expected_family:
                return None, None

            try:
                record = self.registry.get(str(leaf.get("crystal_id") or ""))
            except (LookupError, ValueError):
                return None, None

            if record.get("status") != "promoted":
                return None, None

            child = record["crystal_object"]
        else:
            child = self.crystal

        if child.task_family != expected_family:
            return None, None

        spec = fc.FAMILIES.get(child.task_family)
        if not spec:
            return child, None

        resolver = fc.RESOLVERS.get(spec["resolver"])
        if resolver is None:
            return child, None

        observed = dict(verify_result or {})
        output = self._output(observed)
        observed["output"] = output
        observed["failures"] = self._failures(observed)

        if type(observed.get("tests_run")) is not int:
            match = re.search(r"^Ran (\d+) tests?", output, re.M)
            observed["tests_run"] = int(match.group(1)) if match else 0

        try:
            plan = resolver(
                fc.Context(
                    self.root,
                    self.target,
                    list(self.verify_command),
                    observed,
                )
            )
        except (PermissionError, OSError, ValueError, SyntaxError):
            plan = None

        return child, plan

    def _decisions_from_plan(plan):
        decisions = []

        for edit in plan.get("edits") or ():
            decisions.append(PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.replace_exact",
                arguments={
                    "path": str(edit["path"]),
                    "old_text": str(edit["old_text"]),
                    "new_text": str(edit["new_text"]),
                },
                rationale="Apply deterministic promoted family-crystal edit.",
            ))

        for path, content in sorted(dict(plan.get("rewrite") or {}).items()):
            decisions.append(PlannerDecision(
                decision_type=PlannerDecisionType.TOOL,
                tool_id="worktree.write_file",
                arguments={
                    "path": str(path),
                    "content": str(content),
                },
                rationale="Apply deterministic promoted family-crystal rewrite.",
            ))

        return decisions

    def _prepare_stage(self, state):
        marker, verify_result = self._latest_verify(state)
        if verify_result is None:
            return self._refuse("missing_verifier_evidence")

        child, plan = self._build_plan(verify_result)
        if child is None:
            return self._refuse("missing_lattice_child")

        if child.task_family == "toolchain-regenerate":
            return self._refuse("toolchain_family_not_live_admitted")

        if not plan:
            return self._refuse(
                "resolver_not_applicable",
                child_id=child.crystal_id,
                child_family=child.task_family,
            )

        from app.kernel.compute.direct_coder_compound import (
            CompoundFragmentError,
            compose_fragments,
            fragment_from_legacy_plan,
        )

        try:
            fragment = fragment_from_legacy_plan(
                plan,
                fragment_id=(
                    f"{self.crystal.crystal_id}:stage:{self.stage}:"
                    f"{child.crystal_id}"
                ),
                producer=child.crystal_id,
                provenance_lane=child.task_family,
            )
            compound_plan = compose_fragments([fragment])
        except CompoundFragmentError as exc:
            return self._refuse(
                "compound_fragment_not_admitted",
                child_id=child.crystal_id,
                child_family=child.task_family,
                detail=str(exc),
            )

        fragment_row = fragment.to_dict()
        self.compound_fragments.append({
            "stage": self.stage,
            "fragment": fragment_row,
            "plan_digest": compound_plan["plan_digest"],
            "paths": list(compound_plan["paths"]),
        })

        self.engine.emit(
            self.run_id,
            "agent.compound_crystal.fragment.admitted",
            {
                "lattice_id": self.crystal.crystal_id,
                "stage": self.stage,
                "child_id": child.crystal_id,
                "child_family": child.task_family,
                "fragment_id": fragment.fragment_id,
                "fragment_digest": fragment_row["fragment_digest"],
                "plan_digest": compound_plan["plan_digest"],
                "paths": list(compound_plan["paths"]),
                "provenance_lane": fragment.provenance_lane,
            },
        )

        # Execution remains on the existing governed Direct Coder tool path.
        # The compound layer only validates/composes the mutation plan.
        self.pending = self._decisions_from_plan(
            compound_plan["legacy_plan"]
        )
        if not self.pending:
            return self._refuse(
                "resolver_plan_has_no_live_mutation",
                child_id=child.crystal_id,
                child_family=child.task_family,
            )

        self.current_lattice_leaf = None

        if self.lattice_topology is not None:
            leaves = list(self.lattice_topology.get("leaves") or ())

            if self.stage >= len(leaves):
                return self._refuse(
                    "lattice_stage_out_of_bounds",
                    stage=self.stage,
                    leaf_count=len(leaves),
                )

            leaf = dict(leaves[self.stage])

            # Fail closed if flattened runtime execution has drifted away from
            # the topology admitted during discovery.
            if leaf.get("task_family") != child.task_family:
                return self._refuse(
                    "lattice_execution_binding_mismatch",
                    expected_leaf_id=leaf.get("crystal_id"),
                    expected_family=leaf.get("task_family"),
                    resolved_child_id=child.crystal_id,
                    resolved_family=child.task_family,
                )

            self.current_lattice_leaf = leaf

            self.engine.emit(self.run_id, "agent.family_lattice.stage.started", {
                "lattice_id": self.crystal.crystal_id,
                "lattice_family": self.crystal.task_family,
                "stage": self.stage,
                "leaf_id": leaf.get("crystal_id"),
                "resolved_child_id": child.crystal_id,
                "child_family": child.task_family,
                "parent_id": leaf.get("parent_id"),
                "path": list(leaf.get("path") or ()),
                "depth": leaf.get("depth"),
                "mutations": len(self.pending),
                "failures_before": self.previous_failures,
            })

        self.engine.emit(self.run_id, "agent.family_crystal.stage.started", {
            "crystal_id": self.crystal.crystal_id,
            "task_family": self.crystal.task_family,
            "stage": self.stage,
            "child_id": child.crystal_id,
            "child_family": child.task_family,
            "mutations": len(self.pending),
            "failures_before": self.previous_failures,
        })

        return self.pending.pop(0)

    def next_decision(self, run, state):
        if self.done:
            return None

        if self.pending:
            return self.pending.pop(0)

        if self.waiting_for_verify:
            marker, result = self._latest_verify(state)

            # We have not yet seen the verifier issued for this stage.
            if marker is None or marker == self.last_verify_marker:
                return PlannerDecision(
                    decision_type=PlannerDecisionType.TOOL,
                    tool_id="worktree.verify",
                    arguments={"command": list(self.verify_command)},
                    rationale="Verify deterministic family-crystal mutation.",
                )

            current = self._failures(result)
            final_stage = self.stage == len(self._families()) - 1
            expected = "pass" if final_stage else "improve"

            passed = (
                current == 0
                if final_stage
                else current < self.previous_failures
            )

            self.engine.emit(self.run_id, "agent.family_crystal.stage.verified", {
                "crystal_id": self.crystal.crystal_id,
                "task_family": self.crystal.task_family,
                "stage": self.stage,
                "expect": expected,
                "failures_before": self.previous_failures,
                "failures_after": current,
                "passed": passed,
            })

            if self.lattice_topology is not None:
                leaf = dict(self.current_lattice_leaf or {})

                self.engine.emit(self.run_id, "agent.family_lattice.stage.verified", {
                    "lattice_id": self.crystal.crystal_id,
                    "lattice_family": self.crystal.task_family,
                    "stage": self.stage,
                    "leaf_id": leaf.get("crystal_id"),
                    "parent_id": leaf.get("parent_id"),
                    "path": list(leaf.get("path") or ()),
                    "depth": leaf.get("depth"),
                    "expect": expected,
                    "failures_before": self.previous_failures,
                    "failures_after": current,
                    "failure_delta": current - self.previous_failures,
                    "passed": passed,
                })

            if not passed:
                return self._refuse(
                    "stage_postcondition_failed",
                    failures_before=self.previous_failures,
                    failures_after=current,
                    expected=expected,
                )

            self.previous_failures = current
            self.waiting_for_verify = False

            if final_stage:
                if (
                    self.lattice_topology is not None
                    and not self._finalize_compound_dag(current)
                ):
                    return self._refuse(
                        "compound_dag_postcondition_failed",
                        failures_after=current,
                    )

                self.done = True
                self.succeeded = True
                try:
                    self.registry.record_reuse(
                        self.crystal.crystal_id,
                        run_id=self.run_id,
                        outcome="verified",
                    )
                except Exception:
                    pass

                self.engine.emit(self.run_id, "agent.family_crystal.completed", {
                    "crystal_id": self.crystal.crystal_id,
                    "task_family": self.crystal.task_family,
                    "composite": bool(self.crystal.component_ids),
                    "stages": len(self._families()),
                    "final_failures": current,
                })

                if self.lattice_topology is not None:
                    self.engine.emit(self.run_id, "agent.family_lattice.completed", {
                        "lattice_id": self.crystal.crystal_id,
                        "lattice_family": self.crystal.task_family,
                        "leaf_count": self.lattice_topology.get("leaf_count"),
                        "stages": len(self._families()),
                        "final_failures": current,
                        "verified": current == 0,
                    })
                return PlannerDecision(
                    decision_type=PlannerDecisionType.COMPLETE,
                    summary=(
                        "Promoted family crystal verified successfully"
                        if not self.crystal.component_ids
                        else "Promoted crystal lattice verified successfully"
                    ),
                )

            self.stage += 1
            return self._prepare_stage(state)

        decision = self._prepare_stage(state)
        if decision is None:
            return None

        # Remaining mutations are served before verification.
        return decision

    def mutation_observed(self, state):
        """Mark the stage ready for its verifier after the final emitted edit."""
        if self.done or self.pending:
            return
        marker, _ = self._latest_verify(state)
        self.last_verify_marker = marker
        self.waiting_for_verify = True


class DirectCoderCrystals:
    def __init__(self, engine, extras, env=None):
        self.engine = engine
        self.extras = extras
        self.env = dict(env or {})
        self.budget = RunBudgetTracker(engine.store, engine.emit)
        self.sessions = {}
        self.family_sessions = {}

    @classmethod
    def prepare(cls, engine, run, env):
        from app.kernel.compute.coder_crystal_feedback import trial_enabled
        from app.kernel.compute.coding_crystal_runtime import planner_runtime_extras

        request = run.get("request") or {}
        if not trial_enabled(env) or request.get("crystal_trial_profile") != PROFILE:
            return None
        return cls(engine, planner_runtime_extras(engine.workspace_root, env=env), env=env)

    def _family_discovery(self, run_id, run, state):
        """Discover promoted family/lattice crystals from observed runtime evidence.

        This is nomination only. It never mutates the worktree and never assigns a
        task family from the prompt.
        """
        from pathlib import Path

        from app.kernel.agents.verification_planner import verified_handoff_command
        from app.kernel.compute import family_crystals as fc

        if not fc.family_crystals_enabled(self.env):
            return None

        checkpoint = run.get("checkpoint") or {}
        worktree_text = str(checkpoint.get("worktree_root") or "").strip()
        if not worktree_text:
            return None

        request = dict(run.get("request") or {})
        target = str(request.get("implementation_target") or "").strip()
        if not target:
            return None

        try:
            command = list(verified_handoff_command(dict(run)) or ())
        except ValueError:
            return None
        if not command:
            return None

        latest = None
        for item in reversed(state.get("observations") or ()):
            if not isinstance(item, dict):
                continue
            if item.get("tool_id") != "worktree.verify":
                continue
            result = item.get("result")
            if not isinstance(result, dict):
                continue
            if type(result.get("returncode")) is not int:
                continue
            latest = result
            break
        if latest is None:
            return None

        output = "\n".join(
            str(latest.get(key) or "") for key in ("stdout", "stderr")
        ).strip()
        observed = {
            "returncode": int(latest["returncode"]),
            "output": output,
            "tests_run": 0,
            "failures": fc.failure_count(output, int(latest["returncode"])),
        }

        task = {
            "target": target,
            "verify": command,
        }
        root = Path(worktree_text).resolve()

        ranked = []
        registries = {}
        seen = set()
        for db in fc.family_crystal_db_paths(self.env):
            registry = fc.FamilyRegistry(db)
            try:
                rows = fc.discover(registry, root, task, observed)
            except (OSError, PermissionError, ValueError):
                continue
            for row in rows:
                crystal_id = str(row.get("crystal_id") or "")
                if not crystal_id or crystal_id in seen:
                    continue
                seen.add(crystal_id)
                registries[crystal_id] = registry
                ranked.append(dict(row, storage_path=str(db)))

        ranked.sort(
            key=lambda row: (
                -float(row.get("similarity") or 0.0),
                -int(row.get("expected_failures") or 0),
                str(row.get("crystal_id") or ""),
            )
        )

        summary = [
            {
                "crystal_id": row.get("crystal_id"),
                "task_family": row.get("task_family"),
                "similarity": row.get("similarity"),
                "composite": bool(row.get("composite")),
                "expected_failures": row.get("expected_failures"),
                "resolver_plan": bool((row.get("features") or {}).get("resolver_plan")),
            }
            for row in ranked[:8]
        ]

        self.engine.emit(run_id, "agent.family_crystal.discovery", {
            "candidate_count": len(ranked),
            "observed_failures": observed["failures"],
            "target": target,
            "ranked": summary,
        })

        if not ranked:
            return None

        top = ranked[0]
        features = top.get("features") or {}

        # Live replay remains conservative: similarity nominates, but a deterministic
        # resolver plan and an exact-band match are both required before execution.
        if float(top.get("similarity") or 0.0) < 0.95 or not features.get("resolver_plan"):
            self.engine.emit(run_id, "agent.family_crystal.not_nominated", {
                "crystal_id": top.get("crystal_id"),
                "task_family": top.get("task_family"),
                "similarity": top.get("similarity"),
                "reason": "no_exact_applicable_family_crystal",
            })
            return None

        registry = registries[str(top["crystal_id"])]
        try:
            crystal = registry.get(str(top["crystal_id"]))["crystal_object"]
        except (LookupError, ValueError):
            return None

        nomination = {
            "crystal": crystal,
            "registry": registry,
            "task": task,
            "observed": observed,
            "row": top,
            "root": root,
        }
        self.engine.emit(run_id, "agent.family_crystal.nominated", {
            "crystal_id": crystal.crystal_id,
            "task_family": crystal.task_family,
            "similarity": top.get("similarity"),
            "composite": bool(crystal.component_ids),
            "children": list(crystal.component_ids),
            "component_families": list(crystal.component_families),
            "storage_path": top.get("storage_path"),
        })

        # A promoted composite is also a governed lattice root. Preserve the
        # immediate graph structure for evidence/UI while execution continues
        # through the already-reviewed family-crystal session machinery.
        if crystal.component_ids:
            from app.kernel.compute.family_crystals import lattice_topology

            try:
                topology = lattice_topology(registry, crystal)
            except (LookupError, PermissionError, ValueError) as exc:
                self.engine.emit(run_id, "agent.family_lattice.refused", {
                    "crystal_id": crystal.crystal_id,
                    "task_family": crystal.task_family,
                    "reason": f"topology_invalid:{type(exc).__name__}",
                })
                return None

            nomination["lattice_topology"] = topology

            self.engine.emit(run_id, "agent.family_lattice.selected", {
                "crystal_id": crystal.crystal_id,
                "task_family": crystal.task_family,
                "similarity": top.get("similarity"),
                "leaf_count": topology["leaf_count"],
                "expected_failures": topology["expected_failures"],
            })

            self.engine.emit(run_id, "agent.family_lattice.expanded", {
                "crystal_id": crystal.crystal_id,
                "task_family": crystal.task_family,
                "root": topology["root"],
                "leaves": topology["leaves"],
                "leaf_count": topology["leaf_count"],
                "component_families": topology["component_families"],
            })

        return nomination

    def decision(self, run_id, run, state):
        planner = self.extras.get("crystal_planner")
        router = self.extras.get("adaptive_router")
        if not planner or not router:
            return None
        routed_run = run
        if not state.get("crystal_checked"):
            from app.kernel.compute.coder_crystal_feedback import observed_trial_family

            request = dict(run.get("request") or {})

            # First consult the reviewed multi-family/lattice catalog using the
            # observed baseline. This is nomination-only in this patch; execution
            # remains on the existing native Coder path until the live session
            # adapter is admitted.
            family_nomination = self._family_discovery(run_id, run, state)
            if family_nomination is not None:
                state["family_crystal_nomination"] = {
                    "crystal_id": family_nomination["crystal"].crystal_id,
                    "task_family": family_nomination["crystal"].task_family,
                    "similarity": family_nomination["row"].get("similarity"),
                    "composite": bool(family_nomination["crystal"].component_ids),
                    "children": list(family_nomination["crystal"].component_ids),
                }

                latest_result = None
                for item in reversed(state.get("observations") or ()):
                    if (
                        isinstance(item, dict)
                        and item.get("tool_id") == "worktree.verify"
                        and isinstance(item.get("result"), dict)
                        and type(item["result"].get("returncode")) is int
                    ):
                        latest_result = item["result"]
                        break

                crystal = family_nomination["crystal"]

                live_families = (
                    crystal.component_families
                    if crystal.component_ids
                    else (crystal.task_family,)
                )

                if (
                    latest_result is not None
                    and all(
                        f in DirectCoderFamilySession.LIVE_FAMILIES
                        for f in live_families
                    )
                ):
                    session = DirectCoderFamilySession(
                        crystal,
                        family_nomination["registry"],
                        root=family_nomination["root"],
                        target=family_nomination["task"]["target"],
                        verify_command=family_nomination["task"]["verify"],
                        baseline_result=latest_result,
                        engine=self.engine,
                        run_id=run_id,
                    )
                    self.family_sessions[run_id] = session

                    state["crystal_checked"] = True
                    self.engine.merge_checkpoint(
                        run_id,
                        {"direct_coder": state},
                    )

                    decision = session.next_decision(run, state)
                    if decision is not None:
                        session.mutation_observed(state)
                        return decision

            family = observed_trial_family(request, state.get("observations") or ())
            # Crystal applicability is evidence-driven. Before the canonical
            # baseline and target read exist, Direct Coder performs deterministic
            # preflight instead of guessing a family from the prompt.
            if not family:
                if "baseline_rc" not in state or not state.get("target_inspection_attempted"):
                    return None
                state["crystal_checked"] = True
                self.engine.merge_checkpoint(run_id, {"direct_coder": state})
                route = router.route_run({**run, "request": {**request, "task_family": ""}}).to_dict()
                route["observed_task_family"] = ""
                self.engine.emit(run_id, "agent.route.decision", route)
                return None
            routed_run = {**run, "request": {**request, "task_family": family}}
            state["crystal_checked"] = True
            self.engine.merge_checkpoint(run_id, {"direct_coder": state})
            route = router.route_run(routed_run).to_dict()
            route["observed_task_family"] = family
            self.engine.emit(run_id, "agent.route.decision", route)
            if route.get("route") != "crystal_replay":
                return None
            governor = self.extras.get("governor")
            if governor is not None:
                from app.kernel.governance.governor_spine import Episode, Proposal

                reader = self.extras.get("memory_reader")
                memory = reader.read({"crystal_id": route["crystal_id"], "run_id": run_id}) if reader else None
                verdict = governor.admit(Episode(run_id=run_id), Proposal(
                    kind="crystal", crystal_id=str(route["crystal_id"]), route_decision=route, memory=memory))
                self.engine.emit(run_id, "agent.governor.decision", {
                    "outcome": verdict.outcome, "receipt_id": verdict.receipt_id, "crystal_id": route["crystal_id"],
                })
                if not verdict.permits():
                    return None
            self.sessions[run_id] = planner.activate(
                routed_run, run_id, engine=self.engine, nominated_crystal_id=str(route["crystal_id"]))
        family_session = self.family_sessions.get(run_id)
        if family_session is not None:
            try:
                decision = family_session.next_decision(run, state)
                if decision is not None and decision.tool_id in {
                    "worktree.replace_exact", "worktree.write_file"
                }:
                    family_session.mutation_observed(state)
                if family_session.done:
                    self.family_sessions.pop(run_id, None)
                if decision is not None:
                    return decision
            except Exception as exc:
                family_session._refuse(
                    f"session_error:{type(exc).__name__}"
                )
                self.family_sessions.pop(run_id, None)

        session = self.sessions.get(run_id)
        if session is None:
            return None
        try:
            return session.next_decision(run, SimpleNamespace(
                observations=episode_observations(self.engine.store, run_id)))
        except Exception as exc:
            session.abort(f"session_error:{type(exc).__name__}")
            return None
    async def complete(self, run_id, objective, verified):
        if not verified or self.extras.get("envelope_store") is None:
            return
        self.budget.mark_wall(run_id)
        envelope = EpisodeEnvelopeBuilder().build(self.engine.store, run_id)
        self.extras["envelope_store"].put(envelope)
        self.engine.emit(run_id, "agent.episode.sealed", {
            "envelope_digest": envelope.envelope_digest, "task_family": envelope.task_family,
            "verification": dict(envelope.verification), "budget": dict(envelope.budget), "stored": True,
        })
        session = self.sessions.pop(run_id, None)
        if session is not None and session.succeeded:
            accounted = session.planner.on_reuse_sealed(session, envelope)
            if accounted:
                receipt = accounted.get("receipt") or {}
                self.engine.emit(run_id, "agent.crystal.reduction_receipt", {
                    "receipt_id": receipt.get("receipt_id"), "crystal_id": session.candidate.crystal_id})
        from app.kernel.agents.coder_integrations import CoderIntegrationCoordinator

        result = await asyncio.to_thread(
            CoderIntegrationCoordinator(self.engine.workspace_root).complete,
            run_id=run_id, objective=objective, verified=True)
        for event in result["events"]:
            self.engine.emit(run_id, event["event_type"], event["payload"])
