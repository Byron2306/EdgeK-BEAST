"""Create an isolated Git workspace for the native Coder UI feedback trial."""

import argparse
from pathlib import Path
import subprocess

FILES = {
    "plain.py": "BATCH_SIZE = 3\nRETRY_LIMIT = 17\n",
    "test_plain.py": """import unittest
from plain import BATCH_SIZE, RETRY_LIMIT

class Contract(unittest.TestCase):
    def test_batch(self):
        self.assertEqual(BATCH_SIZE, 5)

    def test_retry_remains(self):
        self.assertEqual(RETRY_LIMIT, 17)
""",
    "dependent.py": "BATCH_SIZE = 3\nRETRY_LIMIT = 3\n\ndef attempts():\n    return BATCH_SIZE\n",
    "test_dependent.py": """import unittest
from dependent import BATCH_SIZE, RETRY_LIMIT, attempts

class Contract(unittest.TestCase):
    def test_attempts(self):
        self.assertEqual(attempts(), 5)

    def test_constants_stay_put(self):
        self.assertEqual((BATCH_SIZE, RETRY_LIMIT), (3, 3))
""",
    ".gitignore": ".beast/\n__pycache__/\n",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    root = parser.parse_args().workspace.resolve()
    root.mkdir(mode=0o700, exist_ok=False)
    for name, value in FILES.items():
        (root / name).write_text(value, encoding="utf-8")
    for command in (["git", "init", "-q"], ["git", "add", "--", *FILES],
                    ["git", "-c", "user.name=BEAST UI Trial", "-c", "user.email=beast-ui-trial@localhost",
                     "-c", "commit.gpgsign=false", "commit", "-qm", "Create isolated crystal UI fixtures"]):
        subprocess.run(command, cwd=root, check=True)
    print(f"WORKSPACE={root}")
    print("Plain task: Fix plain.py to pass test_plain.py. Read the target and run the test before editing, "
          "then make one exact line replacement and run the tests again.")
    print("Near-miss task (repeat unchanged): Fix dependent.py to pass test_dependent.py without editing tests.")


if __name__ == "__main__":
    main()
