"""Bind the native crystal lifecycle to the Direct Coder engine."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.kernel.compute.coder_crystal_feedback import PROFILE
from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeBuilder, RunBudgetTracker, episode_observations


class DirectCoderCrystals:
    def __init__(self, engine, extras, env=None):
        self.engine = engine
        self.extras = extras
        self.env = dict(env or {})
        self.budget = RunBudgetTracker(engine.store, engine.emit)
        self.sessions = {}

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
