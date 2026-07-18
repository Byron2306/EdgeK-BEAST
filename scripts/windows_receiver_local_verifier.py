#!/usr/bin/env python3
"""Explicit local verifier hook for the Windows discovery receiver.

This intentionally fails closed: set BEAST_RECEIVER_VERIFY_COMMAND to a command
that tests the task against the receiver's clean checkout. The command receives
task.json and candidate.json as its final two arguments.
"""
import json, os, subprocess, sys
if len(sys.argv) != 3:
    raise SystemExit("usage: windows_receiver_local_verifier.py task.json candidate.json")
command = os.environ.get("BEAST_RECEIVER_VERIFY_COMMAND")
if not command and os.environ.get("BEAST_RECEIVER_VERIFIER_PLAN"):
    task = json.loads(open(sys.argv[1], encoding="utf-8").read())
    plan = json.loads(open(os.environ["BEAST_RECEIVER_VERIFIER_PLAN"], encoding="utf-8").read())
    digest = task.get("semantic_contract_digest", "")
    command = " ".join(plan.get("contracts", {}).get(digest, []))
if not command:
    raise SystemExit("No verifier configured; refusing to claim reproduction")
completed = subprocess.run([*command.split(), sys.argv[1], sys.argv[2]], timeout=120, check=False)
raise SystemExit(completed.returncode)
