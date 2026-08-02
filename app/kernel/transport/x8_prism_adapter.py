from __future__ import annotations
from .x8_contracts import RemoteResidualCandidate

REMOTE_ROUTE = "remote_residual"
REMOTE_AUTHORITY = "reconstruction_only"

def as_prism_candidate(candidate: RemoteResidualCandidate) -> dict:
    """Payload-safe adapter for a PRISM candidate source.

    It advertises estimated route economics and applicability, never execution authority.
    """
    return {
        "candidate_id": candidate.candidate_id,
        "route": REMOTE_ROUTE,
        "authority": REMOTE_AUTHORITY,
        "applicable": candidate.eligible,
        "estimated_cost_us": candidate.total_cost_us,
        "missing_bytes": candidate.missing_bytes,
        "object_digest": candidate.object_digest,
        "manifest_digest": candidate.manifest_digest,
        "sender_node": candidate.sender_node,
        "promotion_allowed": False,
        "execution_allowed": False,
        "raw_payload_retained": False,
    }
