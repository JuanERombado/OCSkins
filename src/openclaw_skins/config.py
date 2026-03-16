from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "OpenClaw Skins"
APP_SLUG = "openclaw-skins"
APP_VENDOR = "OpenClawSkins"
APP_VERSION = "0.1.0"
PROTOCOL_VERSION = 3
DEFAULT_GATEWAY_URL = os.environ.get("OPENCLAW_SKINS_GATEWAY_URL", "ws://127.0.0.1:18789")
DEFAULT_CLI_COMMAND = os.environ.get("OPENCLAW_SKINS_CLI_COMMAND", "openclaw")
DEFAULT_SKIN_ID = os.environ.get("OPENCLAW_SKINS_DEFAULT_SKIN", "crab")
DEFAULT_TICK_INTERVAL_MS = 30_000
RECONNECT_DELAY_MS = 2_000


def local_app_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_VENDOR
    return Path.home() / "AppData" / "Local" / APP_VENDOR


def identity_data_dir() -> Path:
    return local_app_data_dir() / "identity"


def default_settings_path() -> Path:
    return local_app_data_dir() / "settings.json"


def default_device_identity_path() -> Path:
    return identity_data_dir() / "device.json"


def default_device_auth_store_path() -> Path:
    return identity_data_dir() / "device-auth.json"
