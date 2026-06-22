"""Task matrix definitions for the BEAST definitive mega-test."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List


DEFAULT_PROVIDERS = ["nvidia_nim", "gemini", "groq", "cerebras", "cloudflare"]
FIRST_LIVE_PROVIDERS = ["nvidia_nim", "mistral", "gemini", "cohere", "groq"]
OCCURRENCE_POINTS = [1, 2, 3, 5, 10]
LANES = ["raw", "beast_no_compute_governor", "full_beast_compute_governor"]

TASK_FAMILIES: Dict[str, Dict[str, str]] = {
    "schema_validation": {
        "intent": "Validate structured output and fail closed on malformed action plans.",
        "fixture_anchor": "output_governance_malformed_json,mcp_tool_schema_pinning",
    },
    "provider_alias_normalization": {
        "intent": "Resolve provider/model aliases without mutating explicit overrides.",
        "fixture_anchor": "deployment_route_resolution,provider_id_parser",
    },
    "patch_compilation": {
        "intent": "Produce source patches that compile and pass visible tests.",
        "fixture_anchor": "multi_file_hidden_decimal_fix,quality_cascade_language_matrix",
    },
    "syntax_check": {
        "intent": "Catch language syntax errors before verification credit.",
        "fixture_anchor": "patch_compilation,quality_matrix",
    },
    "route_diagnostics": {
        "intent": "Separate route/network/auth failure from model capability.",
        "fixture_anchor": "network_probe_failure_classification,route_diagnostics",
    },
    "secret_redaction": {
        "intent": "Preserve useful evidence while excluding secrets, prompts, code, and paths.",
        "fixture_anchor": "provider_config_secret_redaction,otel_attribute_secret_redaction",
    },
}


@dataclass(frozen=True)
class MegaObservationPlan:
    mode: str
    family: str
    provider: str
    occurrence: int
    lane: str
    task_id: str
    fixture_anchor: str
    objective: str
    status: str = "planned"

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def normalize_csv(values: str | Iterable[str] | None, default: List[str]) -> List[str]:
    """Normalize CLI lists without accepting empty selections."""

    if values is None:
        return list(default)
    if isinstance(values, str):
        items = [item.strip() for item in values.split(",")]
    else:
        items = [str(item).strip() for item in values]
    selected = [item for item in items if item]
    return selected or list(default)


def validate_families(families: Iterable[str]) -> List[str]:
    selected = [str(item).strip() for item in families if str(item).strip()]
    unknown = [item for item in selected if item not in TASK_FAMILIES]
    if unknown:
        raise ValueError(f"Unknown mega-test task family: {', '.join(unknown)}")
    return selected


def validate_occurrences(occurrences: Iterable[int]) -> List[int]:
    selected = [int(item) for item in occurrences]
    invalid = [item for item in selected if item not in OCCURRENCE_POINTS]
    if invalid:
        raise ValueError(f"Unsupported occurrence point: {', '.join(str(item) for item in invalid)}")
    return selected


def validate_lanes(lanes: Iterable[str]) -> List[str]:
    selected = [str(item).strip() for item in lanes if str(item).strip()]
    invalid = [item for item in selected if item not in LANES]
    if invalid:
        raise ValueError(f"Unsupported mega-test lane: {', '.join(invalid)}")
    return selected


def task_id(family: str, occurrence: int) -> str:
    return f"{family}_o{occurrence:02d}_v1"


def build_observation_plan(
    providers: Iterable[str] | None = None,
    families: Iterable[str] | None = None,
    occurrences: Iterable[int] | None = None,
    lanes: Iterable[str] | None = None,
    mode: str = "controlled",
) -> List[MegaObservationPlan]:
    """Build the controlled mega-test lane matrix."""

    selected_providers = normalize_csv(providers, DEFAULT_PROVIDERS)
    selected_families = validate_families(families or TASK_FAMILIES.keys())
    selected_occurrences = validate_occurrences(occurrences or OCCURRENCE_POINTS)
    selected_lanes = validate_lanes(lanes or LANES)
    rows: List[MegaObservationPlan] = []
    for family in selected_families:
        metadata = TASK_FAMILIES[family]
        for provider in selected_providers:
            for occurrence in selected_occurrences:
                for lane in selected_lanes:
                    rows.append(MegaObservationPlan(
                        mode=mode,
                        family=family,
                        provider=str(provider).strip(),
                        occurrence=occurrence,
                        lane=lane,
                        task_id=task_id(family, occurrence),
                        fixture_anchor=metadata["fixture_anchor"],
                        objective=metadata["intent"],
                    ))
    return rows


def expected_controlled_observations(
    providers: Iterable[str] | None = None,
    families: Iterable[str] | None = None,
    occurrences: Iterable[int] | None = None,
    lanes: Iterable[str] | None = None,
) -> int:
    return len(normalize_csv(providers, DEFAULT_PROVIDERS)) * len(validate_families(families or TASK_FAMILIES.keys())) * len(validate_occurrences(occurrences or OCCURRENCE_POINTS)) * len(validate_lanes(lanes or LANES))
