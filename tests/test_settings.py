from __future__ import annotations

from openclaw_skins.models import Point
from openclaw_skins.settings import AppSettingsStore


def test_settings_store_writes_defaults(tmp_path) -> None:
    store = AppSettingsStore(tmp_path / "settings.json")
    assert store.settings.gateway_url.startswith("ws://")
    assert store.settings.selected_skin == "crab"
    assert store.settings_path.exists()


def test_settings_store_persists_changes(tmp_path) -> None:
    settings_path = tmp_path / "settings.json"
    store = AppSettingsStore(settings_path)
    store.update(
        gateway_url="ws://10.0.0.4:18789",
        cli_command="wsl openclaw",
        window_position=Point(x=120, y=220),
        window_scale=0.78,
    )

    reloaded = AppSettingsStore(settings_path)
    assert reloaded.settings.gateway_url == "ws://10.0.0.4:18789"
    assert reloaded.settings.cli_command == "wsl openclaw"
    assert reloaded.settings.window_position == Point(x=120, y=220)
    assert reloaded.settings.window_scale == 0.78
