"""Private task authoring and immutable freeze support for CrystalBench."""
from __future__ import annotations
import base64,hashlib,json,time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from app.kernel.compute.crystal_frontier_crucible import SealedTask, HiddenVerifierVault
from app.kernel.sensorium.contracts_hash import content_hash
from app.kernel.commons.signature_verifier import canonical_bytes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey

@dataclass(frozen=True)
class CrystalBenchDraft:
    task_id: str; family: str; tier: str; language: str; expected_eligible: bool
    repository_snapshot: bytes; task_specification: bytes; hidden_verifier: bytes

class CrystalBenchAuthoringVault:
    def __init__(self, root: Path): self.root=Path(root); self.verifiers=HiddenVerifierVault()
    def freeze(self,draft: CrystalBenchDraft) -> SealedTask:
        private=self.root/'private-tasks'/draft.task_id
        if private.exists(): raise FileExistsError(f'task already frozen: {draft.task_id}')
        private.mkdir(parents=True)
        (private/'repository.snapshot').write_bytes(draft.repository_snapshot)
        (private/'task.md').write_bytes(draft.task_specification)
        verifier=self.verifiers.commit(self.root,draft.task_id,draft.hidden_verifier)
        commitment={"task_id":draft.task_id,"family":draft.family,"tier":draft.tier,"language":draft.language,"expected_eligible":draft.expected_eligible,"repository_digest":"sha256:"+hashlib.sha256(draft.repository_snapshot).hexdigest(),"specification_digest":"sha256:"+hashlib.sha256(draft.task_specification).hexdigest(),"hidden_verifier_digest":verifier}
        (private/'freeze.json').write_text(json.dumps({**commitment,'freeze_digest':content_hash(commitment)},indent=2,sort_keys=True)+'\n')
        return SealedTask(**commitment)
    def verify_frozen(self, task: SealedTask) -> bool:
        private=self.root/'private-tasks'/task.task_id
        if not private.is_dir(): return False
        return ('sha256:'+hashlib.sha256((private/'repository.snapshot').read_bytes()).hexdigest()==task.repository_digest and 'sha256:'+hashlib.sha256((private/'task.md').read_bytes()).hexdigest()==task.specification_digest and self.verifiers.verify(self.root,task.task_id,task.hidden_verifier_digest))

class SealedManifestSigner:
    def __init__(self, private_key: Ed25519PrivateKey): self.private_key=private_key
    def sign(self, manifest: dict[str,Any]) -> dict[str,Any]:
        payload={**manifest,'sealed_at':time.time()}; signature=self.private_key.sign(canonical_bytes(payload))
        return {**payload,'signature_alg':'Ed25519','signer_public_key':base64.b64encode(self.private_key.public_key().public_bytes_raw()).decode(),'signature':base64.b64encode(signature).decode()}
    @staticmethod
    def verify(signed: dict[str,Any]) -> bool:
        try:
            signature=base64.b64decode(signed['signature']); public=Ed25519PublicKey.from_public_bytes(base64.b64decode(signed['signer_public_key'])); payload={k:v for k,v in signed.items() if k not in {'signature','signature_alg','signer_public_key'}}; public.verify(signature,canonical_bytes(payload)); return True
        except Exception: return False
