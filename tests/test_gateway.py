from __future__ import annotations

from openclaw_skins.gateway import build_connect_params
from openclaw_skins.identity import load_or_create_device_identity


def test_build_connect_params_uses_supported_backend_identity(tmp_path) -> None:
    identity = load_or_create_device_identity(tmp_path / "device.json")
    params = build_connect_params(
        gateway_token="secret-token",
        device_identity=identity,
        nonce="nonce-1",
    )

    assert params["client"]["id"] == "gateway-client"
    assert params["client"]["mode"] == "backend"
    assert params["role"] == "operator"
    assert params["auth"] == {"token": "secret-token"}
    assert params["device"]["id"] == identity.device_id
    assert params["device"]["nonce"] == "nonce-1"


def test_build_connect_params_uses_bootstrap_token_when_shared_token_is_missing(tmp_path) -> None:
    identity = load_or_create_device_identity(tmp_path / "device.json")
    params = build_connect_params(
        bootstrap_token="bootstrap-token",
        device_identity=identity,
        nonce="nonce-2",
    )

    assert params["auth"] == {"bootstrapToken": "bootstrap-token"}
    assert params["device"]["id"] == identity.device_id
