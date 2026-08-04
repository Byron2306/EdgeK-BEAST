from __future__ import annotations

import html
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .residual_contracts import canonical_json, sha256_digest, utc_now_iso, validate_digest


class AssetKind(str, Enum):
    MASCOT_STATE = "mascot_state"
    DIAGRAM = "diagram"
    STATUS_CARD = "status_card"
    IDE_ASSET = "ide_asset"
    VISUAL_REGION = "visual_region"


class SceneOpcodeKind(str, Enum):
    PLACE_ASSET = "place_asset"
    DRAW_RECT = "draw_rect"
    DRAW_TEXT = "draw_text"
    DRAW_LINE = "draw_line"


@dataclass(frozen=True, slots=True)
class CanvasContract:
    width: int
    height: int
    background: str = "#00000000"

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("canvas dimensions must be positive")
        if not self.background.strip():
            raise ValueError("canvas background must not be empty")


@dataclass(frozen=True, slots=True)
class AssetRef:
    asset_id: str
    kind: AssetKind
    digest: str
    media_type: str
    width: int
    height: int
    source: str
    state: str = ""

    def __post_init__(self) -> None:
        if not self.asset_id.strip() or not self.media_type.strip() or not self.source.strip():
            raise ValueError("asset identity, media type, and source are required")
        if not isinstance(self.kind, AssetKind):
            object.__setattr__(self, "kind", AssetKind(self.kind))
        validate_digest(self.digest, field_name="asset_digest")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("asset dimensions must be positive")


@dataclass(frozen=True, slots=True)
class SignedAssetManifest:
    manifest_id: str
    assets: tuple[AssetRef, ...]
    signer_id: str
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.manifest_id.strip() or not self.signer_id.strip():
            raise ValueError("manifest_id and signer_id are required")
        ids = [asset.asset_id for asset in self.assets]
        if len(ids) != len(set(ids)):
            raise ValueError("asset ids must be unique")
        if not self.assets:
            raise ValueError("asset manifest cannot be empty")

    @property
    def unsigned_payload(self) -> Mapping[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "assets": self.assets,
            "signer_id": self.signer_id,
            "version": "beast.asset-manifest.v1",
        }

    @property
    def manifest_digest(self) -> str:
        return sha256_digest(self.unsigned_payload)

    def asset(self, asset_id: str) -> AssetRef:
        for item in self.assets:
            if item.asset_id == asset_id:
                return item
        raise KeyError(asset_id)


@dataclass(frozen=True, slots=True)
class SceneOpcode:
    kind: SceneOpcodeKind
    args: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SceneOpcodeKind):
            object.__setattr__(self, "kind", SceneOpcodeKind(self.kind))
        canonical_json(self.args)


