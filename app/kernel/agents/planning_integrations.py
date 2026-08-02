"""Planning integrations that enrich governed AgentRuns without granting authority."""

from __future__ import annotations

from typing import Any

from app.kernel.operations_console.objective_plan import ObjectivePlanWorkspace


class PlanningIntegrationRuntime:
    """Durable record-only planning helpers for AgentRuns."""

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = workspace_root
        self.objective_plan = ObjectivePlanWorkspace(workspace_root)

    @staticmethod
    def _is_mutating_mode(run: dict[str, Any]) -> bool:
        return str(run.get("mode") or "").strip().lower() in {"agent", "edit", "implementer"}

    @staticmethod
    def _context_files(run: dict[str, Any]) -> list[str]:
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        raw = request.get("context_files") if isinstance(request.get("context_files"), list) else []
        files: list[str] = []
        for item in raw:
            path = str(item or "").strip()
            if path and path not in files:
                files.append(path)
        return files[:8]

    @classmethod
    def _scope_signals(cls, run: dict[str, Any]) -> dict[str, Any]:
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        objective = str(run.get("objective") or "").lower()
        files = cls._context_files(run)
        broad_terms = ("large repo", "large-repo", "multi-turn", "architecture", "architectural", "ambiguous", "monorepo", "cross-cutting", "many files", "dependencies")
        explicit = bool(request.get("long_horizon") or request.get("architecture_planning") or request.get("monorepo"))
        broad = explicit or len(files) > 3 or any(term in objective for term in broad_terms)
        return {
            "broad": broad,
            "explicit": explicit,
            "context_file_count": len(files),
            "risk": str(request.get("risk") or request.get("risk_level") or ""),
            "package_roots": request.get("package_roots") if isinstance(request.get("package_roots"), list) else [],
            "test_strategy": request.get("test_strategy") if isinstance(request.get("test_strategy"), dict) else {},
        }

    @classmethod
    def _success_criteria(cls, run: dict[str, Any]) -> list[str]:
        request = run.get("request") if isinstance(run.get("request"), dict) else {}
        existing = request.get("success_criteria") if isinstance(request.get("success_criteria"), list) else []
        criteria = [str(item or "").strip() for item in existing if str(item or "").strip()]
        files = cls._context_files(run)
        if files:
            criteria.append(f"Planned file set stays bounded to declared context: {', '.join(files[:4])}")
        criteria.append("Bounded verification passes for the latest mutation epoch")
        criteria.append("Verified worktree diff is materialized into SourcePlan handoff evidence")
        seen: set[str] = set()
        deduped: list[str] = []
        for item in criteria:
            if item not in seen:
                deduped.append(item)
                seen.add(item)
        return deduped

    @classmethod
    def _phase1_steps(cls, run: dict[str, Any]) -> list[dict[str, Any]]:
        files = cls._context_files(run)
        signals = cls._scope_signals(run)
        inspect_title = "Inspect workspace scope"
        if files:
            inspect_title = f"Inspect declared file scope: {', '.join(files[:2])}"
        if signals["broad"]:
            telemetry = {"planning_mode": "long_horizon", "scope_signals": signals}
            return [
                {"step_id": "inspect", "title": inspect_title, "status": "active", "telemetry": telemetry, "success_criteria": ["Workspace index and relevant source ranges are observed before mutation"]},
                {"step_id": "architecture", "title": "Map architecture, ownership boundaries, and risky dependency edges", "telemetry": telemetry, "success_criteria": ["Changed components and dependency edges are identified"]},
                {"step_id": "test-map", "title": "Build package-aware verification strategy before edits", "telemetry": telemetry, "success_criteria": ["Focused and fallback verification commands are selected"]},
                {"step_id": "bind", "title": "Bind isolated worktree for governed mutation", "telemetry": telemetry},
                {"step_id": "mutate", "title": "Apply bounded edits in dependency-aware waves", "telemetry": telemetry, "success_criteria": ["Each mutation wave stays bounded and reviewable"]},
                {"step_id": "verify", "title": "Run focused then fallback verification for latest mutation epoch", "telemetry": telemetry},
                {"step_id": "repair", "title": "Classify failures and repair only the smallest failed slice", "telemetry": telemetry},
                {"step_id": "handoff", "title": "Prepare SourcePlan handoff from verified worktree diff", "telemetry": telemetry},
            ]
        return [
            {"step_id": "inspect", "title": inspect_title, "status": "active"},
            {"step_id": "bind", "title": "Bind isolated worktree for governed mutation"},
            {"step_id": "mutate", "title": "Apply bounded file edits across planned scope"},
            {"step_id": "verify", "title": "Run bounded verification for the latest mutation epoch"},
            {"step_id": "handoff", "title": "Prepare SourcePlan handoff from verified worktree diff"},
        ]

    def ensure_phase1_plan(self, run_id: str, run: dict[str, Any]) -> dict[str, Any] | None:
        if not self._is_mutating_mode(run):
            return None
        current = self.objective_plan.current(run_id)
        if current.get("revision_id"):
            return None
        objective = str(run.get("objective") or "").strip() or "Governed implementation task"
        receipt = self.objective_plan.revise(
            run_id,
            objective=objective,
            success_criteria=self._success_criteria(run),
            steps=self._phase1_steps(run),
            active_step_id="inspect",
            operator_id="beast.phase1",
            reason="phase1_multi_file_execution_planning_seed",
            expansion_confirmed=False,
        )
        self.objective_plan.engine.emit(run_id, "agent.plan.integration.seeded", {
            "integration_id": "phase1_multi_file_execution_planning",
            "plan_version": receipt.get("plan_version"),
            "active_step_id": "inspect",
            "step_count": len((receipt.get("plan") or {}).get("steps") or []),
        })
        return receipt

    def current_plan_brief(self, run_id: str) -> dict[str, Any]:
        current = self.objective_plan.current(run_id)
        plan = current.get("plan") if isinstance(current.get("plan"), dict) else {}
        steps = [step for step in (plan.get("steps") if isinstance(plan.get("steps"), list) else []) if isinstance(step, dict)]
        active = str(plan.get("active_step_id") or "")
        return {
            "mode": next((str((step.get("telemetry") or {}).get("planning_mode") or "") for step in steps if isinstance(step.get("telemetry"), dict) and (step.get("telemetry") or {}).get("planning_mode")), "standard"),
            "active_step_id": active,
            "steps": [
                {
                    "step_id": str(step.get("step_id") or ""),
                    "status": str(step.get("status") or ""),
                    "title": str(step.get("title") or "")[:120],
                    "success_criteria": (step.get("success_criteria") if isinstance(step.get("success_criteria"), list) else [])[:3],
                }
                for step in steps[:10]
            ],
        }

    def sync_phase5_resume(self, run_id: str, run: dict[str, Any]) -> dict[str, Any] | None:
        current = self.objective_plan.current(run_id)
        if not current.get("revision_id"):
            return None
        plan = current.get("plan") if isinstance(current.get("plan"), dict) else {}
        steps = [dict(step) for step in (plan.get("steps") if isinstance(plan.get("steps"), list) else [])]
        if not steps:
            return None
        events = self.objective_plan.engine.store.events(run_id, after=0, limit=512)
        latest_resume = next(
            (event for event in reversed(events) if str(event.get("event_type") or "") == "agent.run.resumed"),
            None,
        )
        if latest_resume is None:
            return None
        latest_integration = next(
            (event for event in reversed(events) if str(event.get("event_type") or "") == "agent.plan.integration.resumed"),
            None,
        )
        if latest_integration and int(latest_integration.get("sequence") or 0) > int(latest_resume.get("sequence") or 0):
            return None
        active_step_id = str(plan.get("active_step_id") or "")
        if not active_step_id:
            active_step_id = next((str(step.get("step_id") or "") for step in steps if step.get("status") == "active"), "")
        if not active_step_id:
            return None
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        planner = checkpoint.get("planner") if isinstance(checkpoint.get("planner"), dict) else {}
        latest_failure = None
        failures = planner.get("verification_failures") if isinstance(planner.get("verification_failures"), list) else []
        if failures:
            tail = failures[-1]
            latest_failure = tail if isinstance(tail, dict) else None
        approval_resume = checkpoint.get("approval_resume") if isinstance(checkpoint.get("approval_resume"), dict) else {}
        updated = False
        for step in steps:
            if str(step.get("step_id") or "") != active_step_id:
                continue
            telemetry = dict(step.get("telemetry") or {})
            continuity = dict(telemetry.get("continuity") or {})
            failure_analysis = latest_failure.get("analysis") if isinstance(latest_failure, dict) and isinstance(latest_failure.get("analysis"), dict) else {}
            target_paths = latest_failure.get("target_paths") if isinstance(latest_failure, dict) and isinstance(latest_failure.get("target_paths"), list) else []
            continuity.update({
                "resume_sequence": int(latest_resume.get("sequence") or 0),
                "resumed_at": float(latest_resume.get("created_at") or 0.0),
                "resumed_from_state": str((latest_resume.get("payload") or {}).get("from_state") or ""),
                "resumed_turn": int(planner.get("turn") or 0),
                "resume_observation_count": len(planner.get("observations") if isinstance(planner.get("observations"), list) else []),
                "resume_repair_cycles": int(planner.get("repair_cycles") or 0),
                "resume_pending_repair": bool(latest_failure),
                "resume_failure_class": str(failure_analysis.get("failure_class") or ""),
                "resume_missing_symbol": str(failure_analysis.get("missing_symbol") or ""),
                "resume_target_paths": [str(path) for path in target_paths[:4]],
                "resume_execution_target": str(latest_failure.get("execution_target") or ""),
                "resume_target_execution": str(latest_failure.get("target_execution") or ""),
                "resume_transport": str(latest_failure.get("transport") or ""),
                "resume_verifier_command": [str(item) for item in (latest_failure.get("command") or [])[:12]],
                "resume_step_id": str(approval_resume.get("step_id") or active_step_id),
                "resume_state": str(approval_resume.get("resume_state") or ""),
            })
            continuity["resume_count"] = int(continuity.get("resume_count") or 0) + 1
            if latest_failure:
                continuity["resume_status"] = "repair_pending"
            elif approval_resume:
                continuity["resume_status"] = "approval_resumed"
            else:
                continuity["resume_status"] = "planner_resumed"
            telemetry["continuity"] = continuity
            step["telemetry"] = telemetry
            updated = True
            break
        if not updated:
            return None
        receipt = self.objective_plan.revise(
            run_id,
            objective=str(current.get("objective") or ""),
            success_criteria=current.get("success_criteria") or [],
            steps=steps,
            active_step_id=active_step_id,
            operator_id="beast.phase5",
            reason="phase5_resume_continuity_recorded",
            expansion_confirmed=False,
        )
        self.objective_plan.engine.emit(run_id, "agent.plan.integration.resumed", {
            "integration_id": "phase5_resume_continuity",
            "plan_version": receipt.get("plan_version"),
            "active_step_id": active_step_id,
            "resume_sequence": int(latest_resume.get("sequence") or 0),
            "resume_repair_cycles": int(planner.get("repair_cycles") or 0),
        })
        return receipt

    def sync_phase6_approval(self, run_id: str, event_type: str, payload: dict[str, Any], run: dict[str, Any] | None = None) -> dict[str, Any] | None:
        current = self.objective_plan.current(run_id)
        if not current.get("revision_id"):
            return None
        plan = current.get("plan") if isinstance(current.get("plan"), dict) else {}
        steps = [dict(step) for step in (plan.get("steps") if isinstance(plan.get("steps"), list) else [])]
        if not steps:
            return None
        active_step_id = str(plan.get("active_step_id") or "")
        step_id = str(payload.get("step_id") or active_step_id or "").strip()
        if not step_id:
            return None
        updated = False
        next_active_step_id = active_step_id
        if not run:
            run = self.objective_plan.engine.store.get_run(run_id) or {}
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        approval_resume = checkpoint.get("approval_resume") if isinstance(checkpoint.get("approval_resume"), dict) else {}
        for step in steps:
            if str(step.get("step_id") or "") != step_id:
                continue
            telemetry = dict(step.get("telemetry") or {})
            approval = dict(telemetry.get("approval") or {})
            approval_history = list(approval.get("history") or [])
            entry = {
                "event_type": str(event_type or ""),
                "approval_id": str(payload.get("approval_id") or approval_resume.get("approval_id") or ""),
                "tool_id": str(payload.get("tool_id") or approval_resume.get("tool_id") or ""),
                "step_id": step_id,
                "status": "",
            }
            if event_type == "agent.approval.requested":
                entry["status"] = "waiting_for_approval"
                step["status"] = "blocked"
                step["blocked_reason"] = f"Awaiting operator approval for {entry['tool_id'] or 'governed tool'}"
                next_active_step_id = step_id
            elif event_type == "agent.approval.capability_consumed":
                entry["status"] = "exact_step_resumed"
                if step.get("status") == "blocked":
                    step["status"] = "active"
                step["blocked_reason"] = ""
                next_active_step_id = step_id
            else:
                return None
            if approval_history and approval_history[-1] == entry:
                return None
            approval_history.append(entry)
            approval["history"] = approval_history[-6:]
            approval["approval_id"] = entry["approval_id"]
            approval["tool_id"] = entry["tool_id"]
            approval["step_id"] = step_id
            approval["status"] = entry["status"]
            if payload.get("request_digest"):
                approval["request_digest"] = str(payload.get("request_digest"))
            if event_type == "agent.approval.capability_consumed":
                approval["resume_state"] = str(payload.get("resume_state") or approval_resume.get("status") or "")
            step["telemetry"] = {**telemetry, "approval": approval}
            updated = True
            break
        if not updated:
            return None
        receipt = self.objective_plan.revise(
            run_id,
            objective=str(current.get("objective") or ""),
            success_criteria=current.get("success_criteria") or [],
            steps=steps,
            active_step_id=next_active_step_id,
            operator_id="beast.phase6",
            reason=f"phase6_approval_{event_type.rsplit('.', 1)[-1]}",
            expansion_confirmed=False,
        )
        self.objective_plan.engine.emit(run_id, "agent.plan.integration.approval", {
            "integration_id": "phase6_approval_pause_resume",
            "plan_version": receipt.get("plan_version"),
            "active_step_id": next_active_step_id,
            "step_id": step_id,
            "event_type": event_type,
            "approval_status": entry["status"],
            "approval_id": entry["approval_id"],
            "tool_id": entry["tool_id"],
        })
        return receipt

    def sync_phase7_handoff(self, run_id: str, event_type: str, payload: dict[str, Any], run: dict[str, Any] | None = None) -> dict[str, Any] | None:
        current = self.objective_plan.current(run_id)
        if not current.get("revision_id"):
            return None
        plan = current.get("plan") if isinstance(current.get("plan"), dict) else {}
        steps = [dict(step) for step in (plan.get("steps") if isinstance(plan.get("steps"), list) else [])]
        if not steps:
            return None
        handoff = next((step for step in steps if str(step.get("step_id") or "") == "handoff"), None)
        if handoff is None:
            return None
        if run is None:
            run = self.objective_plan.engine.store.get_run(run_id) or {}
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        sourceplan = checkpoint.get("sourceplan") if isinstance(checkpoint.get("sourceplan"), dict) else {}
        promotion = checkpoint.get("promotion") if isinstance(checkpoint.get("promotion"), dict) else {}
        commit_candidate = checkpoint.get("commit_candidate") if isinstance(checkpoint.get("commit_candidate"), dict) else {}
        telemetry = dict(handoff.get("telemetry") or {})
        handoff_state = dict(telemetry.get("handoff") or {})
        promotion_state = dict(telemetry.get("promotion") or {})
        updated = False
        active_step_id = str(plan.get("active_step_id") or "")
        if event_type == "agent.sourceplan.ready":
            handoff_state.update({
                "status": "sourceplan_ready",
                "plan_id": str(payload.get("plan_id") or sourceplan.get("plan_id") or ""),
                "worktree_task_id": str(payload.get("worktree_task_id") or sourceplan.get("worktree_task_id") or ""),
                "file_count": len(payload.get("files") or []),
                "requires_operator_translation": bool(payload.get("requires_operator_translation") if "requires_operator_translation" in payload else sourceplan.get("requires_operator_translation")),
            })
            handoff["status"] = "completed"
            handoff["blocked_reason"] = ""
            if active_step_id == "handoff":
                active_step_id = ""
            updated = True
        elif event_type == "agent.promotion.evaluated":
            failed_policies = payload.get("failed_policies") if isinstance(payload.get("failed_policies"), list) else []
            promotion_state.update({
                "status": "eligible" if bool(payload.get("eligible")) else "blocked",
                "receipt_id": str(payload.get("receipt_id") or promotion.get("receipt_id") or ""),
                "receipt_digest": str(payload.get("receipt_digest") or promotion.get("receipt_digest") or ""),
                "approval_id": str(payload.get("approval_id") or promotion.get("approval_id") or ""),
                "failed_policies": [str(item) for item in failed_policies[:8]],
            })
            updated = True
        elif event_type == "agent.promotion.committed":
            promotion_state.update({
                "status": "committed",
                "candidate_id": str(payload.get("candidate_id") or commit_candidate.get("candidate_id") or ""),
                "approval_id": str(payload.get("approval_id") or commit_candidate.get("approval_id") or ""),
                "commit": str(payload.get("commit") or commit_candidate.get("commit") or ""),
            })
            updated = True
        else:
            return None
        if not updated:
            return None
        handoff["telemetry"] = {**telemetry, "handoff": handoff_state, "promotion": promotion_state}
        receipt = self.objective_plan.revise(
            run_id,
            objective=str(current.get("objective") or ""),
            success_criteria=current.get("success_criteria") or [],
            steps=steps,
            active_step_id=active_step_id,
            operator_id="beast.phase7",
            reason=f"phase7_handoff_{event_type.rsplit('.', 1)[-1]}",
            expansion_confirmed=False,
        )
        self.objective_plan.engine.emit(run_id, "agent.plan.integration.handoff", {
            "integration_id": "phase7_handoff_promotion",
            "plan_version": receipt.get("plan_version"),
            "active_step_id": active_step_id,
            "event_type": event_type,
            "plan_id": handoff_state.get("plan_id", ""),
            "promotion_status": promotion_state.get("status", ""),
        })
        return receipt

    def sync_phase1_progress(self, run_id: str, observation: dict[str, Any]) -> dict[str, Any] | None:
        current = self.objective_plan.current(run_id)
        if not current.get("revision_id"):
            return None
        plan = current.get("plan") if isinstance(current.get("plan"), dict) else {}
        steps = [dict(step) for step in (plan.get("steps") if isinstance(plan.get("steps"), list) else [])]
        step_ids = [str(step.get("step_id") or "") for step in steps]
        required = {"inspect", "bind", "mutate", "verify", "handoff"}
        if not required.issubset(set(step_ids)):
            return None
        tool_id = str(observation.get("tool_id") or "")
        status = str(observation.get("status") or "")
        transition: tuple[str, str, str] | None = None
        if tool_id in {"workspace.index", "workspace.list", "workspace.search_text", "workspace.read_range"} and status == "completed":
            transition = ("inspect", "bind", "phase1_progress_workspace_inspected")
        elif tool_id == "worktree.bind" and status == "completed":
            transition = ("bind", "mutate", "phase1_progress_worktree_bound")
        elif tool_id in {"worktree.replace_exact", "worktree.write_file"} and status == "completed":
            transition = ("mutate", "verify", "phase1_progress_mutation_applied")
        elif tool_id == "worktree.verify" and status == "completed":
            transition = ("verify", "handoff", "phase1_progress_verification_passed")
        elif tool_id == "worktree.verify" and status != "completed":
            transition = ("verify", "mutate", "phase1_progress_verification_failed_requires_repair")
        elif tool_id == "worktree.sourceplan_draft" and status == "completed":
            transition = ("handoff", "", "phase1_progress_handoff_ready")
        if transition is None:
            return None
        completed_step, next_step, reason = transition
        updated = False
        for step in steps:
            if step["step_id"] == completed_step:
                step["status"] = "completed" if next_step != "mutate" or tool_id != "worktree.verify" or status == "completed" else "completed"
                updated = True
            elif tool_id in {"workspace.index", "workspace.list", "workspace.search_text", "workspace.read_range"} and status == "completed" and step["step_id"] in {"architecture", "test-map"}:
                step["status"] = "completed"
                telemetry = dict(step.get("telemetry") or {})
                telemetry["evidence"] = {
                    "tool_id": tool_id,
                    "status": "completed",
                    "reason": "read_only_workspace_evidence_collected",
                }
                step["telemetry"] = telemetry
                updated = True
            elif next_step and step["step_id"] == next_step:
                step["status"] = "active"
                updated = True
            elif step["status"] == "active" and step["step_id"] != next_step:
                step["status"] = "pending"
                updated = True
        if tool_id == "worktree.verify" and status != "completed":
            result = observation.get("result") if isinstance(observation.get("result"), dict) else {}
            analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
            target_paths = result.get("target_paths") if isinstance(result.get("target_paths"), list) else []
            failure_class = str(analysis.get("failure_class") or "unknown")
            missing_symbol = str(analysis.get("missing_symbol") or "").strip()
            target_summary = ", ".join(str(path) for path in target_paths[:2]) if target_paths else "latest mutation scope"
            mutate_title = f"Repair {failure_class} failure in {target_summary}"
            if missing_symbol:
                mutate_title += f" for {missing_symbol}"
            for step in steps:
                if step["step_id"] == "verify":
                    step["status"] = "blocked"
                    step["blocked_reason"] = str(observation.get("error") or "verification failed")
                elif step["step_id"] == "mutate":
                    step["status"] = "active"
                    step["title"] = mutate_title
                    criteria = step.get("success_criteria") if isinstance(step.get("success_criteria"), list) else []
                    criteria = [str(item) for item in criteria if str(item).strip()]
                    criteria.append(f"Repair only the verifier-declared residual for {target_summary}")
                    if missing_symbol:
                        criteria.append(f"Preserve and resolve missing symbol boundary: {missing_symbol}")
                    step["success_criteria"] = list(dict.fromkeys(criteria))
        if tool_id in {"worktree.replace_exact", "worktree.write_file"} and status == "completed":
            for step in steps:
                if step["step_id"] == "verify":
                    step["blocked_reason"] = ""
                elif step["step_id"] == "mutate" and step["status"] != "completed":
                    step["title"] = "Apply bounded file edits across planned scope"
                    step["success_criteria"] = []
        if tool_id == "worktree.sourceplan_draft" and status == "completed":
            for step in steps:
                if step["step_id"] == "handoff":
                    step["status"] = "completed"
        if not updated:
            return None
        active_step_id = next((step["step_id"] for step in steps if step["status"] == "active"), "")
        receipt = self.objective_plan.revise(
            run_id,
            objective=str(current.get("objective") or ""),
            success_criteria=current.get("success_criteria") or [],
            steps=steps,
            active_step_id=active_step_id,
            operator_id="beast.phase1",
            reason=reason,
            expansion_confirmed=False,
        )
        self.objective_plan.engine.emit(run_id, "agent.plan.integration.progressed", {
            "integration_id": "phase1_multi_file_execution_planning",
            "plan_version": receipt.get("plan_version"),
            "active_step_id": active_step_id,
            "tool_id": tool_id,
            "tool_status": status,
            "reason": reason,
        })
        return receipt

    @staticmethod
    def _telemetry_step_id(tool_id: str, active_step_id: str) -> str:
        if tool_id in {"workspace.index", "workspace.list", "workspace.search_text", "workspace.read_range"}:
            return "inspect"
        if tool_id == "worktree.bind":
            return "bind"
        if tool_id in {"worktree.replace_exact", "worktree.write_file"}:
            return "mutate"
        if tool_id == "worktree.verify":
            return "verify"
        if tool_id == "worktree.sourceplan_draft":
            return "handoff"
        return active_step_id

    def sync_phase3_telemetry(self, run_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        current = self.objective_plan.current(run_id)
        if not current.get("revision_id"):
            return None
        plan = current.get("plan") if isinstance(current.get("plan"), dict) else {}
        steps = [dict(step) for step in (plan.get("steps") if isinstance(plan.get("steps"), list) else [])]
        if not steps:
            return None
        active_step_id = str(plan.get("active_step_id") or "")
        target_step_id = active_step_id
        if event_type == "agent.plan.telemetry.observation":
            target_step_id = self._telemetry_step_id(str(payload.get("tool_id") or ""), active_step_id)
        updated = False
        for step in steps:
            if step["step_id"] != target_step_id:
                continue
            telemetry = dict(step.get("telemetry") or {})
            if event_type == "agent.planner.turn.started":
                telemetry["planner_turns"] = int(telemetry.get("planner_turns") or 0) + 1
                telemetry["last_turn"] = int(payload.get("turn") or 0)
            elif event_type == "agent.model.usage":
                telemetry["model_turns"] = int(telemetry.get("model_turns") or 0) + 1
                latency = payload.get("latency_ms")
                if isinstance(latency, (int, float)):
                    telemetry["model_latency_ms"] = round(float(telemetry.get("model_latency_ms") or 0.0) + float(latency), 3)
                    telemetry["last_model_latency_ms"] = round(float(latency), 3)
                telemetry["prompt_chars"] = int(telemetry.get("prompt_chars") or 0) + int(payload.get("prompt_chars") or 0)
                telemetry["completion_chars"] = int(telemetry.get("completion_chars") or 0) + int(payload.get("completion_chars") or 0)
                if payload.get("model"):
                    telemetry["model"] = str(payload.get("model"))
            elif event_type == "agent.plan.telemetry.observation":
                telemetry["tool_calls"] = int(telemetry.get("tool_calls") or 0) + 1
                duration = payload.get("duration_ms")
                if isinstance(duration, (int, float)):
                    telemetry["tool_latency_ms"] = round(float(telemetry.get("tool_latency_ms") or 0.0) + float(duration), 3)
                    telemetry["last_tool_latency_ms"] = round(float(duration), 3)
                telemetry["last_tool_id"] = str(payload.get("tool_id") or "")
                telemetry["last_tool_status"] = str(payload.get("status") or "")
                if str(payload.get("tool_id") or "") == "worktree.verify" and isinstance(duration, (int, float)):
                    telemetry["verification_latency_ms"] = round(float(duration), 3)
            else:
                return None
            step["telemetry"] = telemetry
            updated = True
            break
        if not updated:
            return None
        receipt = self.objective_plan.revise(
            run_id,
            objective=str(current.get("objective") or ""),
            success_criteria=current.get("success_criteria") or [],
            steps=steps,
            active_step_id=active_step_id,
            operator_id="beast.phase3",
            reason=f"phase3_latency_telemetry_{event_type.rsplit('.', 1)[-1]}",
            expansion_confirmed=False,
        )
        self.objective_plan.engine.emit(run_id, "agent.plan.integration.telemetry", {
            "integration_id": "phase3_latency_observability",
            "plan_version": receipt.get("plan_version"),
            "active_step_id": active_step_id,
            "event_type": event_type,
            "step_id": target_step_id,
        })
        return receipt

    def sync_phase4_route(self, run_id: str, route: dict[str, Any]) -> dict[str, Any] | None:
        current = self.objective_plan.current(run_id)
        if not current.get("revision_id"):
            return None
        plan = current.get("plan") if isinstance(current.get("plan"), dict) else {}
        steps = [dict(step) for step in (plan.get("steps") if isinstance(plan.get("steps"), list) else [])]
        active_step_id = str(plan.get("active_step_id") or "")
        if not active_step_id:
            return None
        updated = False
        for step in steps:
            if step["step_id"] != active_step_id:
                continue
            telemetry = dict(step.get("telemetry") or {})
            route_history = list(telemetry.get("route_history") or [])
            entry = {
                "provider": str(route.get("provider") or ""),
                "engine": str(route.get("engine") or ""),
                "route_kind": str(route.get("route_kind") or ""),
                "reason": str(route.get("reason") or ""),
                "turn": int(route.get("turn") or 0),
            }
            if route_history and route_history[-1] == entry:
                return None
            route_history.append(entry)
            telemetry["route_history"] = route_history[-6:]
            telemetry["route_provider"] = entry["provider"]
            telemetry["route_engine"] = entry["engine"]
            telemetry["route_kind"] = entry["route_kind"]
            telemetry["route_reason"] = entry["reason"]
            telemetry["route_turn"] = entry["turn"]
            step["telemetry"] = telemetry
            updated = True
            break
        if not updated:
            return None
        receipt = self.objective_plan.revise(
            run_id,
            objective=str(current.get("objective") or ""),
            success_criteria=current.get("success_criteria") or [],
            steps=steps,
            active_step_id=active_step_id,
            operator_id="beast.phase4",
            reason="phase4_model_routing_recorded",
            expansion_confirmed=False,
        )
        self.objective_plan.engine.emit(run_id, "agent.plan.integration.routing", {
            "integration_id": "phase4_model_routing",
            "plan_version": receipt.get("plan_version"),
            "active_step_id": active_step_id,
            "route_provider": str(route.get("provider") or ""),
            "route_engine": str(route.get("engine") or ""),
            "route_kind": str(route.get("route_kind") or ""),
        })
        return receipt
