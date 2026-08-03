import pytest

from app.kernel.commons.synthesis_space import (
    SynthesisCapabilityKind,
    build_synthesis_space_package,
    validate_synthesis_space_manifest,
)
from app.kernel.compute.residual_contracts import sha256_digest


def _package(kind=SynthesisCapabilityKind.SEMANTIC):
    return build_synthesis_space_package(
        space_id=f"beast/{kind.value}-synthesis",
        capability_kind=kind,
        artifact_digests=(sha256_digest({"artifact": kind.value}),),
        schemas={"request": {"type": "object"}, "receipt": {"type": "object"}},
        verifier={"verifier_id": f"{kind.value}-verifier", "command": "pytest"},
        negative_cases=({"case": "stale-world", "expect": "reject"},),
        replay_corpus=({"input": "status", "expect": "verified"},),
        evidence_digests=(sha256_digest({"evidence": kind.value}),),
        reproducibility={
            "engine": "local-cpu",
            "seed": 7,
            "dependencies": ("pytest",),
        },
    )


def test_synthesis_space_package_contains_c1_required_sections_and_round_trips():
    package = _package()
    manifest = package.to_manifest()

    assert manifest["authority"] == "remote_hypothesis"
    assert manifest["maximum_authority"] == "verify_only"
    assert manifest["local_reproduction_required"] is True
    assert validate_synthesis_space_manifest(manifest) == package


def test_visual_synthesis_space_package_is_still_hypothesis_only():
    manifest = _package(SynthesisCapabilityKind.VISUAL).to_manifest()

    assert validate_synthesis_space_manifest(manifest).capability_kind is SynthesisCapabilityKind.VISUAL
    manifest["maximum_authority"] = "execute"
    with pytest.raises(PermissionError, match="verify-only hypotheses"):
        validate_synthesis_space_manifest(manifest)


def test_synthesis_space_rejects_missing_negative_cases_and_digest_tamper():
    with pytest.raises(ValueError, match="negative_cases"):
        build_synthesis_space_package(
            space_id="beast/bad",
            capability_kind=SynthesisCapabilityKind.SEMANTIC,
            artifact_digests=(sha256_digest({"artifact": "semantic"}),),
            schemas={"request": {"type": "object"}},
            verifier={"verifier_id": "semantic-verifier"},
            negative_cases=(),
            replay_corpus=({"input": "status"},),
            evidence_digests=(sha256_digest({"evidence": "semantic"}),),
            reproducibility={"engine": "local-cpu"},
        )

    manifest = _package().to_manifest()
    manifest["schemas"] = {"request": {"type": "tampered"}}
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_synthesis_space_manifest(manifest)
