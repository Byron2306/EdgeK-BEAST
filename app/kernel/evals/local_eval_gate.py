import re
from typing import Any, Dict, List

class LocalEvalGate:
    def evaluate(self, *, request, response: str, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        checks = []

        for rule in rules:
            kind = rule.get("type")

            if kind == "must_contain":
                value = str(rule.get("value", ""))
                ok = value.lower() in response.lower()
                checks.append({"rule": rule, "passed": ok})

            elif kind == "must_not_contain":
                value = str(rule.get("value", ""))
                ok = value.lower() not in response.lower()
                checks.append({"rule": rule, "passed": ok})

            elif kind == "regex":
                pattern = str(rule.get("pattern", ""))
                ok = bool(re.search(pattern, response, flags=re.IGNORECASE))
                checks.append({"rule": rule, "passed": ok})

            elif kind == "max_length":
                limit = int(rule.get("value", 4000))
                ok = len(response) <= limit
                checks.append({"rule": rule, "passed": ok})

            elif kind == "no_secret_patterns":
                secretish = [
                    r"sk-[A-Za-z0-9]{20,}",
                    r"-----BEGIN PRIVATE KEY-----",
                    r"AKIA[0-9A-Z]{16}",
                    r"password\s*=",
                ]
                ok = not any(re.search(p, response) for p in secretish)
                checks.append({"rule": rule, "passed": ok})

            else:
                checks.append({"rule": rule, "passed": False, "reason": "unknown_rule_type"})

        passed = all(c.get("passed") for c in checks)
        return {
            "beast_object_type": "local_eval_gate_result",
            "version": "1.0",
            "passed": passed,
            "checks": checks,
            "promotion_allowed": passed,
        }
