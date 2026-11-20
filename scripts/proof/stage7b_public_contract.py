"""Public-only prompt treatment for the isolated Stage 7B near-miss rerun."""


def public_contract_messages(task, source, failure):
    visible = task["files"][f"test_{task['pkg']}_contract.py"]
    return [
        {"role": "system", "content": (
            "Repair the file with exactly one line replacement. Return one JSON object "
            "with string fields old_text and new_text. Copy original indentation exactly. "
            "All public assertions must pass, including tests that already pass. "
            "A constant edit may change only the integer assigned to the same name. "
            "A return edit must keep the original returned constant name and may "
            "add or subtract one integer literal from it. Do not edit tests."
        )},
        {"role": "user", "content": (
            f"File: {task['target']}\n{source}\n"
            f"Public contract tests:\n{visible}\n"
            f"Visible failing test output:\n{failure[-1800:]}"
        )},
    ]
