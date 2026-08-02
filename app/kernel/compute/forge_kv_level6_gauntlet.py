"""Fixture-driven production publication and receiver gauntlet."""
from __future__ import annotations

from typing import Any


def run_gauntlet(*, plane: Any, approval: Any, commit: dict, files: dict[str,bytes], chunks: dict[str,bytes],
                 receiver: Any, receiver_job: dict) -> dict:
    published=plane.publish_hf(approval=approval,commit=commit,files=files,chunks=chunks,branch="forge-proof",open_pr=True,now=approval.issued_at+1)
    received=receiver.run(**receiver_job)
    return {"beast_object_type":"forge_kv_level6_gauntlet_receipt","version":"1.0",
            "publication_status":published["status"],"receiver_verified":received.locally_verified,
            "promotion_granted":received.promotion_granted,"native_context_exported":published["native_context_exported"],
            "passed":published["status"]=="published" and received.locally_verified and not received.promotion_granted and not published["native_context_exported"]}
