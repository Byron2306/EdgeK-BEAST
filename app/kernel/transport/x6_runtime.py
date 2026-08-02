from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryDirectory
from .x4_contracts import build_manifest, ObjectManifest, digest_bytes
from .x4_cas import FileCAS
from .x4_protocol import Receiver
from .x5_runtime import _measure_lane, LaneAdapter
from .x5_contracts import SelectionPolicy
from .x5_economics import choose_lane
from .x6_contracts import SignedManifestEnvelope, X6Receipt, X6Refusal
from .x6_identity import NodeSigner, verify_envelope

@dataclass
class ReplayLedger:
    last_sequence: dict[tuple[str,str], int]
    seen_nonces: set[tuple[str,str,str]]
    def __init__(self):
        self.last_sequence = {}
        self.seen_nonces = set()
    def admit(self, sender: str, receiver: str, sequence: int, nonce: str) -> None:
        key=(sender,receiver)
        if sequence <= self.last_sequence.get(key,0):
            raise X6Refusal("manifest sequence replay")
        nonce_key=(sender,receiver,nonce)
        if nonce_key in self.seen_nonces:
            raise X6Refusal("manifest nonce replay")
        self.last_sequence[key]=sequence
        self.seen_nonces.add(nonce_key)

def _manifest_from_body(body: dict) -> ObjectManifest:
    from .x4_contracts import ChunkRef
    try:
        return ObjectManifest(
            version=int(body["version"]),
            object_digest=str(body["object_digest"]),
            object_size=int(body["object_size"]),
            chunk_size=int(body["chunk_size"]),
            chunks=tuple(ChunkRef(**c) for c in body["chunks"]),
        )
    except Exception as exc:
        raise X6Refusal("invalid manifest body") from exc

def create_envelope(data: bytes, sender_node: str, receiver_node: str, signer: NodeSigner, sequence: int, chunk_size: int=65536, nonce: str|None=None) -> tuple[ObjectManifest,SignedManifestEnvelope]:
    manifest=build_manifest(data,chunk_size)
    body={
        "sender_node":sender_node,
        "receiver_node":receiver_node,
        "manifest_body":manifest.body(),
        "manifest_digest":manifest.manifest_digest,
        "nonce":nonce or token_hex(16),
        "sequence":sequence,
    }
    env=SignedManifestEnvelope(
        sender_node=sender_node,
        receiver_node=receiver_node,
        manifest_body=manifest.body(),
        manifest_digest=manifest.manifest_digest,
        public_key_b64=signer.public_key_b64,
        signature_b64=signer.sign(body),
        nonce=body["nonce"],
        sequence=sequence,
    )
    return manifest,env

def run_x6_canary(*, data: bytes, sender_node: str, receiver_node: str, signer: NodeSigner, trusted_public_keys: set[str], receiver_cas_root: Path, lanes: list[LaneAdapter], sequence: int=1, preseed: int=0, replay_ledger: ReplayLedger|None=None, policy: SelectionPolicy|None=None) -> tuple[X6Receipt, bytes]:
    if sender_node == receiver_node:
        raise X6Refusal("cross-node canary requires distinct nodes")
    if not lanes:
        raise X6Refusal("at least one governed lane required")
    ledger=replay_ledger or ReplayLedger()
    manifest,envelope=create_envelope(data,sender_node,receiver_node,signer,sequence)
    verify_envelope(envelope,trusted_public_keys)
    ledger.admit(sender_node,receiver_node,envelope.sequence,envelope.nonce)
    received_manifest=_manifest_from_body(envelope.manifest_body)
    if received_manifest.manifest_digest != envelope.manifest_digest:
        raise X6Refusal("manifest digest mismatch")
    if received_manifest.object_digest != digest_bytes(data):
        raise X6Refusal("sender object root mismatch")
    chunks=tuple(data[c.offset:c.offset+c.size] for c in manifest.chunks)
    cas=FileCAS(receiver_cas_root)
    for ref,part in zip(manifest.chunks[:preseed],chunks[:preseed]):
        cas.put_verified(part,ref.digest)
    needed=Receiver(cas).negotiate(received_manifest).needed_indexes
    measurements=[]
    for lane in lanes:
        # Benchmark candidates against isolated CAS state so trials cannot pre-fill
        # the receiver's final admission store.
        with TemporaryDirectory(prefix="beast-x6-lane-") as td:
            trial_cas=FileCAS(Path(td))
            for ref,part in zip(manifest.chunks[:preseed],chunks[:preseed]):
                trial_cas.put_verified(part,ref.digest)
            measurements.append(_measure_lane(lane,received_manifest,Receiver(trial_cas),needed))
    selected=choose_lane(measurements,policy or SelectionPolicy())
    # Run the selected lane into the real receiver CAS to bind closure to the chosen route.
    selected_lane=next(l for l in lanes if l.name == selected.lane)
    final_receiver=Receiver(cas)
    still_needed=final_receiver.negotiate(received_manifest).needed_indexes
    seq=1
    for index in still_needed:
        ref=received_manifest.chunks[index]
        final_receiver.accept(received_manifest,index,selected_lane.fetch(index,ref.digest),seq)
        seq += 1
    reconstructed=final_receiver.reconstruct(received_manifest)
    root_ok=digest_bytes(reconstructed)==received_manifest.object_digest
    if not root_ok:
        raise X6Refusal("reconstructed object root mismatch")
    receipt=X6Receipt(
        phase="X6",
        sender_node=sender_node,
        receiver_node=receiver_node,
        manifest_digest=received_manifest.manifest_digest,
        object_digest=received_manifest.object_digest,
        signature_verified=True,
        sender_authorized=True,
        replay_safe=True,
        selected_lane=selected.lane,
        fallback_used=selected.lane != lanes[0].name,
        chunks_total=len(received_manifest.chunks),
        chunks_needed=len(needed),
        chunks_transmitted=len(still_needed),
        bytes_transmitted=sum(received_manifest.chunks[i].size for i in still_needed),
        bytes_avoided=received_manifest.object_size-sum(received_manifest.chunks[i].size for i in still_needed),
        reconstruction_verified=True,
        object_root_verified=True,
        receiver_cas_admitted=True,
        promotion_allowed=False,
        execution_allowed=False,
        raw_payload_retained_in_receipt=False,
        authority="cross_node_reconstruction_only",
    ).seal()
    return receipt,reconstructed
