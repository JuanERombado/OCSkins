from __future__ import annotations

import json
from pathlib import Path

from openclaw_skins.models import Point, Rect, SkinManifest
from openclaw_skins.resources import resource_path


def load_manifest_from_path(manifest_path: Path) -> SkinManifest:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("skin manifest must be an object")

    skin_id = str(raw.get("id", "")).strip()
    display_name = str(raw.get("display_name", "")).strip()
    frames = raw.get("frames")
    if not skin_id:
        raise ValueError("skin manifest requires a non-empty id")
    if not display_name:
        raise ValueError("skin manifest requires a non-empty display_name")
    if not isinstance(frames, list) or len(frames) != 2 or not all(isinstance(item, str) and item.strip() for item in frames):
        raise ValueError("skin manifest requires exactly two frame paths")

    window_size = raw.get("window_size")
    if not isinstance(window_size, dict):
        raise ValueError("skin manifest requires window_size")
    try:
        width = int(window_size["width"])
        height = int(window_size["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("window_size must include integer width and height") from exc

    canvas_bounds = Rect.from_dict(raw.get("canvas_bounds"))
    drag_regions_raw = raw.get("drag_regions")
    if not isinstance(drag_regions_raw, list) or not drag_regions_raw:
        raise ValueError("skin manifest requires at least one drag region")
    drag_regions = tuple(Rect.from_dict(item) for item in drag_regions_raw)

    overlay_anchor = Point.from_dict(raw.get("overlay_anchor"))
    if overlay_anchor is None:
        raise ValueError("skin manifest requires overlay_anchor")

    idle_frame = int(raw.get("idle_frame", 0))
    animation_interval_ms = int(raw.get("animation_interval_ms", 350))
    frame_paths = tuple((manifest_path.parent / item).resolve() for item in frames)
    return SkinManifest(
        skin_id=skin_id,
        display_name=display_name,
        frame_paths=(frame_paths[0], frame_paths[1]),
        window_size=(width, height),
        canvas_bounds=canvas_bounds,
        drag_regions=drag_regions,
        idle_frame=idle_frame,
        animation_interval_ms=animation_interval_ms,
        overlay_anchor=overlay_anchor,
        manifest_path=manifest_path.resolve(),
    )


class SkinCatalog:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or resource_path("assets", "skins")
        self._manifests: dict[str, SkinManifest] = {}

    def load(self) -> dict[str, SkinManifest]:
        manifests: dict[str, SkinManifest] = {}
        if self.root.exists():
            for manifest_path in sorted(self.root.glob("*/skin.json")):
                manifest = load_manifest_from_path(manifest_path)
                manifests[manifest.skin_id] = manifest
        self._manifests = manifests
        return manifests

    def all(self) -> dict[str, SkinManifest]:
        if not self._manifests:
            self.load()
        return dict(self._manifests)

    def get(self, skin_id: str) -> SkinManifest | None:
        return self.all().get(skin_id)
