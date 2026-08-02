from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .residual_candidate import ResidualCandidate
from .residual_contracts import ResidualRoute


@dataclass(frozen=True, slots=True)
class CandidateSet:
    request_digest: str
    workspace_id: str
    privacy_domain: str
    candidates: tuple[ResidualCandidate, ...]

    def __post_init__(self) -> None:
        ids = [candidate.candidate_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate IDs must be unique")
        for candidate in self.candidates:
            if candidate.workspace_id != self.workspace_id:
                raise PermissionError("candidate workspace does not match candidate set")
            if candidate.privacy_domain != self.privacy_domain:
                raise PermissionError("candidate privacy domain does not match candidate set")

    def by_route(self, route: ResidualRoute) -> tuple[ResidualCandidate, ...]:
        return tuple(candidate for candidate in self.candidates if candidate.route is route)

    def eligible(self) -> tuple[ResidualCandidate, ...]:
        return tuple(candidate for candidate in self.candidates if candidate.eligible)


def collect_candidates(
    request_digest: str,
    workspace_id: str,
    privacy_domain: str,
    candidates: Iterable[ResidualCandidate],
) -> CandidateSet:
    return CandidateSet(
        request_digest=request_digest,
        workspace_id=workspace_id,
        privacy_domain=privacy_domain,
        candidates=tuple(candidates),
    )
