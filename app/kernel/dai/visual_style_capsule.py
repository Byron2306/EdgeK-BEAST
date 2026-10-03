"""Deterministic visual style capsules for Phase-7 BEAST drawing.

A style capsule is not a neural fine-tune and not an image-understanding claim.
It is a bounded visual grammar extracted from a reference image:

* reference file digest;
* small palette;
* semantic SVG style mapping;
* explicit nonclaims.

The capsule can restyle a verified semantic SVG without changing the graph,
fact ids, edge ids or semantic digest.  In other words: reference image teaches
BEAST *how the diagram should look*, not what the diagram means.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from xml.etree import ElementTree as ET

from app.kernel.compute.deterministic_intelligence import canonical_json, require_digest, sha256_bytes, sha256_digest


VISUAL_STYLE_CAPSULE_VERSION = "2026-08-05.phase7.visual-style-capsule.v1"


@dataclass(frozen=True, slots=True)
class VisualStyleCapsule:
    beast_object_type: str
    version: str
    capsule_id: str
    reference_image_digest: str
    extraction_method: str
    palette: tuple[str, ...]
    style_map: Mapping[str, Any]
    nonclaims: tuple[str, ...] = (
        "not_neural_image_training",
        "not_object_recognition",
        "not_pixel_reconstruction",
        "does_not_change_semantic_graph",
    )
    provider_calls_used: int = 0
    production_authority_allowed: bool = False
    execution_authority_allowed: bool = False

    def __post_init__(self) -> None:
        if self.beast_object_type != "dai_visual_style_capsule":
            raise ValueError("unexpected visual style capsule type")
        if self.version != VISUAL_STYLE_CAPSULE_VERSION:
            raise ValueError("unexpected visual style capsule version")
        if not self.capsule_id.strip():
            raise ValueError("style capsule requires capsule_id")
        require_digest(self.reference_image_digest, field_name="reference_image_digest")
        if not self.palette:
            raise ValueError("style capsule requires a palette")
        for color in self.palette:
            _require_hex_color(color)
        canonical_json(self.style_map)
        if self.provider_calls_used != 0 or self.production_authority_allowed or self.execution_authority_allowed:
            raise ValueError("visual style capsule cannot grant provider, production or execution authority")

    @property
    def capsule_digest(self) -> str:
        return sha256_digest(self)


def teach_visual_style_from_reference(path: str | Path, *, capsule_id: str = "phase7:visual-style:reference") -> VisualStyleCapsule:
    source = Path(path).expanduser().resolve()
    image_digest = sha256_bytes(source.read_bytes())
    palette = _extract_palette(source)
    background = _darkest(palette)
    brightest = _brightest(palette)
    mid = palette[len(palette) // 2]
    accent = palette[1] if len(palette) > 1 else brightest
    style_map = {
        "background": background,
        "node_fill": _mix_hex(background, mid, 0.42),
        "node_stroke": accent,
        "edge_stroke": accent,
        "text_primary": brightest,
        "text_secondary": _mix_hex(brightest, accent, 0.45),
        "text_value": _mix_hex(brightest, "#72e3a6", 0.50),
        "footer": _mix_hex(brightest, background, 0.45),
        "node_radius": 14,
        "edge_width": 3,
        "layout_style": "reference_palette_semantic_cards",
        "font_family": "Inter, ui-sans-serif, system-ui, sans-serif",
    }
    return VisualStyleCapsule(
        beast_object_type="dai_visual_style_capsule",
        version=VISUAL_STYLE_CAPSULE_VERSION,
        capsule_id=capsule_id,
        reference_image_digest=image_digest,
        extraction_method="pillow_quantized_palette_v1",
        palette=palette,
        style_map=style_map,
    )


def apply_visual_style_to_svg(svg: str, capsule: VisualStyleCapsule | Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    if not isinstance(capsule, VisualStyleCapsule):
        capsule = VisualStyleCapsule(**dict(capsule))
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    root = ET.fromstring(svg)
    semantic_digest = root.attrib.get("data-semantic-digest", "")
    require_digest(semantic_digest, field_name="svg.data-semantic-digest")
    original_semantic_digest = semantic_digest
    original_fact_ids = tuple(element.attrib["data-fact-id"] for element in root.findall(".//*[@data-fact-id]"))
    original_edge_ids = tuple(element.attrib["data-edge-id"] for element in root.findall(".//*[@data-edge-id]"))

    style = dict(capsule.style_map)
    root.set("data-style-capsule-digest", capsule.capsule_digest)
    _set_style_attr(root, "font-family", str(style.get("font_family", "")))
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "rect" and element.attrib.get("width") == "100%":
            element.set("fill", str(style["background"]))
        elif tag == "rect":
            element.set("fill", str(style["node_fill"]))
            element.set("stroke", str(style["node_stroke"]))
            element.set("rx", str(style.get("node_radius", 14)))
        elif tag == "line":
            element.set("stroke", str(style["edge_stroke"]))
            element.set("stroke-width", str(style.get("edge_width", 3)))
        elif tag == "path" and element.attrib.get("d", "").startswith("M0,0"):
            element.set("fill", str(style["edge_stroke"]))
        elif tag == "text":
            text = element.text or ""
            if text.startswith("value:"):
                element.set("fill", str(style["text_value"]))
            elif text.startswith("semantic:"):
                element.set("fill", str(style["footer"]))
            elif element.attrib.get("font-size") in {"12", "10"}:
                element.set("fill", str(style["text_secondary"]))
            else:
                element.set("fill", str(style["text_primary"]))
    styled_svg = ET.tostring(root, encoding="unicode")
    receipt = verify_styled_svg(svg, styled_svg, capsule)
    return styled_svg, receipt


def verify_styled_svg(original_svg: str, styled_svg: str, capsule: VisualStyleCapsule | Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(capsule, VisualStyleCapsule):
        capsule = VisualStyleCapsule(**dict(capsule))
    original = ET.fromstring(original_svg)
    styled = ET.fromstring(styled_svg)
    original_semantic = original.attrib.get("data-semantic-digest", "")
    styled_semantic = styled.attrib.get("data-semantic-digest", "")
    original_fact_ids = tuple(element.attrib["data-fact-id"] for element in original.findall(".//*[@data-fact-id]"))
    styled_fact_ids = tuple(element.attrib["data-fact-id"] for element in styled.findall(".//*[@data-fact-id]"))
    original_edge_ids = tuple(element.attrib["data-edge-id"] for element in original.findall(".//*[@data-edge-id]"))
    styled_edge_ids = tuple(element.attrib["data-edge-id"] for element in styled.findall(".//*[@data-edge-id]"))
    original_text = tuple((element.text or "") for element in original.iter() if element.tag.rsplit("}", 1)[-1] == "text")
    styled_text = tuple((element.text or "") for element in styled.iter() if element.tag.rsplit("}", 1)[-1] == "text")
    gates = {
        "semantic_digest_preserved": original_semantic == styled_semantic and bool(original_semantic),
        "style_capsule_bound": styled.attrib.get("data-style-capsule-digest") == capsule.capsule_digest,
        "fact_ids_preserved": original_fact_ids == styled_fact_ids,
        "edge_ids_preserved": original_edge_ids == styled_edge_ids,
        "text_labels_preserved": original_text == styled_text,
        "reference_image_digest_bound": bool(capsule.reference_image_digest),
        "provider_calls_zero": capsule.provider_calls_used == 0,
        "authority_false": not capsule.production_authority_allowed and not capsule.execution_authority_allowed,
    }
    receipt: dict[str, Any] = {
        "beast_object_type": "dai_visual_style_application_receipt",
        "version": VISUAL_STYLE_CAPSULE_VERSION,
        "style_capsule_digest": capsule.capsule_digest,
        "reference_image_digest": capsule.reference_image_digest,
        "original_svg_digest": sha256_digest(original_svg),
        "styled_svg_digest": sha256_digest(styled_svg),
        "semantic_digest": styled_semantic,
        "gates": gates,
        "verified": all(gates.values()),
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "claim_boundary": (
            "Reference image teaches palette/style grammar only. The semantic graph, fact ids, edge ids "
            "and labels are preserved and remain independently generated from meaning."
        ),
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def write_visual_style_capsule(path: str | Path, capsule: VisualStyleCapsule) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {**_as_payload(capsule), "capsule_digest": capsule.capsule_digest}
    target.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def _extract_palette(path: Path, *, color_count: int = 7) -> tuple[str, ...]:
    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - dependency exists in project requirements
        raise RuntimeError("Pillow is required to teach a visual style from a reference image") from exc
    image = Image.open(path).convert("RGB")
    image.thumbnail((160, 160))
    direct_counts = image.getcolors(maxcolors=160 * 160) or []
    quantized = image.quantize(colors=color_count)
    palette = quantized.getpalette() or []
    counts = quantized.getcolors(maxcolors=160 * 160) or []
    direct_rows: list[tuple[float, int, tuple[int, int, int]]] = []
    for count, rgb in direct_counts:
        saturation = (max(rgb) - min(rgb)) / 255.0
        brightness = sum(rgb) / (3 * 255.0)
        direct_rows.append((saturation * 3.0 + brightness + min(count, 64) / 64.0, count, rgb))
    weighted_rows: list[tuple[float, int, int]] = []
    for count, index in counts:
        offset = index * 3
        rgb = tuple(palette[offset:offset + 3])
        if len(rgb) != 3:
            continue
        saturation = (max(rgb) - min(rgb)) / 255.0
        brightness = sum(rgb) / (3 * 255.0)
        weighted_rows.append((float(count) * (1.0 + saturation + 0.35 * brightness), count, index))
    colors: list[str] = []
    for _weight, _count, rgb in sorted(direct_rows, reverse=True):
        if _weight < 1.0:
            continue
        color = "#%02x%02x%02x" % rgb
        if color not in colors:
            colors.append(color)
        if len(colors) >= max(2, color_count // 2):
            break
    for _weight, _count, index in sorted(weighted_rows, reverse=True):
        offset = index * 3
        rgb = tuple(palette[offset:offset + 3])
        if len(rgb) == 3:
            color = "#%02x%02x%02x" % rgb
            if color not in colors:
                colors.append(color)
    for _count, index in sorted(counts, reverse=True):
        offset = index * 3
        rgb = tuple(palette[offset:offset + 3])
        if len(rgb) == 3:
            color = "#%02x%02x%02x" % rgb
            if color not in colors:
                colors.append(color)
    return tuple(colors[:color_count] or ("#08111f", "#58b6ff", "#e6f1ff"))


def _require_hex_color(color: str) -> None:
    if not isinstance(color, str) or not re_full_hex(color):
        raise ValueError(f"invalid hex color: {color!r}")


def re_full_hex(color: str) -> bool:
    return len(color) == 7 and color.startswith("#") and all(ch in "0123456789abcdefABCDEF" for ch in color[1:])


def _darkest(colors: tuple[str, ...]) -> str:
    return min(colors, key=_luminance)


def _brightest(colors: tuple[str, ...]) -> str:
    return max(colors, key=_luminance)


def _luminance(color: str) -> float:
    r, g, b = _hex_to_rgb(color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _mix_hex(left: str, right: str, right_weight: float) -> str:
    lr, lg, lb = _hex_to_rgb(left)
    rr, rg, rb = _hex_to_rgb(right)
    lw = 1.0 - right_weight
    return "#%02x%02x%02x" % (
        int(lr * lw + rr * right_weight),
        int(lg * lw + rg * right_weight),
        int(lb * lw + rb * right_weight),
    )


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    _require_hex_color(color)
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _set_style_attr(root: ET.Element, name: str, value: str) -> None:
    if value:
        root.set(name, value)


def _as_payload(capsule: VisualStyleCapsule) -> dict[str, Any]:
    return {
        "beast_object_type": capsule.beast_object_type,
        "version": capsule.version,
        "capsule_id": capsule.capsule_id,
        "reference_image_digest": capsule.reference_image_digest,
        "extraction_method": capsule.extraction_method,
        "palette": capsule.palette,
        "style_map": dict(capsule.style_map),
        "nonclaims": capsule.nonclaims,
        "provider_calls_used": capsule.provider_calls_used,
        "production_authority_allowed": capsule.production_authority_allowed,
        "execution_authority_allowed": capsule.execution_authority_allowed,
    }
