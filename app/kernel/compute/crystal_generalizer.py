"""Strict structural generalization of natural RuntimeEpisodes.

Version one deliberately supports only a small allowlist of parameter classes.
Varying process/socket descriptor identities or causal structure fail closed;
similarity is never used as an equivalence proof.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from app.kernel.compute.runtime_crystallizer import CrystalIR
from app.kernel.compute.crystal_verifier_synthesis import synthesize_verifier_plan
from app.kernel.sensorium.contracts import RuntimeEpisode, content_hash


SUCCESS_STATES = {"verified_success", "success", "passed"}
PORT_RE = re.compile(r"(?P<prefix>(?:^|:)port:)(?P<value>[1-9][0-9]{0,4})(?=$|:)")
WORKSPACE_RE = re.compile(r"^workspace:(?P<value>[A-Za-z0-9._-]+)$")
DIGEST_PARAMETER_RE = re.compile(r"^(?P<prefix>cleanup_manifest|approval):(?P<value>sha256:[0-9a-f]{64})$")
PARAMETERIZABLE_FIELDS = {"subject", "reads", "requires", "writes", "produces", "resource"}
IDENTITY_FIELDS = {"descriptor_refs", "operation", "phase", "result", "branch", "event_type", "payload_sha256"}


@dataclass(frozen=True)
class GeneralizationReceipt:
    candidate_id: str
    positive_episode_hashes: tuple[str, ...]
    negative_episode_hashes: tuple[str, ...]
    structural_signature: tuple[tuple[str, str], ...]
    inferred_parameters: tuple[str, ...]
    rejected_parameter_classes: tuple[str, ...]
    family_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "positive_episode_hashes": list(self.positive_episode_hashes),
            "negative_episode_hashes": list(self.negative_episode_hashes),
            "structural_signature": [list(item) for item in self.structural_signature],
            "inferred_parameters": list(self.inferred_parameters),
            "rejected_parameter_classes": list(self.rejected_parameter_classes),
            "family_hash": self.family_hash,
        }


class CrystalGeneralizer:
    def __init__(self, *, minimum_positive_episodes: int = 3):
        if minimum_positive_episodes < 2:
            raise ValueError("minimum_positive_episodes must be at least two")
        self.minimum_positive_episodes = int(minimum_positive_episodes)

    def generalize(
        self,
        episodes: Iterable[RuntimeEpisode | Mapping[str, Any]],
        *,
        identity: str,
        task_family: Iterable[str],
    ) -> tuple[CrystalIR, GeneralizationReceipt]:
        values = sorted(
            (self._episode_dict(item) for item in episodes),
            key=lambda item: str(item.get("episode_hash") or ""),
        )
        positives = [item for item in values if str((item.get("outcome") or {}).get("status")) in SUCCESS_STATES]
        negatives = [item for item in values if item not in positives]
        if len(positives) < self.minimum_positive_episodes:
            raise ValueError(f"at least {self.minimum_positive_episodes} successful natural episodes are required")

        positive_steps = [self._steps(item) for item in positives]
        signatures = [tuple((step["operation"], step["phase"]) for step in steps) for steps in positive_steps]
        if any(signature != signatures[0] for signature in signatures[1:]):
            raise ValueError("positive episodes do not share one structural operation/phase signature")
        causal = [self._causal_signature(item) for item in positives]
        if any(value != causal[0] for value in causal[1:]):
            raise ValueError("positive episodes do not share one evidence-backed causal topology")

        parameter_observations: dict[str, tuple[Any, ...]] = {}
        templates = []
        for index in range(len(positive_steps[0])):
            templates.append(self._merge_values(
                [steps[index] for steps in positive_steps],
                path=(f"step_{index}",),
                parameter_observations=parameter_observations,
            ))
        parameter_schemas = self._parameter_schemas(parameter_observations)
        preconditions = self._preconditions(templates)
        postconditions = self._postconditions(templates, positives)
        negative_conditions = self._negative_conditions(negatives)
        family_payload = {
            "positive_episode_hashes": sorted(str(item["episode_hash"]) for item in positives),
            "signature": signatures[0],
            "templates": templates,
            "causal": causal[0],
        }
        family_hash = self._hash(family_payload)
        receipt = GeneralizationReceipt(
            candidate_id=identity,
            positive_episode_hashes=tuple(str(item["episode_hash"]) for item in positives),
            negative_episode_hashes=tuple(str(item["episode_hash"]) for item in negatives),
            structural_signature=signatures[0],
            inferred_parameters=tuple(sorted(parameter_schemas)),
            rejected_parameter_classes=("process_identity", "socket_identity", "executable_digest", "arbitrary_string"),
            family_hash=family_hash,
        )
        resources = {
            key: max(float(item.get("resources", {}).get(key, 0.0)) for item in positives)
            for key in sorted({key for item in positives for key in (item.get("resources") or {})})
        }
        verifier_plan = synthesize_verifier_plan(
            templates, postconditions=postconditions, negative_conditions=negative_conditions,
            evidence=receipt.positive_episode_hashes + receipt.negative_episode_hashes,
        )
        crystal = CrystalIR(
            identity=identity,
            task_family=tuple(task_family),
            parameters=tuple(sorted(parameter_schemas)),
            preconditions=tuple(preconditions),
            execution_graph=tuple(step["operation"] for step in templates),
            postconditions=tuple(postconditions),
            evidence=receipt.positive_episode_hashes + receipt.negative_episode_hashes,
            source_episode_hash=family_hash,
            topology=tuple(self._descriptor_invariants(templates)),
            resource_envelope=resources,
            negative_conditions=tuple(negative_conditions),
            causal_edges=tuple((f"step:{source}", f"step:{target}", relation, confidence) for source, target, relation, confidence in causal[0]),
            parameter_schemas=parameter_schemas,
            invariants={"step_templates": templates, "causal_topology": causal[0],
                        "verifier_plan": verifier_plan.to_dict()},
            generalization_receipt=receipt.to_dict(),
        )
        return crystal, receipt

    @staticmethod
    def _episode_dict(value: RuntimeEpisode | Mapping[str, Any]) -> dict[str, Any]:
        if isinstance(value, RuntimeEpisode):
            value.validate()
            return value.to_dict()
        result = dict(value)
        if not result.get("episode_hash"):
            raise ValueError("every episode requires a sealed episode_hash")
        content = {
            key: result.get(key)
            for key in (
                "mission_id", "objective_hash", "workspace_identity", "initial_state_hash",
                "event_ids", "source_loss", "causal_graph", "resources", "outcome",
            )
        }
        if result["episode_hash"] != content_hash(content):
            raise ValueError("episode_hash does not match episode content")
        return result

    @staticmethod
    def _steps(episode: Mapping[str, Any]) -> list[dict[str, Any]]:
        graph = episode.get("causal_graph") or {}
        facts = graph.get("event_facts") or {}
        steps = []
        for event_id in episode.get("event_ids") or ():
            fact = facts.get(event_id)
            if fact:
                projected = dict(fact)
                # The digest remains bound through the episode hash/evidence
                # list; it is evidence identity, not generalizable structure.
                projected.pop("payload_sha256", None)
                steps.append(projected)
        if not steps:
            raise ValueError("episode has no typed physical event facts")
        return steps

    @staticmethod
    def _causal_signature(episode: Mapping[str, Any]) -> tuple[tuple[int, int, str, float], ...]:
        graph = episode.get("causal_graph") or {}
        event_ids = list(episode.get("event_ids") or ())
        positions = {event_id: index for index, event_id in enumerate(event_ids)}
        result = []
        for edge in graph.get("causal_edges") or ():
            source, target = edge.get("source"), edge.get("target")
            if source in positions and target in positions:
                result.append((positions[source], positions[target], str(edge.get("relation")), float(edge.get("confidence", 0.0))))
        return tuple(sorted(result))

    def _merge_values(
        self,
        values: Sequence[Any],
        *,
        path: tuple[str, ...],
        parameter_observations: dict[str, tuple[Any, ...]],
    ) -> Any:
        first = values[0]
        if all(value == first for value in values[1:]):
            return first
        field = path[-1]
        if "descriptor_refs" in path and all(isinstance(value, str) for value in values):
            kinds = tuple(value.split(":", 1)[0] for value in values)
            if len(set(kinds)) == 1 and kinds[0] in {"process", "socket", "port_lease", "workspace"}:
                return f"descriptor_type:{kinds[0]}"
            raise ValueError(f"unsafe varying descriptor class at {'.'.join(path)}")
        if all(isinstance(value, Mapping) for value in values):
            keys = set(first)
            if any(set(value) != keys for value in values[1:]):
                raise ValueError(f"structural field mismatch at {'.'.join(path)}")
            return {
                key: self._merge_values(
                    [value[key] for value in values],
                    path=(*path, str(key)),
                    parameter_observations=parameter_observations,
                )
                for key in sorted(keys)
            }
        if all(isinstance(value, list) for value in values):
            if any(len(value) != len(first) for value in values[1:]):
                raise ValueError(f"structural list mismatch at {'.'.join(path)}")
            return [
                self._merge_values(
                    [value[index] for value in values],
                    path=(*path, field, str(index)),
                    parameter_observations=parameter_observations,
                )
                for index in range(len(first))
            ]
        if field in IDENTITY_FIELDS or "descriptor_refs" in path:
            raise ValueError(f"unsafe varying causal identity at {'.'.join(path)}")
        if not all(isinstance(value, str) for value in values) or not any(item in PARAMETERIZABLE_FIELDS for item in path):
            raise ValueError(f"unsupported varying value at {'.'.join(path)}")
        return self._infer_string_parameter(tuple(values), path, parameter_observations)

    @staticmethod
    def _infer_string_parameter(values: tuple[str, ...], path: tuple[str, ...], observations: dict[str, tuple[Any, ...]]) -> str:
        port_matches = [PORT_RE.search(value) for value in values]
        if all(port_matches):
            normalized = [PORT_RE.sub(r"\g<prefix>{{requested_port}}", value) for value in values]
            if len(set(normalized)) == 1:
                observed = tuple(int(match.group("value")) for match in port_matches if match)
                previous = observations.setdefault("requested_port", observed)
                if previous != observed:
                    raise ValueError("requested_port observations are not correlated across causal facts")
                return normalized[0]
        workspace_matches = [WORKSPACE_RE.fullmatch(value) for value in values]
        if all(workspace_matches):
            observed = tuple(match.group("value") for match in workspace_matches if match)
            previous = observations.setdefault("workspace_identity", observed)
            if previous != observed:
                raise ValueError("workspace observations are not correlated across causal facts")
            return "workspace:{{workspace_identity}}"
        digest_matches = [DIGEST_PARAMETER_RE.fullmatch(value) for value in values]
        if all(digest_matches) and len({match.group("prefix") for match in digest_matches if match}) == 1:
            prefix = digest_matches[0].group("prefix")
            name = "cleanup_manifest_digest" if prefix == "cleanup_manifest" else "approval_receipt_digest"
            observed = tuple(match.group("value") for match in digest_matches if match)
            previous = observations.setdefault(name, observed)
            if previous != observed:
                raise ValueError(f"{name} observations are not correlated across causal facts")
            return f"{prefix}:{{{{{name}}}}}"
        raise ValueError(f"unsafe varying causal value at {'.'.join(path)}")

    @staticmethod
    def _parameter_schemas(observations: Mapping[str, tuple[Any, ...]]) -> dict[str, Any]:
        schemas: dict[str, Any] = {}
        for name, values in sorted(observations.items()):
            if name == "requested_port":
                schemas[name] = {"type": "integer", "minimum": 1, "maximum": 65535, "observed_min": min(values), "observed_max": max(values), "observed_count": len(values)}
            elif name == "workspace_identity":
                schemas[name] = {"type": "workspace_identity", "observed_count": len(values)}
            elif name in {"cleanup_manifest_digest", "approval_receipt_digest"}:
                schemas[name] = {"type": "sha256_digest", "observed_count": len(values)}
        return schemas

    @staticmethod
    def _preconditions(templates: Sequence[Mapping[str, Any]]) -> list[str]:
        result = []
        for step in templates:
            result.extend(str(item) for item in step.get("requires") or ())
            transition = step.get("state_transition") or {}
            if transition.get("resource") and transition.get("from"):
                result.append(f"{transition['resource']}=={transition['from']}")
        return list(dict.fromkeys(result)) or ["typed_physical_preconditions_revalidated"]

    @staticmethod
    def _postconditions(templates: Sequence[Mapping[str, Any]], positives: Sequence[Mapping[str, Any]]) -> list[str]:
        result = [f"{step['operation']}:{step['result']}" for step in templates if step.get("phase") == "verification"]
        result.extend(f"outcome:{(item.get('outcome') or {}).get('status')}" for item in positives)
        return list(dict.fromkeys(result))

    @classmethod
    def _negative_conditions(cls, negatives: Sequence[Mapping[str, Any]]) -> list[str]:
        result = []
        for episode in negatives:
            status = str((episode.get("outcome") or {}).get("status") or "unknown")
            result.append(f"outcome_status:{status}")
            for step in cls._steps(episode):
                if step.get("branch"):
                    result.append(f"branch:{step['branch']}")
                if step.get("result") in {"failure", "denied", "refused", "rolled_back"}:
                    result.append(f"effect_result:{step['operation']}:{step['result']}")
        return list(dict.fromkeys(result))

    @staticmethod
    def _descriptor_invariants(templates: Sequence[Mapping[str, Any]]) -> list[str]:
        return list(dict.fromkeys(str(item) for step in templates for item in (step.get("descriptor_refs") or ())))

    @staticmethod
    def _hash(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()
