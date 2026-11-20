"""Bind the native crystal lifecycle to the Direct Coder engine."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.kernel.compute.coder_crystal_feedback import PROFILE
from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeBuilder, RunBudgetTracker, episode_observations


class DirectCoderCrystals:
    def __init__(self, engine, extras):
        self.engine = engine
        self.extras = extras
        self.budget = RunBudgetTracker(engine.store, engine.emit)
        self.sessions = {}

    @classmethod
    def prepare(cls, engine, run, env):
        from app.kernel.compute.coder_crystal_feedback import trial_enabled
        from app.kernel.compute.coding_crystal_runtime import planner_runtime_extras

        request = run.get("request") or {}
        if not trial_enabled(env) or request.get("crystal_trial_profile") != PROFILE:
            return None
        return cls(engine, planner_runtime_extras(engine.workspace_root, env=env))

    def decision(self, run_id, run, state):
        planner = self.extras.get("crystal_planner")
        router = self.extras.get("adaptive_router")
        if not planner or not router:
            return None
        routed_run = run
        if not state.get("crystal_checked"):
            from app.kernel.compute.coder_crystal_feedback import observed_trial_family

            request = dict(run.get("request") or {})
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
