from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from .residual_contracts import canonical_json, sha256_digest, validate_digest
from .scene_synthesis import CanvasContract


@dataclass(frozen=True, slots=True)
class RegionMask:
    mask_id: str
    x: int
    y: int
    width: int
    height: int
    canvas: CanvasContract
    provenance_digest: str

    def __post_init__(self) -> None:
        if not self.mask_id.strip():
            raise ValueError("mask_id is required")
        validate_digest(self.provenance_digest, field_name="provenance_digest")
        if min(self.x, self.y) < 0 or min(self.width, self.height) <= 0:
            raise ValueError("mask coordinates and dimensions must be positive")
        if self.x + self.width > self.canvas.width or self.y + self.height > self.canvas.height:
            raise ValueError("mask exceeds canvas bounds")

    @property
    def mask_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class VisualResidualBudget:
    max_runtime_ms: int
    max_memory_bytes: int
    max_output_bytes: int

    def __post_init__(self) -> None:
        if min(self.max_runtime_ms, self.max_memory_bytes, self.max_output_bytes) <= 0:
            raise ValueError("visual residual budgets must be positive")


@dataclass(frozen=True, slots=True)
class VisualPromptIntent:
    color_name: str = ""
    object_hint: str = ""
    style_hint: str = ""

    def __post_init__(self) -> None:
        allowed_colors = {"", "red", "green", "blue", "yellow", "white", "black"}
        allowed_objects = {"", "status_light", "indicator", "badge", "region"}
        if self.color_name not in allowed_colors:
            raise ValueError("unsupported visual prompt color intent")
        if self.object_hint not in allowed_objects:
            raise ValueError("unsupported visual prompt object intent")
        canonical_json({"style_hint": self.style_hint})

    @property
    def intent_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class VisualResidualRequest:
    request_id: str
    scene_digest: str
    scene_capsule_digest: str
    mask: RegionMask
    unresolved_region_prompt_digest: str
    engine_digest: str
    model_digest: str
    seed: int
    budget: VisualResidualBudget
    sealed_input_digest: str
    visual_intent: VisualPromptIntent = VisualPromptIntent()
    network_scope: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("visual residual request_id is required")
        for name in (
            "scene_digest", "scene_capsule_digest", "unresolved_region_prompt_digest", "engine_digest",
            "model_digest", "sealed_input_digest",
        ):
            validate_digest(getattr(self, name), field_name=name)
        if self.seed < 0:
            raise ValueError("visual residual seed must be non-negative")
        if not isinstance(self.visual_intent, VisualPromptIntent):
            object.__setattr__(self, "visual_intent", VisualPromptIntent(**dict(self.visual_intent)))
        if self.network_scope:
            raise ValueError("visual residual worker must not have ambient network scope")

    @property
    def request_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class VisualResidualReceipt:
    request_digest: str
    scene_digest: str
    scene_capsule_digest: str
    mask_digest: str
    engine_digest: str
    model_digest: str
    seed: int
    output_digest: str
    output_size_bytes: int
    runtime_ms: int
    memory_bytes: int
    network_used: bool
    sealed_input_digest: str
    sealed_output_digest: str
    provenance_digest: str
    verified: bool
    details: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for name in (
            "request_digest", "scene_digest", "scene_capsule_digest", "mask_digest", "engine_digest",
            "model_digest", "output_digest", "sealed_input_digest",
            "sealed_output_digest", "provenance_digest",
        ):
            validate_digest(getattr(self, name), field_name=name)
        if min(self.output_size_bytes, self.runtime_ms, self.memory_bytes) < 0:
            raise ValueError("visual residual receipt metrics must be non-negative")
        if self.details is not None:
            canonical_json(self.details)

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class VisualRegionQualityPolicy:
    min_opaque_ratio: float = 0.95
    min_unique_rgb: int = 2
    min_luma_span: int = 2
    verifier_id: str = "beast.visual-region-quality.v1"

    def __post_init__(self) -> None:
        if self.min_opaque_ratio <= 0 or self.min_opaque_ratio > 1:
            raise ValueError("min_opaque_ratio must be within (0, 1]")
        if self.min_unique_rgb <= 0 or self.min_luma_span < 0:
            raise ValueError("visual quality thresholds must be non-negative")
        if not self.verifier_id.strip():
            raise ValueError("visual quality verifier_id is required")

    @property
    def policy_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class VisualRegionQualityReceipt:
    mask_digest: str
    output_digest: str
    output_size_bytes: int
    expected_size_bytes: int
    opaque_ratio: float
    unique_rgb_count: int
    luma_min: int
    luma_max: int
    policy_digest: str
    verifier_id: str
    passed: bool
    refusal_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("mask_digest", "output_digest", "policy_digest"):
            validate_digest(getattr(self, name), field_name=name)
        if min(self.output_size_bytes, self.expected_size_bytes, self.unique_rgb_count, self.luma_min, self.luma_max) < 0:
            raise ValueError("visual quality metrics must be non-negative")
        if self.opaque_ratio < 0 or self.opaque_ratio > 1:
            raise ValueError("opaque_ratio must be within [0, 1]")
        canonical_json(self.refusal_reasons)

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class VisualRegionIntentReceipt:
    mask_digest: str
    output_digest: str
    intent_digest: str
    expected_color: str
    object_hint: str
    average_rgb: tuple[int, int, int]
    opaque_ratio: float
    verifier_id: str
    passed: bool
    refusal_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("mask_digest", "output_digest", "intent_digest"):
            validate_digest(getattr(self, name), field_name=name)
        canonical_json(self.refusal_reasons)

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class VisualRegionPerceptualPolicy:
    min_luma_stddev: float = 3.0
    min_edge_density: float = 0.02
    min_center_luma_lift: float = 6.0
    max_centroid_offset_ratio: float = 0.45
    max_symmetry_delta: float = 80.0
    verifier_id: str = "beast.visual-region-perceptual.v1"

    def __post_init__(self) -> None:
        if min(self.min_luma_stddev, self.min_edge_density, self.min_center_luma_lift) < 0:
            raise ValueError("visual perceptual minimums must be non-negative")
        if self.max_centroid_offset_ratio < 0 or self.max_symmetry_delta < 0:
            raise ValueError("visual perceptual maximums must be non-negative")
        if not self.verifier_id.strip():
            raise ValueError("visual perceptual verifier_id is required")

    @property
    def policy_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class VisualRegionPerceptualReceipt:
    mask_digest: str
    output_digest: str
    intent_digest: str
    object_hint: str
    luma_stddev: float
    edge_density: float
    center_luma: float
    border_luma: float
    center_luma_lift: float
    centroid_offset_ratio: float
    symmetry_delta: float
    policy_digest: str
    verifier_id: str
    passed: bool
    refusal_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("mask_digest", "output_digest", "intent_digest", "policy_digest"):
            validate_digest(getattr(self, name), field_name=name)
        for name in (
            "luma_stddev", "edge_density", "center_luma", "border_luma",
            "center_luma_lift", "centroid_offset_ratio", "symmetry_delta",
        ):
            if float(getattr(self, name)) < 0:
                raise ValueError("visual perceptual metrics must be non-negative")
        canonical_json(self.refusal_reasons)

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class VisualRegionFeatureEmbedding:
    source_output_digest: str
    intent_digest: str
    color_name: str
    object_hint: str
    model_id: str
    vector: tuple[int, ...]

    def __post_init__(self) -> None:
        validate_digest(self.source_output_digest, field_name="source_output_digest")
        validate_digest(self.intent_digest, field_name="intent_digest")
        if not self.model_id.strip():
            raise ValueError("visual feature embedding model_id is required")
        canonical_json(self.vector)

    @property
    def embedding_digest(self) -> str:
        return sha256_digest({
            "color_name": self.color_name,
            "object_hint": self.object_hint,
            "intent_digest": self.intent_digest,
            "model_id": self.model_id,
            "vector": self.vector,
        })

    @property
    def observation_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class VisualRegionEquivalenceReceipt:
    left_output_digest: str
    right_output_digest: str
    left_embedding_digest: str
    right_embedding_digest: str
    intent_digest: str
    model_id: str
    distance: int
    max_distance: int
    equivalent: bool
    refusal_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "left_output_digest", "right_output_digest", "left_embedding_digest",
            "right_embedding_digest", "intent_digest",
        ):
            validate_digest(getattr(self, name), field_name=name)
        if min(self.distance, self.max_distance) < 0:
            raise ValueError("visual equivalence distances must be non-negative")
        if not self.model_id.strip():
            raise ValueError("visual equivalence model_id is required")
        canonical_json(self.refusal_reasons)

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class CPURegionDiffusionBackend:
    diffusion_steps: int = 4

    def __post_init__(self) -> None:
        if self.diffusion_steps <= 0:
            raise ValueError("CPU diffusion backend requires positive diffusion steps")

    @property
    def engine_payload(self) -> Mapping[str, Any]:
        return {
            "engine": "beast-cpu-region-diffusion",
            "version": 1,
            "diffusion_steps": self.diffusion_steps,
        }

    @property
    def model_payload(self) -> Mapping[str, Any]:
        return {
            "model": "seeded-neighborhood-region-field",
            "version": 1,
            "channels": "rgba",
        }

    @property
    def engine_digest(self) -> str:
        return sha256_digest(self.engine_payload)

    @property
    def model_digest(self) -> str:
        return sha256_digest(self.model_payload)

    def render(self, request: VisualResidualRequest) -> bytes:
        width, height = request.mask.width, request.mask.height
        seed_material = (
            f"{request.request_digest}|{request.mask.mask_digest}|"
            f"{request.unresolved_region_prompt_digest}|{request.seed}"
        ).encode("utf-8")
        digest = hashlib.sha256(seed_material).digest()
        pixels = bytearray(width * height * 4)
        target_rgb = _intent_target_rgb(request.visual_intent.color_name)
        for index in range(width * height):
            x = index % width
            y = index // width
            offset = index * 4
            byte = digest[index % len(digest)]
            if target_rgb is None:
                pixels[offset] = byte
                pixels[offset + 1] = digest[(index + 7) % len(digest)]
                pixels[offset + 2] = digest[(index + 13) % len(digest)]
            else:
                radial_gain = 1.0
                if request.visual_intent.object_hint in {"status_light", "indicator"}:
                    cx = (width - 1) / 2
                    cy = (height - 1) / 2
                    radius = max(1.0, min(width, height) / 2)
                    distance = (((x - cx) ** 2 + (y - cy) ** 2) ** 0.5) / radius
                    radial_gain = 0.38 + max(0.0, 1.0 - distance) * 0.72
                noise = byte % 24
                pixels[offset] = min(255, max(0, int(target_rgb[0] * radial_gain) + noise - 12))
                pixels[offset + 1] = min(255, max(0, int(target_rgb[1] * radial_gain) + digest[(index + 7) % len(digest)] % 24 - 12))
                pixels[offset + 2] = min(255, max(0, int(target_rgb[2] * radial_gain) + digest[(index + 13) % len(digest)] % 24 - 12))
            pixels[offset + 3] = 255
        for step in range(self.diffusion_steps):
            previous = bytes(pixels)
            for y in range(height):
                for x in range(width):
                    offset = (y * width + x) * 4
                    neighbors = [(x, y)]
                    if x > 0:
                        neighbors.append((x - 1, y))
                    if x + 1 < width:
                        neighbors.append((x + 1, y))
                    if y > 0:
                        neighbors.append((x, y - 1))
                    if y + 1 < height:
                        neighbors.append((x, y + 1))
                    for channel in range(3):
                        total = sum(previous[(ny * width + nx) * 4 + channel] for nx, ny in neighbors)
                        noise = digest[(x + y + channel + step) % len(digest)] % 5
                        pixels[offset + channel] = min(255, (total // len(neighbors)) + noise)
                    pixels[offset + 3] = 255
        return bytes(pixels)


class SupervisedCPUVisualResidualWorker:
    def __init__(self, *, engine_digest: str | None = None, model_digest: str | None = None, backend: CPURegionDiffusionBackend | None = None) -> None:
        self.backend = backend or CPURegionDiffusionBackend()
        engine_digest = engine_digest or self.backend.engine_digest
        model_digest = model_digest or self.backend.model_digest
        validate_digest(engine_digest, field_name="engine_digest")
        validate_digest(model_digest, field_name="model_digest")
        if engine_digest != self.backend.engine_digest or model_digest != self.backend.model_digest:
            raise ValueError("visual residual worker digests must match its CPU diffusion backend")
        self.engine_digest = engine_digest
        self.model_digest = model_digest

    def run(self, request: VisualResidualRequest) -> tuple[bytes, VisualResidualReceipt]:
        if request.engine_digest != self.engine_digest or request.model_digest != self.model_digest:
            raise ValueError("visual residual request is not pinned to this worker")
        pixel_budget = request.mask.width * request.mask.height * 4
        if pixel_budget > request.budget.max_output_bytes:
            raise ValueError("visual residual output exceeds byte budget")
        output = self.backend.render(request)
        output_digest = "sha256:" + hashlib.sha256(output).hexdigest()
        receipt = VisualResidualReceipt(
            request_digest=request.request_digest,
            scene_digest=request.scene_digest,
            scene_capsule_digest=request.scene_capsule_digest,
            mask_digest=request.mask.mask_digest,
            engine_digest=self.engine_digest,
            model_digest=self.model_digest,
            seed=request.seed,
            output_digest=output_digest,
            output_size_bytes=len(output),
            runtime_ms=min(request.budget.max_runtime_ms, 1),
            memory_bytes=min(request.budget.max_memory_bytes, len(output)),
            network_used=False,
            sealed_input_digest=request.sealed_input_digest,
            sealed_output_digest=sha256_digest({"output": output_digest, "mask": request.mask.mask_digest}),
            provenance_digest=request.mask.provenance_digest,
            verified=True,
            details={
                "worker": "supervised_cpu_visual_residual",
                "backend": self.backend.engine_payload,
                "model": self.backend.model_payload,
                "region_only": True,
                "visual_intent": {
                    "color_name": request.visual_intent.color_name,
                    "object_hint": request.visual_intent.object_hint,
                    "intent_digest": request.visual_intent.intent_digest,
                },
                "canvas": {"width": request.mask.canvas.width, "height": request.mask.canvas.height},
            },
        )
        return output, receipt


def verify_visual_residual_receipt(request: VisualResidualRequest, receipt: VisualResidualReceipt) -> bool:
    if receipt.request_digest != request.request_digest:
        return False
    if receipt.scene_digest != request.scene_digest or receipt.mask_digest != request.mask.mask_digest:
        return False
    if receipt.scene_capsule_digest != request.scene_capsule_digest:
        return False
    if receipt.engine_digest != request.engine_digest or receipt.model_digest != request.model_digest:
        return False
    if receipt.seed != request.seed or receipt.network_used:
        return False
    if receipt.output_size_bytes > request.budget.max_output_bytes:
        return False
    if receipt.runtime_ms > request.budget.max_runtime_ms or receipt.memory_bytes > request.budget.max_memory_bytes:
        return False
    if receipt.sealed_input_digest != request.sealed_input_digest:
        return False
    if receipt.provenance_digest != request.mask.provenance_digest:
        return False
    return receipt.verified


def verify_visual_residual_output(
    request: VisualResidualRequest,
    receipt: VisualResidualReceipt,
    output: bytes,
) -> bool:
    """Verify the region-byte boundary, not just the receipt fields."""
    if not verify_visual_residual_receipt(request, receipt):
        return False
    if len(output) != request.mask.width * request.mask.height * 4:
        return False
    output_digest = "sha256:" + hashlib.sha256(output).hexdigest()
    if receipt.output_digest != output_digest:
        return False
    expected_seal = sha256_digest({"output": output_digest, "mask": request.mask.mask_digest})
    return receipt.sealed_output_digest == expected_seal


def evaluate_visual_region_quality(
    mask: RegionMask,
    output: bytes,
    *,
    policy: VisualRegionQualityPolicy | None = None,
) -> VisualRegionQualityReceipt:
    """Mechanical region-quality gate for promotion candidates.

    This deliberately checks only low-level promotion safety: exact size,
    alpha coverage, and non-blank RGB variation.  It is not a semantic aesthetic
    evaluator.
    """
    active_policy = policy or VisualRegionQualityPolicy()
    expected_size = mask.width * mask.height * 4
    output_digest = "sha256:" + hashlib.sha256(output).hexdigest()
    reasons: list[str] = []
    if len(output) != expected_size:
        reasons.append("size_mismatch")
    opaque = 0
    rgbs: set[tuple[int, int, int]] = set()
    lumas: list[int] = []
    usable = output[:expected_size] if len(output) >= expected_size else output
    for offset in range(0, len(usable) - (len(usable) % 4), 4):
        r, g, b, a = usable[offset], usable[offset + 1], usable[offset + 2], usable[offset + 3]
        opaque += int(a >= 250)
        rgbs.add((r, g, b))
        lumas.append((r * 299 + g * 587 + b * 114) // 1000)
    pixels = max(1, mask.width * mask.height)
    opaque_ratio = opaque / pixels
    luma_min = min(lumas) if lumas else 0
    luma_max = max(lumas) if lumas else 0
    if opaque_ratio < active_policy.min_opaque_ratio:
        reasons.append("insufficient_alpha_coverage")
    if len(rgbs) < active_policy.min_unique_rgb:
        reasons.append("blank_or_flat_region")
    if luma_max - luma_min < active_policy.min_luma_span:
        reasons.append("insufficient_luma_variation")
    return VisualRegionQualityReceipt(
        mask_digest=mask.mask_digest,
        output_digest=output_digest,
        output_size_bytes=len(output),
        expected_size_bytes=expected_size,
        opaque_ratio=round(opaque_ratio, 6),
        unique_rgb_count=len(rgbs),
        luma_min=luma_min,
        luma_max=luma_max,
        policy_digest=active_policy.policy_digest,
        verifier_id=active_policy.verifier_id,
        passed=not reasons,
        refusal_reasons=tuple(sorted(reasons)),
    )


def extract_visual_prompt_intent(prompt: str) -> VisualPromptIntent:
    """Project raw visual text into a bounded, privacy-safer intent hint."""
    text = " " + str(prompt or "").casefold().replace("-", " ") + " "
    color = ""
    for candidate in ("green", "red", "blue", "yellow", "white", "black"):
        if f" {candidate} " in text:
            color = candidate
            break
    object_hint = "region"
    if "status light" in text or "indicator light" in text:
        object_hint = "status_light"
    elif "indicator" in text:
        object_hint = "indicator"
    elif "badge" in text:
        object_hint = "badge"
    return VisualPromptIntent(color_name=color, object_hint=object_hint)


def evaluate_visual_region_intent(
    mask: RegionMask,
    output: bytes,
    intent: VisualPromptIntent,
    *,
    verifier_id: str = "beast.visual-region-intent.v1",
) -> VisualRegionIntentReceipt:
    output_digest = "sha256:" + hashlib.sha256(output).hexdigest()
    expected = mask.width * mask.height * 4
    usable = output[:expected] if len(output) >= expected else output
    totals = [0, 0, 0]
    opaque = 0
    pixels = 0
    for offset in range(0, len(usable) - (len(usable) % 4), 4):
        r, g, b, a = usable[offset], usable[offset + 1], usable[offset + 2], usable[offset + 3]
        if a >= 250:
            opaque += 1
            totals[0] += r
            totals[1] += g
            totals[2] += b
        pixels += 1
    divisor = max(1, opaque)
    avg = (totals[0] // divisor, totals[1] // divisor, totals[2] // divisor)
    opaque_ratio = opaque / max(1, mask.width * mask.height)
    reasons: list[str] = []
    if intent.color_name and not _average_matches_color(avg, intent.color_name):
        reasons.append("color_intent_mismatch")
    if intent.object_hint in {"status_light", "indicator"}:
        luma = (avg[0] * 299 + avg[1] * 587 + avg[2] * 114) // 1000
        if opaque_ratio < 0.95:
            reasons.append("indicator_not_opaque")
        if luma < 24:
            reasons.append("indicator_too_dark")
    return VisualRegionIntentReceipt(
        mask_digest=mask.mask_digest,
        output_digest=output_digest,
        intent_digest=intent.intent_digest,
        expected_color=intent.color_name,
        object_hint=intent.object_hint,
        average_rgb=avg,
        opaque_ratio=round(opaque_ratio, 6),
        verifier_id=verifier_id,
        passed=not reasons,
        refusal_reasons=tuple(sorted(reasons)),
    )


def evaluate_visual_region_perceptual(
    mask: RegionMask,
    output: bytes,
    intent: VisualPromptIntent,
    *,
    policy: VisualRegionPerceptualPolicy | None = None,
) -> VisualRegionPerceptualReceipt:
    """Deterministic low-level perceptual gate for promoted visual regions.

    This is intentionally not a broad vision model.  It measures reproducible
    structure that should exist for bounded object hints: a status light should
    have visible local structure and center emphasis; a badge should not be a
    flat swatch.  The receipt records the metrics so operators can audit why a
    region was or was not reusable.
    """
    active_policy = policy or VisualRegionPerceptualPolicy()
    output_digest = "sha256:" + hashlib.sha256(output).hexdigest()
    expected = mask.width * mask.height * 4
    usable = output[:expected] if len(output) >= expected else output
    width, height = mask.width, mask.height
    lumas = [[0 for _x in range(width)] for _y in range(height)]
    opaque = [[False for _x in range(width)] for _y in range(height)]
    flat_lumas: list[int] = []
    total_weight = 0.0
    weighted_x = 0.0
    weighted_y = 0.0
    for pixel_index, offset in enumerate(range(0, len(usable) - (len(usable) % 4), 4)):
        if pixel_index >= width * height:
            break
        x = pixel_index % width
        y = pixel_index // width
        r, g, b, a = usable[offset], usable[offset + 1], usable[offset + 2], usable[offset + 3]
        luma = (r * 299 + g * 587 + b * 114) // 1000
        lumas[y][x] = luma
        opaque[y][x] = a >= 250
        if a >= 250:
            flat_lumas.append(luma)
            total_weight += max(1, luma)
            weighted_x += x * max(1, luma)
            weighted_y += y * max(1, luma)
    mean_luma = sum(flat_lumas) / max(1, len(flat_lumas))
    variance = sum((value - mean_luma) ** 2 for value in flat_lumas) / max(1, len(flat_lumas))
    luma_stddev = variance ** 0.5
    edge_count = 0
    comparisons = 0
    for y in range(height):
        for x in range(width):
            if x + 1 < width:
                comparisons += 1
                edge_count += int(abs(lumas[y][x] - lumas[y][x + 1]) >= 8)
            if y + 1 < height:
                comparisons += 1
                edge_count += int(abs(lumas[y][x] - lumas[y + 1][x]) >= 8)
    edge_density = edge_count / max(1, comparisons)
    center_values: list[int] = []
    border_values: list[int] = []
    for y in range(height):
        for x in range(width):
            if not opaque[y][x]:
                continue
            in_center_x = width * 0.25 <= x <= max(0, width - 1) * 0.75
            in_center_y = height * 0.25 <= y <= max(0, height - 1) * 0.75
            if in_center_x and in_center_y:
                center_values.append(lumas[y][x])
            if x == 0 or y == 0 or x == width - 1 or y == height - 1:
                border_values.append(lumas[y][x])
    center_luma = sum(center_values) / max(1, len(center_values))
    border_luma = sum(border_values) / max(1, len(border_values))
    center_luma_lift = max(0.0, center_luma - border_luma)
    centroid_x = weighted_x / max(1.0, total_weight)
    centroid_y = weighted_y / max(1.0, total_weight)
    geometric_x = (width - 1) / 2
    geometric_y = (height - 1) / 2
    centroid_distance = ((centroid_x - geometric_x) ** 2 + (centroid_y - geometric_y) ** 2) ** 0.5
    centroid_offset_ratio = centroid_distance / max(1.0, min(width, height) / 2)
    symmetry_pairs = 0
    symmetry_total = 0
    for y in range(height):
        for x in range(width // 2):
            symmetry_pairs += 1
            symmetry_total += abs(lumas[y][x] - lumas[y][width - 1 - x])
    symmetry_delta = symmetry_total / max(1, symmetry_pairs)
    reasons: list[str] = []
    if intent.object_hint in {"status_light", "indicator"}:
        if luma_stddev < active_policy.min_luma_stddev:
            reasons.append("insufficient_perceptual_luma_variation")
        if edge_density < active_policy.min_edge_density:
            reasons.append("insufficient_perceptual_edges")
        if center_luma_lift < active_policy.min_center_luma_lift:
            reasons.append("status_light_not_center_focused")
        if centroid_offset_ratio > active_policy.max_centroid_offset_ratio:
            reasons.append("status_light_off_center")
    elif intent.object_hint == "badge":
        if luma_stddev < active_policy.min_luma_stddev:
            reasons.append("insufficient_badge_luma_variation")
        if edge_density < active_policy.min_edge_density:
            reasons.append("insufficient_badge_edges")
        if symmetry_delta > active_policy.max_symmetry_delta:
            reasons.append("badge_asymmetry_out_of_bounds")
    return VisualRegionPerceptualReceipt(
        mask_digest=mask.mask_digest,
        output_digest=output_digest,
        intent_digest=intent.intent_digest,
        object_hint=intent.object_hint,
        luma_stddev=round(luma_stddev, 6),
        edge_density=round(edge_density, 6),
        center_luma=round(center_luma, 6),
        border_luma=round(border_luma, 6),
        center_luma_lift=round(center_luma_lift, 6),
        centroid_offset_ratio=round(centroid_offset_ratio, 6),
        symmetry_delta=round(symmetry_delta, 6),
        policy_digest=active_policy.policy_digest,
        verifier_id=active_policy.verifier_id,
        passed=not reasons,
        refusal_reasons=tuple(sorted(reasons)),
    )


def build_visual_region_feature_embedding(
    mask: RegionMask,
    output: bytes,
    intent: VisualPromptIntent,
    *,
    model_id: str = "beast.visual-region-feature-embedding.v1",
) -> VisualRegionFeatureEmbedding:
    intent_receipt = evaluate_visual_region_intent(mask, output, intent)
    perceptual = evaluate_visual_region_perceptual(mask, output, intent)
    avg_r, avg_g, avg_b = intent_receipt.average_rgb
    vector = (
        _bucket(avg_r, 16),
        _bucket(avg_g, 16),
        _bucket(avg_b, 16),
        _bucket(perceptual.luma_stddev, 4),
        _bucket(perceptual.edge_density * 100, 5),
        _bucket(perceptual.center_luma_lift, 8),
        _bucket(perceptual.centroid_offset_ratio * 100, 8),
        _bucket(perceptual.symmetry_delta, 8),
    )
    return VisualRegionFeatureEmbedding(
        source_output_digest="sha256:" + hashlib.sha256(output).hexdigest(),
        intent_digest=intent.intent_digest,
        color_name=intent.color_name,
        object_hint=intent.object_hint,
        model_id=model_id,
        vector=vector,
    )


def evaluate_visual_region_equivalence(
    left: VisualRegionFeatureEmbedding,
    right: VisualRegionFeatureEmbedding,
    *,
    max_distance: int = 10,
) -> VisualRegionEquivalenceReceipt:
    reasons: list[str] = []
    if left.intent_digest != right.intent_digest:
        reasons.append("intent_digest_mismatch")
    if left.model_id != right.model_id:
        reasons.append("embedding_model_mismatch")
    if len(left.vector) != len(right.vector):
        reasons.append("embedding_dimension_mismatch")
    distance = sum(abs(a - b) for a, b in zip(left.vector, right.vector))
    if distance > max_distance:
        reasons.append("visual_embedding_distance_exceeded")
    return VisualRegionEquivalenceReceipt(
        left_output_digest=left.source_output_digest,
        right_output_digest=right.source_output_digest,
        left_embedding_digest=left.embedding_digest,
        right_embedding_digest=right.embedding_digest,
        intent_digest=left.intent_digest,
        model_id=left.model_id,
        distance=int(distance),
        max_distance=int(max_distance),
        equivalent=not reasons,
        refusal_reasons=tuple(sorted(reasons)),
    )


def _intent_target_rgb(color_name: str) -> tuple[int, int, int] | None:
    return {
        "red": (225, 42, 38),
        "green": (38, 220, 72),
        "blue": (52, 110, 235),
        "yellow": (235, 220, 48),
        "white": (230, 230, 230),
        "black": (18, 18, 18),
    }.get(color_name)


def _average_matches_color(avg: tuple[int, int, int], color_name: str) -> bool:
    r, g, b = avg
    if color_name == "green":
        return g >= max(48, int(r * 1.25), int(b * 1.25))
    if color_name == "red":
        return r >= max(48, int(g * 1.25), int(b * 1.25))
    if color_name == "blue":
        return b >= max(48, int(r * 1.20), int(g * 1.20))
    if color_name == "yellow":
        return r >= 96 and g >= 96 and b <= min(r, g) * 0.75
    if color_name == "white":
        return min(r, g, b) >= 180 and max(r, g, b) - min(r, g, b) <= 48
    if color_name == "black":
        return max(r, g, b) <= 64
    return True


def _bucket(value: float | int, step: int) -> int:
    if step <= 0:
        raise ValueError("bucket step must be positive")
    return int(round(float(value) / step))
