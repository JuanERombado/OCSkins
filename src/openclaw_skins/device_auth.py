from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from time import time

from openclaw_skins.config import default_device_auth_store_path


@dataclass(frozen=True, slots=True)
class DeviceAuthEntry:
    token: str
    role: str
    scopes: tuple[str, ...]
    updated_at_ms: int


def _normalize_role(role: str) -> str:
    trimmed = role.strip().lower()
    return trimmed or "operator"


def _normalize_scopes(scopes: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if not scopes:
        return ()
    unique: list[str] = []
    seen: set[str] = set()
    for scope in scopes:
        trimmed = str(scope).strip()
        if trimmed and trimmed not in seen:
            seen.add(trimmed)
            unique.append(trimmed)
    return tuple(unique)


def _read_store(file_path: Path) -> dict[str, object] | None:
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _write_store(file_path: Path, payload: dict[str, object]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")


def load_device_auth_token(
    device_id: str,
    role: str,
    file_path: Path | None = None,
) -> DeviceAuthEntry | None:
    store_path = file_path or default_device_auth_store_path()
    store = _read_store(store_path)
    if not store or store.get("deviceId") != device_id:
        return None
    tokens = store.get("tokens")
    if not isinstance(tokens, dict):
        return None
    entry = tokens.get(_normalize_role(role))
    if not isinstance(entry, dict):
        return None
    token = entry.get("token")
    if not isinstance(token, str) or not token.strip():
        return None
    scopes = entry.get("scopes")
    normalized_scopes = _normalize_scopes(scopes if isinstance(scopes, list) else None)
    updated_at_ms = entry.get("updatedAtMs")
    return DeviceAuthEntry(
        token=token.strip(),
        role=_normalize_role(role),
        scopes=normalized_scopes,
        updated_at_ms=int(updated_at_ms) if isinstance(updated_at_ms, (int, float)) else 0,
    )


def store_device_auth_token(
    device_id: str,
    role: str,
    token: str,
    scopes: list[str] | tuple[str, ...] | None = None,
    file_path: Path | None = None,
) -> DeviceAuthEntry:
    store_path = file_path or default_device_auth_store_path()
    normalized_role = _normalize_role(role)
    normalized_scopes = _normalize_scopes(scopes)
    payload = _read_store(store_path)
    if not payload or payload.get("deviceId") != device_id:
        payload = {"version": 1, "deviceId": device_id, "tokens": {}}
    tokens = payload.setdefault("tokens", {})
    if not isinstance(tokens, dict):
        tokens = {}
        payload["tokens"] = tokens
    entry = DeviceAuthEntry(
        token=token.strip(),
        role=normalized_role,
        scopes=normalized_scopes,
        updated_at_ms=int(time() * 1000),
    )
    tokens[normalized_role] = {
        "token": entry.token,
        "role": entry.role,
        "scopes": list(entry.scopes),
        "updatedAtMs": entry.updated_at_ms,
    }
    _write_store(store_path, payload)
    return entry


def clear_device_auth_token(device_id: str, role: str, file_path: Path | None = None) -> None:
    store_path = file_path or default_device_auth_store_path()
    payload = _read_store(store_path)
    if not payload or payload.get("deviceId") != device_id:
        return
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        return
    tokens.pop(_normalize_role(role), None)
    _write_store(store_path, payload)
