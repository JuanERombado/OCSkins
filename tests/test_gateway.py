from __future__ import annotations

from openclaw_skins.gateway import build_connect_params


def test_build_connect_params_uses_supported_backend_identity() -> None:
    params = build_connect_params("secret-token")

    assert params["client"]["id"] == "gateway-client"
    assert params["client"]["mode"] == "backend"
    assert params["role"] == "operator"
    assert params["auth"] == {"token": "secret-token"}