@dataclass(frozen=True, slots=True)
class SceneCrystal:
    scene_id: str
    manifest_digest: str
    canvas: CanvasContract
    opcodes: tuple[SceneOpcode, ...]
    policy_digest: str
    verifier_id: str
    output_format: str = "image/svg+xml"

    def __post_init__(self) -> None:
        if not self.scene_id.strip() or not self.verifier_id.strip():
            raise ValueError("scene_id and verifier_id are required")
        validate_digest(self.manifest_digest, field_name="manifest_digest")
        validate_digest(self.policy_digest, field_name="policy_digest")
        if self.output_format != "image/svg+xml":
            raise ValueError("only deterministic SVG composition is supported")
        if not self.opcodes:
            raise ValueError("scene crystal requires compositor opcodes")

    @property
    def scene_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class SceneCompositionReceipt:
    scene_digest: str
    manifest_digest: str
    output_digest: str
    canvas_digest: str
    asset_provenance: tuple[tuple[str, str], ...]
    output_format: str
    verified: bool

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class SceneCapsule:
    capsule_id: str
    scene_id: str
    scene_digest: str
    manifest_digest: str
    composition_receipt_digest: str
    output_digest: str
    policy_digest: str
    canvas_digest: str
    asset_provenance: tuple[tuple[str, str], ...]
    output_format: str
    authority: str = "beast.scene-capsule.v1"
    maximum_authority: str = "render_only"
    network_scope: str = "none"
    provider_scope: str = "none"
    physical_scope: str = "none"
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.capsule_id.strip() or not self.scene_id.strip():
            raise ValueError("scene capsule requires capsule_id and scene_id")
        for name in (
            "scene_digest", "manifest_digest", "composition_receipt_digest",
            "output_digest", "policy_digest", "canvas_digest",
        ):
            validate_digest(getattr(self, name), field_name=name)
        for asset_id, digest in self.asset_provenance:
            if not asset_id.strip():
                raise ValueError("scene capsule asset provenance requires asset ids")
            validate_digest(digest, field_name="asset_provenance_digest")
        if self.output_format != "image/svg+xml":
            raise ValueError("scene capsule only supports deterministic SVG output")
        if self.authority != "beast.scene-capsule.v1":
            raise ValueError("scene capsule authority must be beast.scene-capsule.v1")
        if self.maximum_authority != "render_only":
            raise ValueError("scene capsule maximum authority must be render_only")
        if self.network_scope != "none" or self.provider_scope != "none" or self.physical_scope != "none":
            raise ValueError("scene capsule cannot grant network, provider, or physical authority")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now_iso())

    @property
    def capsule_digest(self) -> str:
        return sha256_digest(
            {
                "capsule_id": self.capsule_id,
                "scene_id": self.scene_id,
                "scene_digest": self.scene_digest,
                "manifest_digest": self.manifest_digest,
                "composition_receipt_digest": self.composition_receipt_digest,
                "output_digest": self.output_digest,
                "policy_digest": self.policy_digest,
                "canvas_digest": self.canvas_digest,
                "asset_provenance": self.asset_provenance,
                "output_format": self.output_format,
                "authority": self.authority,
                "maximum_authority": self.maximum_authority,
                "network_scope": self.network_scope,
                "provider_scope": self.provider_scope,
                "physical_scope": self.physical_scope,
            }
        )


@dataclass(frozen=True, slots=True)
class VisualCorpusReceipt:
    scene_count: int
    deterministic_count: int
    provenance_verified_count: int
    deterministic_rate: float
    threshold: float
    passed: bool
    scene_receipt_digests: tuple[str, ...]

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


