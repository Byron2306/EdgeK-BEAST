"""Additional BEAST-layer coding fixtures for the xAI omni-gauntlet."""

from __future__ import annotations

from typing import Dict, List

from benchmarks.beast_systems_benchmark import SuiteTask, suite_tasks


def _task(
    name: str,
    objective: str,
    module: str,
    broken: str,
    fixed: str,
    public_tests: str,
    hidden_tests: str,
    assertions: List[str],
) -> SuiteTask:
    path = f"app/{module}.py"
    return SuiteTask(
        name=name,
        objective=objective,
        files={path: broken},
        tests={f"tests/test_{module}_public.py": public_tests},
        hidden_tests={f"tests/test_{module}_hidden.py": hidden_tests},
        relevant_files=[path, f"tests/test_{module}_public.py"],
        allowed_edit_paths=[path],
        fixed_files={path: fixed},
        failing_assertions=assertions,
    )


def additional_tasks() -> List[SuiteTask]:
    tasks: List[SuiteTask] = []

    tasks.append(_task(
        "stale_file_hash_rejection", "Reject stale Action IR file references while accepting the current digest.", "hash_guard",
        '''import hashlib\n\ndef validate_ref(content, declared):\n    return True\n''',
        '''import hashlib\n\ndef validate_ref(content, declared):\n    actual = hashlib.sha256(content.encode("utf-8")).hexdigest()\n    return bool(declared) and declared.removeprefix("sha256:") == actual\n''',
        '''import hashlib\nfrom app.hash_guard import validate_ref\n\ndef test_current_hash_is_accepted():\n    text = "current source"\n    digest = hashlib.sha256(text.encode()).hexdigest()\n    assert validate_ref(text, "sha256:" + digest)\n\ndef test_stale_hash_is_rejected():\n    assert not validate_ref("new", "sha256:" + hashlib.sha256(b"old").hexdigest())\n''',
        '''from app.hash_guard import validate_ref\n\ndef test_hidden_empty_and_malformed_hashes_fail_closed():\n    assert not validate_ref("source", "")\n    assert not validate_ref("source", "sha256:not-a-real-digest")\n''',
        ["current hash accepted", "stale and malformed hashes rejected"],
    ))

    tasks.append(_task(
        "session_latency_budget_clamp", "Clamp BEAST preflight and scout budgets so optional work cannot overrun preflight.", "session_budget",
        '''def budgets(preflight_ms, scout_ms):\n    return {"preflight_ms": preflight_ms, "scout_ms": scout_ms}\n''',
        '''def budgets(preflight_ms, scout_ms):\n    preflight = max(25, min(int(preflight_ms), 30000))\n    scout = max(0, min(int(scout_ms), preflight))\n    return {"preflight_ms": preflight, "scout_ms": scout}\n''',
        '''from app.session_budget import budgets\n\ndef test_scout_never_exceeds_preflight():\n    assert budgets(500, 900) == {"preflight_ms": 500, "scout_ms": 500}\n\ndef test_negative_scout_is_disabled():\n    assert budgets(500, -1)["scout_ms"] == 0\n''',
        '''from app.session_budget import budgets\n\ndef test_hidden_preflight_bounds():\n    assert budgets(0, 10)["preflight_ms"] == 25\n    assert budgets(90000, 1)["preflight_ms"] == 30000\n''',
        ["scout <= preflight", "preflight clamped to 25..30000"],
    ))

    tasks.append(_task(
        "provider_economist_role_route", "Select routes by requested role, auth confidence, latency, and hidden-clean economics.", "route_economist",
        '''def select(candidates, role, max_latency_ms):\n    return candidates[0] if candidates else None\n''',
        '''def select(candidates, role, max_latency_ms):\n    eligible = [c for c in candidates if c.get("auth", 0) >= 0.6 and c.get("latency_ms", 0) <= max_latency_ms]\n    eligible.sort(key=lambda c: (c.get("role") == role, c.get("hidden_clean_per_usd", 0)), reverse=True)\n    return eligible[0] if eligible else None\n''',
        '''from app.route_economist import select\n\ndef test_role_fit_beats_unrelated_raw_score():\n    rows = [{"name":"fast","role":"scout","auth":1,"latency_ms":10,"hidden_clean_per_usd":99}, {"name":"patch","role":"patch","auth":.9,"latency_ms":40,"hidden_clean_per_usd":4}]\n    assert select(rows, "patch", 100)["name"] == "patch"\n''',
        '''from app.route_economist import select\n\ndef test_hidden_invalid_auth_and_latency_are_excluded():\n    rows = [{"name":"bad-auth","role":"patch","auth":.2,"latency_ms":1}, {"name":"slow","role":"patch","auth":1,"latency_ms":999}]\n    assert select(rows, "patch", 100) is None\n''',
        ["role fit", "auth and latency exclusion", "hidden clean economics"],
    ))

    tasks.append(_task(
        "tool_laziness_required_override", "Skip learned low-value tools but never suppress a workflow-required tool.", "tool_laziness_gate",
        '''def decisions(tools, skip, required):\n    return {name: ("skip" if name in skip else "call") for name in tools}\n''',
        '''def decisions(tools, skip, required):\n    required = set(required)\n    skip = set(skip)\n    return {name: ("call" if name in required else "skip" if name in skip else "call") for name in tools}\n''',
        '''from app.tool_laziness_gate import decisions\n\ndef test_low_value_tool_is_skipped():\n    assert decisions(["search"], ["search"], [])["search"] == "skip"\n\ndef test_required_tool_overrides_skip():\n    assert decisions(["pytest"], ["pytest"], ["pytest"])["pytest"] == "call"\n''',
        '''from app.tool_laziness_gate import decisions\n\ndef test_hidden_unknown_tools_default_to_call():\n    assert decisions(["new_tool"], [], [])["new_tool"] == "call"\n''',
        ["learned skip", "required tools never skipped", "unknown defaults call"],
    ))

    tasks.append(_task(
        "commons_local_approval_gate", "Keep shared Meta Tool Commons candidates advisory until explicit local approval.", "commons_gate",
        '''def adoption(candidate, approved=False, dry_run=True):\n    return {"adopted": True, "candidate": candidate}\n''',
        '''def adoption(candidate, approved=False, dry_run=True):\n    if dry_run:\n        return {"adopted": False, "reason": "dry_run", "candidate": candidate}\n    if not approved:\n        return {"adopted": False, "reason": "explicit local approval required"}\n    if not str(candidate.get("schema_hash", "")).startswith("sha256:"):\n        return {"adopted": False, "reason": "schema pin required"}\n    return {"adopted": True, "reason": "locally approved", "candidate": candidate}\n''',
        '''from app.commons_gate import adoption\n\ndef test_global_candidate_is_not_auto_adopted():\n    assert not adoption({"schema_hash":"sha256:x"})["adopted"]\n\ndef test_explicit_local_approval_adopts():\n    assert adoption({"schema_hash":"sha256:x"}, approved=True, dry_run=False)["adopted"]\n''',
        '''from app.commons_gate import adoption\n\ndef test_hidden_unpinned_candidate_is_rejected():\n    assert not adoption({}, approved=True, dry_run=False)["adopted"]\n''',
        ["dry run non-mutating", "local approval required", "schema pin required"],
    ))

    tasks.append(_task(
        "plugin_permission_risk_gate", "Reject plugin manifests whose permissions exceed their declared risk and approval policy.", "plugin_gate",
        '''def validate(manifest):\n    return {"valid": True, "errors": []}\n''',
        '''def validate(manifest):\n    errors = []\n    risk = manifest.get("risk_class")\n    permissions = manifest.get("permissions") or {}\n    approval = manifest.get("approval_policy") or {}\n    if permissions.get("filesystem_write") and risk == "low":\n        errors.append("write permission requires medium risk or higher")\n    if (permissions.get("filesystem_write") or permissions.get("network_domains")) and not approval.get("required"):\n        errors.append("side effects require approval")\n    return {"valid": not errors, "errors": errors}\n''',
        '''from app.plugin_gate import validate\n\ndef test_read_only_low_risk_manifest_is_valid():\n    assert validate({"risk_class":"low","permissions":{"filesystem_write":[],"network_domains":[]},"approval_policy":{"required":False}})["valid"]\n\ndef test_low_risk_writer_is_invalid():\n    assert not validate({"risk_class":"low","permissions":{"filesystem_write":["tmp"]},"approval_policy":{"required":True}})["valid"]\n''',
        '''from app.plugin_gate import validate\n\ndef test_hidden_network_side_effect_requires_approval():\n    result = validate({"risk_class":"medium","permissions":{"network_domains":["api.example"]},"approval_policy":{"required":False}})\n    assert not result["valid"]\n''',
        ["permission/risk consistency", "side effects require approval"],
    ))

    tasks.append(_task(
        "otel_attribute_secret_redaction", "Export useful telemetry attributes without leaking secrets, prompts, code, or paths.", "otel_redactor",
        '''def safe_attributes(record):\n    return dict(record)\n''',
        '''def safe_attributes(record):\n    forbidden = {"secret", "api_key", "token", "prompt", "source_code", "path"}\n    return {str(k): v for k, v in record.items() if str(k).lower() not in forbidden and isinstance(v, (str, int, float, bool))}\n''',
        '''from app.otel_redactor import safe_attributes\n\ndef test_keeps_allowlisted_scalar_evidence():\n    assert safe_attributes({"provider":"xai","latency_ms":10}) == {"provider":"xai","latency_ms":10}\n\ndef test_removes_secret_and_prompt():\n    result = safe_attributes({"secret":"x","prompt":"private","provider":"xai"})\n    assert "secret" not in result and "prompt" not in result\n''',
        '''from app.otel_redactor import safe_attributes\n\ndef test_hidden_paths_tokens_code_and_nested_values_are_excluded():\n    result = safe_attributes({"path":"/home/user","token":"t","source_code":"x=1","meta":{"x":1},"ok":True})\n    assert result == {"ok": True}\n''',
        ["secret redaction", "scalar evidence retained", "nested data excluded"],
    ))

    tasks.append(_task(
        "network_probe_failure_classification", "Separate DNS, connect, TLS, first-byte, and application failures from provider capability.", "network_probe",
        '''def classify(probe):\n    return "provider_failure"\n''',
        '''def classify(probe):\n    if not probe.get("dns_ok", False): return "dns_failure"\n    if not probe.get("connect_ok", False): return "connect_failure"\n    if not probe.get("tls_ok", False): return "tls_failure"\n    if probe.get("status_code", 0) >= 400: return "application_route_failure"\n    return "route_healthy"\n''',
        '''from app.network_probe import classify\n\ndef test_transport_stages_are_distinct():\n    assert classify({"dns_ok":False}) == "dns_failure"\n    assert classify({"dns_ok":True,"connect_ok":False}) == "connect_failure"\n    assert classify({"dns_ok":True,"connect_ok":True,"tls_ok":False}) == "tls_failure"\n''',
        '''from app.network_probe import classify\n\ndef test_hidden_http_error_is_route_not_model_failure():\n    assert classify({"dns_ok":True,"connect_ok":True,"tls_ok":True,"status_code":401}) == "application_route_failure"\n    assert classify({"dns_ok":True,"connect_ok":True,"tls_ok":True,"status_code":200}) == "route_healthy"\n''',
        ["transport stage classification", "HTTP failure not model capability"],
    ))

    tasks.append(_task(
        "github_pr_task_envelope", "Turn PR files, failed checks, and review comments into a bounded task envelope.", "pr_envelope",
        '''def build(pr):\n    return {"objective": pr.get("title"), "files": pr.get("files", [])}\n''',
        '''def build(pr):\n    files = [str(item.get("filename")) for item in pr.get("files", []) if item.get("filename")][:20]\n    failures = [str(item.get("name")) for item in pr.get("checks", []) if item.get("conclusion") == "failure"][:10]\n    comments = [str(item.get("body"))[:240] for item in pr.get("comments", []) if item.get("body")][:10]\n    return {"objective": str(pr.get("title") or "Repair pull request"), "allowed_paths": files, "failed_checks": failures, "review_intents": comments}\n''',
        '''from app.pr_envelope import build\n\ndef test_failed_checks_and_comments_become_intent():\n    result = build({"title":"Fix","files":[{"filename":"app/a.py"}],"checks":[{"name":"pytest","conclusion":"failure"}],"comments":[{"body":"Handle None"}]})\n    assert result["allowed_paths"] == ["app/a.py"]\n    assert result["failed_checks"] == ["pytest"]\n    assert result["review_intents"] == ["Handle None"]\n''',
        '''from app.pr_envelope import build\n\ndef test_hidden_envelope_is_bounded():\n    result = build({"files":[{"filename":f"f{i}"} for i in range(40)],"comments":[{"body":"x"*1000} for _ in range(20)]})\n    assert len(result["allowed_paths"]) == 20\n    assert len(result["review_intents"]) == 10\n    assert len(result["review_intents"][0]) == 240\n''',
        ["PR paths bounded", "failed checks retained", "review intent bounded"],
    ))

    tasks.append(_task(
        "quality_cascade_language_matrix", "Select syntax, test, and packaging checks across Python, JS, Java, C#, and HTML projects.", "quality_matrix",
        '''def checks(files):\n    return ["python -m pytest"]\n''',
        '''def checks(files):\n    suffixes = {name.rsplit(".", 1)[-1].lower() for name in files if "." in name}\n    result = []\n    if "py" in suffixes: result += ["python -m compileall", "python -m pytest"]\n    if suffixes & {"js", "ts"}: result += ["npm test", "npm run lint"]\n    if "java" in suffixes: result += ["mvn test"]\n    if "cs" in suffixes: result += ["dotnet test"]\n    if suffixes & {"html", "htm"}: result += ["html validation"]\n    return result\n''',
        '''from app.quality_matrix import checks\n\ndef test_python_and_typescript_checks_are_composed():\n    result = checks(["a.py","web.ts"]); assert "python -m pytest" in result and "npm test" in result\n\ndef test_java_and_csharp_are_supported():\n    result = checks(["A.java","B.cs"]); assert "mvn test" in result and "dotnet test" in result\n''',
        '''from app.quality_matrix import checks\n\ndef test_hidden_html_and_unknown_language_behavior():\n    assert "html validation" in checks(["index.html"])\n    assert checks(["README"]) == []\n''',
        ["multi-language checks", "HTML validation", "unknown is non-destructive"],
    ))

    tasks.append(_task(
        "mcp_tool_schema_pinning", "Canonicalize MCP tool schemas and reject changed schemas under an old pin.", "mcp_schema",
        '''import hashlib, json\n\ndef schema_hash(tool):\n    return "sha256:static"\n\ndef valid(tool, declared):\n    return True\n''',
        '''import hashlib, json\n\ndef schema_hash(tool):\n    pinned = {"name":tool.get("name"),"description":tool.get("description", ""),"inputSchema":tool.get("inputSchema") or {}}\n    raw = json.dumps(pinned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()\n    return "sha256:" + hashlib.sha256(raw).hexdigest()\n\ndef valid(tool, declared):\n    return bool(declared) and schema_hash(tool) == declared\n''',
        '''from app.mcp_schema import schema_hash, valid\n\ndef test_same_schema_matches_pin():\n    tool={"name":"read","inputSchema":{"type":"object"}}; assert valid(tool, schema_hash(tool))\n\ndef test_changed_schema_breaks_pin():\n    tool={"name":"read","inputSchema":{"type":"object"}}; pin=schema_hash(tool); tool["inputSchema"]["required"]=["path"]; assert not valid(tool,pin)\n''',
        '''from app.mcp_schema import schema_hash\n\ndef test_hidden_hash_is_order_stable():\n    a={"name":"x","inputSchema":{"properties":{"b":{},"a":{}},"type":"object"}}\n    b={"inputSchema":{"type":"object","properties":{"a":{},"b":{}}},"name":"x"}\n    assert schema_hash(a) == schema_hash(b)\n''',
        ["schema hash deterministic", "changed schema rejected"],
    ))

    tasks.append(_task(
        "chronicle_provider_evidence_record", "Record provider role, canonicalization, tokens, latency, validation, and pytest status without secrets.", "chronicle_record",
        '''def record(provider, evidence):\n    return {"provider": provider, **evidence}\n''',
        '''def record(provider, evidence):\n    allowed = {"role","canonicalized","tokens","latency_ms","validation_status","pytest_status","cost_usd"}\n    clean = {key:evidence[key] for key in allowed if key in evidence}\n    clean["tokens"] = max(0, int(clean.get("tokens", 0)))\n    clean["latency_ms"] = max(0.0, float(clean.get("latency_ms", 0)))\n    return {"provider": str(provider), **clean}\n''',
        '''from app.chronicle_record import record\n\ndef test_required_provider_evidence_is_recorded():\n    result=record("xai",{"role":"patch","canonicalized":False,"tokens":12,"latency_ms":3,"validation_status":"valid","pytest_status":"passed"})\n    assert result["provider"] == "xai" and result["pytest_status"] == "passed"\n\ndef test_secret_is_not_recorded():\n    assert "api_key" not in record("xai",{"api_key":"secret"})\n''',
        '''from app.chronicle_record import record\n\ndef test_hidden_negative_economics_are_clamped():\n    result=record("xai",{"tokens":-5,"latency_ms":-2,"cost_usd":0.1}); assert result["tokens"] == 0 and result["latency_ms"] == 0\n''',
        ["required Chronicle dimensions", "secret exclusion", "nonnegative metrics"],
    ))

    tasks.append(_task(
        "deployment_route_resolution", "Resolve beast-auto through provider defaults while preserving explicit model overrides.", "deployment_route",
        '''def resolve(provider, requested, defaults):\n    return requested\n''',
        '''def resolve(provider, requested, defaults):\n    provider_id = str(provider).lower().replace("-", "_")\n    if requested and requested not in {"beast-auto","beast_auto","auto"}: return requested\n    if provider_id not in defaults: raise KeyError(provider_id)\n    return defaults[provider_id]\n''',
        '''import pytest\nfrom app.deployment_route import resolve\n\ndef test_auto_resolves_default_and_explicit_wins():\n    defaults={"xai":"grok-build-0.1"}; assert resolve("xai","beast-auto",defaults)=="grok-build-0.1"; assert resolve("xai","grok-4",defaults)=="grok-4"\n\ndef test_unknown_provider_fails_closed():\n    with pytest.raises(KeyError): resolve("unknown","beast-auto",{})\n''',
        '''from app.deployment_route import resolve\n\ndef test_hidden_provider_alias_normalization():\n    assert resolve("nvidia-nim","auto",{"nvidia_nim":"nemotron"}) == "nemotron"\n''',
        ["auto default", "explicit override", "unknown fails closed", "alias normalization"],
    ))

    tasks.append(_task(
        "vector_context_deduplication", "Deduplicate semantic context by canonical identity while preserving best score and bounded ordering.", "vector_context",
        '''def select(rows, limit=5):\n    return rows[:limit]\n''',
        '''def select(rows, limit=5):\n    best = {}\n    for row in rows:\n        key = (str(row.get("path") or ""), str(row.get("symbol") or ""))\n        if key not in best or float(row.get("score",0)) > float(best[key].get("score",0)): best[key] = row\n    return sorted(best.values(), key=lambda row: float(row.get("score",0)), reverse=True)[:max(0,int(limit))]\n''',
        '''from app.vector_context import select\n\ndef test_duplicate_identity_keeps_best_score():\n    result=select([{"path":"a.py","symbol":"f","score":.2},{"path":"a.py","symbol":"f","score":.9}]); assert len(result)==1 and result[0]["score"]==.9\n\ndef test_results_are_ranked_and_bounded():\n    result=select([{"path":str(i),"score":i} for i in range(9)],3); assert [x["score"] for x in result]==[8,7,6]\n''',
        '''from app.vector_context import select\n\ndef test_hidden_empty_and_zero_limit():\n    assert select([], 5) == []\n    assert select([{"path":"a","score":1}], 0) == []\n''',
        ["canonical deduplication", "best score retained", "bounded ranking"],
    ))
    return tasks


def omni_tasks() -> List[SuiteTask]:
    return suite_tasks() + additional_tasks()


OMNI_TASK_CLASSES: Dict[str, str] = {
    "provider_model_wiring": "provider_routing",
    "config_validation_edge_case": "config_governance",
    "provider_id_parser": "parsing",
    "multi_file_hidden_decimal_fix": "multi_file_hidden",
    "ui_state_collapse_selection": "tui_state",
    "async_streaming_empty_chunk": "async_streaming",
    "provider_config_secret_redaction": "secret_redaction",
    "patch_rollback_created_file": "rollback",
    "output_governance_malformed_json": "output_governance",
    "nim_refs_only_contract": "refs_only_action_ir",
    **{task.name: task.name for task in additional_tasks()},
}
