#!/usr/bin/env python3
"""Commons scale economics ladder.

Example:

    python scripts/commons_scale_economics_ladder.py \
      --target-spaces 10 --matches-per-space 3 \
      --cloud-call-cost 0.02 --token-cost-per-1m 5

Defaults use zero-dollar assumptions so the report never pretends to know
market prices. Pass assumptions explicitly when exploring financial scenarios.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.kernel.commons_economy import ComputeReductionEconomy
from app.kernel.commons_scale_economics import CommonsScaleEconomics, ScaleEconomicsAssumptions
from app.kernel.commons_space_registry import CommonsSpaceRegistry


LATEST_RECEIPT = ROOT / "benchmarks" / "results" / "commons_scale_economics_ladder_latest.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute BEAST Commons proof density and scale economics")
    parser.add_argument("--target-spaces", type=int, default=10)
    parser.add_argument("--matches-per-space", type=int, default=3)
    parser.add_argument("--tokens-per-match", type=int, default=3900)
    parser.add_argument("--cloud-call-cost", type=float, default=0.0)
    parser.add_argument("--token-cost-per-1m", type=float, default=0.0)
    parser.add_argument("--local-verifier-cost", type=float, default=0.0)
    parser.add_argument("--setup-cost", type=float, default=0.0)
    parser.add_argument("--marketplace-take-rate", type=float, default=0.0)
    parser.add_argument(
        "--value-tier",
        default="base_space",
        choices=["base_space", "forge_crystal", "meta_tool", "skill_tree", "fused_inference_crystal"],
    )
    parser.add_argument("--tier-value-multiplier", type=float, default=None)
    parser.add_argument("--output", default=str(LATEST_RECEIPT))
    args = parser.parse_args()

    registry = CommonsSpaceRegistry()
    economy = ComputeReductionEconomy(registry)
    default_multipliers = {
        "base_space": 1.0,
        "forge_crystal": 1.5,
        "meta_tool": 1.8,
        "skill_tree": 2.2,
        "fused_inference_crystal": 3.0,
    }
    assumptions = ScaleEconomicsAssumptions(
        target_spaces=args.target_spaces,
        matches_per_space=args.matches_per_space,
        tokens_per_match=args.tokens_per_match,
        cloud_call_cost_usd=args.cloud_call_cost,
        token_cost_per_1m_usd=args.token_cost_per_1m,
        local_verifier_cost_usd=args.local_verifier_cost,
        setup_cost_usd=args.setup_cost,
        marketplace_take_rate=args.marketplace_take_rate,
        value_tier=args.value_tier,
        tier_value_multiplier=(
            float(args.tier_value_multiplier)
            if args.tier_value_multiplier is not None
            else default_multipliers[args.value_tier]
        ),
    )
    report = CommonsScaleEconomics(registry, economy).report(assumptions)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["receipt_path"] = str(output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
