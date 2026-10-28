import pytest

from plane.utils.instance_config_variables import instance_config_variables

KEYS = [
    "IS_ENTRA_ENABLED",
    "ENTRA_TENANT_ID",
    "ENTRA_CLIENT_ID",
    "ENTRA_CLIENT_SECRET",
    "ENTRA_PROVIDER_NAME",
    "ENTRA_ALLOWED_EMAIL_DOMAINS",
    "ENABLE_ENTRA_SYNC",
    "SSO_ONLY_LOGIN_PAGE",
]


def _by_key():
    return {v["key"]: v for v in instance_config_variables}


@pytest.mark.unit
def test_all_entra_keys_registered_in_entra_category():
    by_key = _by_key()
    for key in KEYS:
        assert key in by_key
        assert by_key[key]["category"] == "ENTRA"


@pytest.mark.unit
def test_only_client_secret_is_encrypted():
    by_key = _by_key()
    assert by_key["ENTRA_CLIENT_SECRET"]["is_encrypted"] is True
    for key in KEYS:
        if key != "ENTRA_CLIENT_SECRET":
            assert by_key[key]["is_encrypted"] is False


@pytest.mark.unit
def test_sync_and_sso_only_default_off(monkeypatch):
    monkeypatch.delenv("ENABLE_ENTRA_SYNC", raising=False)
    monkeypatch.delenv("SSO_ONLY_LOGIN_PAGE", raising=False)
    import importlib

    from plane.ee.entra_auth import config

    config = importlib.reload(config)
    values = {v["key"]: v["value"] for v in config.entra_config_variables}
    assert values["ENABLE_ENTRA_SYNC"] == "0"
    assert values["SSO_ONLY_LOGIN_PAGE"] == "0"
    assert config.ENTRA_CONFIG_KEYS == tuple(KEYS)
