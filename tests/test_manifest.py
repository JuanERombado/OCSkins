from __future__ import annotations

import json

import pytest

from openclaw_skins.resources import resource_path
from openclaw_skins.skins import SkinCatalog, load_manifest_from_path


def test_bundled_crab_manifest_loads() -> None:
    manifest = load_manifest_from_path(resource_path("assets", "skins", "crab", "skin.json"))
    assert manifest.skin_id == "crab"
    assert manifest.display_name == "Crab Monitor"
    assert len(manifest.frame_paths) == 2
    assert manifest.frame_paths[0].name == "openclaw-skin-closed.png"
    assert manifest.frame_paths[1].name == "openclaw-skin-open.png"


def test_catalog_loads_bundled_skin() -> None:
    catalog = SkinCatalog()
    manifests = catalog.all()
    assert "crab" in manifests


def test_manifest_rejects_invalid_frame_list(tmp_path) -> None:
    manifest_path = tmp_path / "skin.json"
    manifest_path.write_text(
        json.dumps(
            {
                "id": "broken",
                "display_name": "Broken",
                "frames": ["only-one.png"],
                "window_size": {"width": 10, "height": 10},
                "canvas_bounds": {"x": 0, "y": 0, "width": 10, "height": 10},
                "drag_regions": [{"x": 0, "y": 0, "width": 10, "height": 10}],
                "overlay_anchor": {"x": 0, "y": 0},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exactly two frame paths"):
        load_manifest_from_path(manifest_path)