class DeterministicSceneCompositor:
    def compose(self, scene: SceneCrystal, manifest: SignedAssetManifest) -> tuple[str, SceneCompositionReceipt]:
        if scene.manifest_digest != manifest.manifest_digest:
            raise ValueError("scene manifest digest does not match asset manifest")
        assets = {asset.asset_id: asset for asset in manifest.assets}
        body: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{scene.canvas.width}" height="{scene.canvas.height}" viewBox="0 0 {scene.canvas.width} {scene.canvas.height}">',
            f'<rect width="100%" height="100%" fill="{html.escape(scene.canvas.background)}"/>',
        ]
        provenance: list[tuple[str, str]] = []
        for opcode in scene.opcodes:
            body.append(self._render_opcode(opcode, scene.canvas, assets, provenance))
        body.append("</svg>")
        output = "".join(body)
        asset_provenance = tuple(sorted(set(provenance)))
        receipt = SceneCompositionReceipt(
            scene_digest=scene.scene_digest,
            manifest_digest=manifest.manifest_digest,
            output_digest=sha256_digest(output),
            canvas_digest=sha256_digest(scene.canvas),
            asset_provenance=asset_provenance,
            output_format=scene.output_format,
            verified=True,
        )
        return output, receipt

    def compose_capsule(
        self,
        scene: SceneCrystal,
        manifest: SignedAssetManifest,
        *,
        capsule_id: str | None = None,
    ) -> tuple[str, SceneCompositionReceipt, SceneCapsule]:
        output, receipt = self.compose(scene, manifest)
        return output, receipt, seal_scene_capsule(scene, manifest, receipt, capsule_id=capsule_id)

    def _render_opcode(
        self,
        opcode: SceneOpcode,
        canvas: CanvasContract,
        assets: Mapping[str, AssetRef],
        provenance: list[tuple[str, str]],
    ) -> str:
        args = dict(opcode.args)
        if opcode.kind is SceneOpcodeKind.PLACE_ASSET:
            asset_id = str(args.get("asset_id") or "")
            if asset_id not in assets:
                raise ValueError("scene references unknown asset: " + asset_id)
            asset = assets[asset_id]
            x, y = self._number(args, "x"), self._number(args, "y")
            width = self._number(args, "width", default=asset.width)
            height = self._number(args, "height", default=asset.height)
            self._require_bounds(canvas, x, y, width, height)
            provenance.append((asset.asset_id, asset.digest))
            href = html.escape(f"asset:{asset.asset_id}#{asset.digest}")
            return f'<image href="{href}" x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}"/>'
        if opcode.kind is SceneOpcodeKind.DRAW_RECT:
            x, y = self._number(args, "x"), self._number(args, "y")
            width, height = self._number(args, "width"), self._number(args, "height")
            self._require_bounds(canvas, x, y, width, height)
            return (
                f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" '
                f'rx="{self._number(args, "rx", default=0):g}" fill="{html.escape(str(args.get("fill") or "#000"))}" '
                f'stroke="{html.escape(str(args.get("stroke") or "none"))}"/>'
            )
        if opcode.kind is SceneOpcodeKind.DRAW_LINE:
            x1, y1 = self._number(args, "x1"), self._number(args, "y1")
            x2, y2 = self._number(args, "x2"), self._number(args, "y2")
            self._require_point(canvas, x1, y1)
            self._require_point(canvas, x2, y2)
            return (
                f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" '
                f'stroke="{html.escape(str(args.get("stroke") or "#fff"))}" '
                f'stroke-width="{self._number(args, "stroke_width", default=1):g}"/>'
            )
        if opcode.kind is SceneOpcodeKind.DRAW_TEXT:
            x, y = self._number(args, "x"), self._number(args, "y")
            self._require_point(canvas, x, y)
            text = html.escape(str(args.get("text") or ""))
            size = self._number(args, "font_size", default=14)
            return f'<text x="{x:g}" y="{y:g}" font-size="{size:g}" fill="{html.escape(str(args.get("fill") or "#fff"))}">{text}</text>'
        raise ValueError("unsupported scene opcode")

    @staticmethod
    def _number(args: Mapping[str, Any], name: str, *, default: float | None = None) -> float:
        value = args.get(name, default)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"scene opcode field {name} must be numeric")
        return float(value)

    @staticmethod
    def _require_bounds(canvas: CanvasContract, x: float, y: float, width: float, height: float) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("scene opcode dimensions must be positive")
        if x < 0 or y < 0 or x + width > canvas.width or y + height > canvas.height:
            raise ValueError("scene opcode exceeds canvas bounds")

    @staticmethod
    def _require_point(canvas: CanvasContract, x: float, y: float) -> None:
        if x < 0 or y < 0 or x > canvas.width or y > canvas.height:
            raise ValueError("scene point exceeds canvas bounds")


def default_beast_asset_manifest() -> SignedAssetManifest:
    assets = (
        _asset("beast.mascot.idle", AssetKind.MASCOT_STATE, 128, 128, "app/cli/assets/sprites/mascot_frames.json", state="idle"),
        _asset("beast.diagram.node", AssetKind.DIAGRAM, 96, 56, "beast://diagram/node"),
        _asset("beast.status.card", AssetKind.STATUS_CARD, 240, 96, "beast://status/card"),
        _asset("beast.ide.panel", AssetKind.IDE_ASSET, 320, 180, "beast://ide/panel"),
    )
    return SignedAssetManifest("beast-default-visual-assets-v1", assets, signer_id="beast.visual.local")


