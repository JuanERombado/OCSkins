from __future__ import annotations

import json
from pathlib import Path

from openclaw_skins.config import default_settings_path
from openclaw_skins.models import AppSettings


class AppSettingsStore:
    def __init__(self, settings_path: Path | None = None) -> None:
        self.settings_path = settings_path or default_settings_path()
        self.settings = self.load()

    def load(self) -> AppSettings:
        if not self.settings_path.exists():
            settings = AppSettings()
            self._write(settings)
            return settings
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = {}
        settings = AppSettings.from_dict(raw)
        self.settings = settings
        return settings

    def save(self, settings: AppSettings) -> AppSettings:
        self.settings = settings
        self._write(settings)
        return self.settings

    def update(self, **changes: object) -> AppSettings:
        updated = AppSettings.from_dict(self.settings.to_dict())
        for key, value in changes.items():
            setattr(updated, key, value)
        return self.save(updated)

    def _write(self, settings: AppSettings) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(settings.to_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

