#!/usr/bin/env python3
"""Generate LiteLLM and Nginx deployment files from BEAST policy."""

import argparse
import json

from app.kernel.deployment import DeploymentManager
from app.kernel.reason import reasoner


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate EdgeK BEAST deployment configs.")
    parser.add_argument("--out", default="deploy/generated")
    args = parser.parse_args()
    manager = DeploymentManager(reasoner.policies)
    print(json.dumps(manager.write_generated_files(args.out), indent=2))


if __name__ == "__main__":
    main()
