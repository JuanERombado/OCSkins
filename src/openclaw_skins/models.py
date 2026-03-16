from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from openclaw_skins.config import DEFAULT_CLI_COMMAND, DEFAULT_GATEWAY_URL, DEFAULT_SKIN_ID, DEFAULT_TICK_INTERVAL_MS


@dataclass(frozen=True, slots=True)
class Point:
    x: int
    y: int

    @classmethod
    def from_dict(cls, raw: object) -> "Point | None":
        if not isinstance(raw, dict):
            return None
        try:
            return cls(x=int(raw.get("x", 0)), y=int(raw.get("y", 0)))
        except (TypeError, ValueError):
            return None

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y}


@dataclass(frozen=True, slots=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @classmethod
    def from_dict(cls, raw: object) -> "Rect":
        if not isinstance(raw, dict):
            raise ValueError("rectangle must be an object")
        try:
            return cls(
                x=int(raw["x"]),
                y=int(raw["y"]),
                width=int(raw["width"]),
                height=int(raw["height"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("rectangle must include integer x, y, width, and height") from exc

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x <= self.x + self.width and self.y <= y <= self.y + self.height

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(frozen=True, slots=True)
class SkinManifest:
    skin_id: str
    display_name: str
    frame_paths: tuple[Path, Path]
    window_size: tuple[int, int]
    canvas_bounds: Rect
    drag_regions: tuple[Rect, ...]
    idle_frame: int
    animation_interval_ms: int
    overlay_anchor: Point
    manifest_path: Path


@dataclass(slots=True)
class AppSettings:
    gateway_url: str = DEFAULT_GATEWAY_URL
    gateway_token: str = ""
    cli_command: str = DEFAULT_CLI_COMMAND
    selected_skin: str = DEFAULT_SKIN_ID
    window_position: Point | None = None
    always_on_top: bool = False

    @classmethod
    def from_dict(cls, raw: object) -> "AppSettings":
        if not isinstance(raw, dict):
            return cls()
        settings = cls()
        gateway_url = raw.get("gateway_url")
        gateway_token = raw.get("gateway_token")
        cli_command = raw.get("cli_command")
        selected_skin = raw.get("selected_skin")
        always_on_top = raw.get("always_on_top")
        if isinstance(gateway_url, str) and gateway_url.strip():
            settings.gateway_url = gateway_url.strip()
        if isinstance(gateway_token, str):
            settings.gateway_token = gateway_token.strip()
        if isinstance(cli_command, str) and cli_command.strip():
            settings.cli_command = cli_command.strip()
        if isinstance(selected_skin, str) and selected_skin.strip():
            settings.selected_skin = selected_skin.strip()
        if isinstance(always_on_top, bool):
            settings.always_on_top = always_on_top
        settings.window_position = Point.from_dict(raw.get("window_position"))
        return settings

    def to_dict(self) -> dict[str, object]:
        return {
            "gateway_url": self.gateway_url,
            "gateway_token": self.gateway_token,
            "cli_command": self.cli_command,
            "selected_skin": self.selected_skin,
            "window_position": self.window_position.to_dict() if self.window_position else None,
            "always_on_top": self.always_on_top,
        }


@dataclass(slots=True)
class GatewayConnectionState:
    transport_connected: bool = False
    handshake_complete: bool = False
    live: bool = False
    status_text: str = "Gateway offline"
    detail_text: str = "Not connected."
    last_error: str | None = None
    tick_interval_ms: int = DEFAULT_TICK_INTERVAL_MS


@dataclass(slots=True)
class GatewayServiceStatus:
    service_present: bool = False
    can_restart: bool = False
    summary: str = "Gateway service is unavailable."
    detail_message: str = "Run openclaw gateway status to inspect the local service."
    disabled_reason: str = "Gateway service is not installed."
    runtime_label: str = ""
    raw_output: str = ""


@dataclass(slots=True)
class BusyRunTracker:
    active_run_ids: set[str] = field(default_factory=set)

    @property
    def busy(self) -> bool:
        return bool(self.active_run_ids)

    def clear(self) -> None:
        self.active_run_ids.clear()

    def apply_agent_event(self, run_id: str, stream: str, data: object) -> bool:
        if not run_id:
            return self.busy
        if stream != "lifecycle":
            self.active_run_ids.add(run_id)
            return self.busy
        if not isinstance(data, dict):
            return self.busy
        phase = str(data.get("phase", "")).strip().lower()
        if phase == "start":
            self.active_run_ids.add(run_id)
        elif phase in {"end", "error"}:
            self.active_run_ids.discard(run_id)
        return self.busy
