from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from time import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from openclaw_skins.config import default_device_identity_path


def base64url_encode(raw: bytes) -> str:
    encoded = base64.b64encode(raw).decode("ascii")
    return encoded.replace("+", "-").replace("/", "_").rstrip("=")


def base64url_decode(value: str) -> bytes:
    normalized = value.replace("-", "+").replace("_", "/")
    padding = "=" * ((4 - (len(normalized) % 4)) % 4)
    return base64.b64decode(f"{normalized}{padding}")


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
    device_id: str
    public_key_pem: str
    private_key_pem: str


def public_key_raw_base64url_from_pem(public_key_pem: str) -> str:
    public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    raw_public_key = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64url_encode(raw_public_key)


def sign_device_payload(private_key_pem: str, payload: str) -> str:
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"),
        password=None,
    )
    signature = private_key.sign(payload.encode("utf-8"))
    return base64url_encode(signature)


def _derive_device_id(public_key_pem: str) -> str:
    public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    raw_public_key = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw_public_key).hexdigest()


def _generate_identity() -> DeviceIdentity:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return DeviceIdentity(
        device_id=_derive_device_id(public_key_pem),
        public_key_pem=public_key_pem,
        private_key_pem=private_key_pem,
    )


def _read_identity(file_path: Path) -> DeviceIdentity | None:
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    public_key_pem = raw.get("publicKeyPem")
    private_key_pem = raw.get("privateKeyPem")
    if not isinstance(public_key_pem, str) or not isinstance(private_key_pem, str):
        return None
    device_id = raw.get("deviceId")
    derived_device_id = _derive_device_id(public_key_pem)
    return DeviceIdentity(
        device_id=device_id.strip() if isinstance(device_id, str) and device_id.strip() else derived_device_id,
        public_key_pem=public_key_pem,
        private_key_pem=private_key_pem,
    )


def _write_identity(file_path: Path, identity: DeviceIdentity) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "deviceId": identity.device_id,
        "publicKeyPem": identity.public_key_pem,
        "privateKeyPem": identity.private_key_pem,
        "createdAtMs": int(time() * 1000),
    }
    file_path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")


def load_or_create_device_identity(file_path: Path | None = None) -> DeviceIdentity:
    identity_path = file_path or default_device_identity_path()
    identity = _read_identity(identity_path)
    if identity is not None:
        if identity.device_id != _derive_device_id(identity.public_key_pem):
            identity = DeviceIdentity(
                device_id=_derive_device_id(identity.public_key_pem),
                public_key_pem=identity.public_key_pem,
                private_key_pem=identity.private_key_pem,
            )
            _write_identity(identity_path, identity)
        return identity
    identity = _generate_identity()
    _write_identity(identity_path, identity)
    return identity
