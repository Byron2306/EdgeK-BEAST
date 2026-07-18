import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app.kernel.compute.crystalbench_authoring import SealedManifestSigner
from app.kernel.compute.crystalbench_authoring import CrystalBenchAuthoringVault,CrystalBenchDraft
def test_private_authoring_freezes_commitments_without_exposing_contents(tmp_path):
 v=CrystalBenchAuthoringVault(tmp_path); d=CrystalBenchDraft('original-1','async_repair','C3','python',True,b'repo-private',b'task-private',b'verifier-private')
 t=v.freeze(d); assert v.verify_frozen(t) and t.hidden_verifier_digest.startswith('sha256:')
 with pytest.raises(FileExistsError): v.freeze(d)
def test_sealed_manifest_signature_detects_tampering():
 s=SealedManifestSigner(Ed25519PrivateKey.generate()).sign({'manifest_digest':'sha256:x'})
 assert SealedManifestSigner.verify(s)
 assert not SealedManifestSigner.verify({**s,'manifest_digest':'sha256:y'})