def run_visual_corpus(
    scenes: tuple[SceneCrystal, ...],
    manifest: SignedAssetManifest,
    *,
    threshold: float = 0.75,
    compositor: DeterministicSceneCompositor | None = None,
) -> VisualCorpusReceipt:
    if not scenes:
        raise ValueError("visual corpus cannot be empty")
    if threshold <= 0 or threshold > 1:
        raise ValueError("visual corpus threshold must be within (0, 1]")
    engine = compositor or DeterministicSceneCompositor()
    deterministic = 0
    provenance_verified = 0
    receipt_digests: list[str] = []
    for scene in scenes:
        _svg, receipt = engine.compose(scene, manifest)
        _svg_again, receipt_again = engine.compose(scene, manifest)
        stable = receipt.output_digest == receipt_again.output_digest
        expected_assets = tuple(
            sorted(
                {
                    (str(opcode.args.get("asset_id")), manifest.asset(str(opcode.args.get("asset_id"))).digest)
                    for opcode in scene.opcodes
                    if opcode.kind is SceneOpcodeKind.PLACE_ASSET
                }
            )
        )
        provenance_ok = receipt.asset_provenance == expected_assets
        deterministic += int(stable)
        provenance_verified += int(provenance_ok)
        receipt_digests.append(receipt.receipt_digest)
    rate = deterministic / len(scenes)
    return VisualCorpusReceipt(
        scene_count=len(scenes),
        deterministic_count=deterministic,
        provenance_verified_count=provenance_verified,
        deterministic_rate=rate,
        threshold=threshold,
        passed=rate >= threshold and provenance_verified == len(scenes),
        scene_receipt_digests=tuple(receipt_digests),
    )


def seal_scene_capsule(
    scene: SceneCrystal,
    manifest: SignedAssetManifest,
    receipt: SceneCompositionReceipt,
    *,
    capsule_id: str | None = None,
) -> SceneCapsule:
    if scene.manifest_digest != manifest.manifest_digest:
        raise ValueError("scene capsule manifest digest does not match asset manifest")
    if receipt.scene_digest != scene.scene_digest:
        raise ValueError("scene capsule receipt does not bind the same scene")
    if receipt.manifest_digest != manifest.manifest_digest:
        raise ValueError("scene capsule receipt does not bind the same manifest")
    if receipt.canvas_digest != sha256_digest(scene.canvas):
        raise ValueError("scene capsule receipt does not bind the same canvas")
    if receipt.output_format != scene.output_format:
        raise ValueError("scene capsule receipt does not bind the same output format")
    expected_assets = tuple(
        sorted(
            {
                (str(opcode.args.get("asset_id")), manifest.asset(str(opcode.args.get("asset_id"))).digest)
                for opcode in scene.opcodes
                if opcode.kind is SceneOpcodeKind.PLACE_ASSET
            }
        )
    )
    if receipt.asset_provenance != expected_assets:
        raise ValueError("scene capsule receipt asset provenance mismatch")
    return SceneCapsule(
        capsule_id=capsule_id or f"scene-capsule:{scene.scene_id}",
        scene_id=scene.scene_id,
        scene_digest=scene.scene_digest,
        manifest_digest=manifest.manifest_digest,
        composition_receipt_digest=receipt.receipt_digest,
        output_digest=receipt.output_digest,
        policy_digest=scene.policy_digest,
        canvas_digest=receipt.canvas_digest,
        asset_provenance=receipt.asset_provenance,
        output_format=scene.output_format,
    )


def _asset(asset_id: str, kind: AssetKind, width: int, height: int, source: str, *, state: str = "") -> AssetRef:
    digest = sha256_digest(
        {
            "asset_id": asset_id,
            "kind": kind,
            "width": width,
            "height": height,
            "source": source,
            "state": state,
        }
    )
    return AssetRef(asset_id, kind, digest, "image/svg+xml", width, height, source, state)
