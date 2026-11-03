from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES
from plane.ee.entra_auth.entra import EntraProvider
from plane.license.models import Instance

PROVIDER = "plane.ee.entra_auth.views.EntraProvider"
TENANT = "11111111-2222-3333-4444-555555555555"
CALLBACK = "entra-callback"


@pytest.fixture(autouse=True)
def hosts(settings):
    settings.APP_BASE_URL = "http://app.example.com"
    settings.SPACE_BASE_URL = "http://space.example.com"
    settings.WEB_URL = None


@pytest.fixture(autouse=True)
def entra_enabled(monkeypatch):
    monkeypatch.setenv("IS_ENTRA_ENABLED", "1")


@pytest.fixture
def instance(db):
    cache.clear()  # /api/instances/ is cached
    return Instance.objects.create(
        instance_name="t",
        instance_id="i1",
        current_version="1",
        last_checked_at=timezone.now(),
        is_setup_done=True,
    )


@pytest.fixture
def entra_env(monkeypatch):
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid")
    monkeypatch.setenv("ENTRA_CLIENT_SECRET", "sec")


def _client(state=None, surface=None, next_path=None):
    client = Client()
    session = client.session
    if state is not None:
        session["state"] = state
    if surface:
        session["entra_surface"] = surface
    if next_path:
        session["next_path"] = next_path
    session.save()
    return client


def _err_exc():
    from plane.authentication.adapter.error import AuthenticationException

    return AuthenticationException(error_code=AUTHENTICATION_ERROR_CODES["ENTRA_PROVIDER_ERROR"], error_message="x")


def _err(url):
    return parse_qs(urlparse(url).query).get("error_code")


@pytest.mark.contract
@pytest.mark.django_db
class TestEntraCallback:
    @pytest.mark.parametrize("state", [None, ""], ids=["no-state", "empty-state"])
    def test_missing_state(self, instance, state):
        params = {"code": "c"}
        if state is not None:
            params["state"] = state
        with patch(PROVIDER) as provider:
            response = _client().get(reverse(CALLBACK), params)
        assert response.status_code == 302
        assert _err(response.url)
        provider.assert_not_called()

    def test_wrong_state(self, instance):
        client = _client(state="expected")
        with patch(PROVIDER) as provider:
            response = client.get(reverse(CALLBACK), {"code": "c", "state": "other"})
        assert response.status_code == 302
        assert _err(response.url)
        provider.assert_not_called()
        assert "_auth_user_id" not in client.session

    def test_missing_code(self, instance):
        with patch(PROVIDER) as provider:
            response = _client(state="s").get(reverse(CALLBACK), {"state": "s"})
        assert _err(response.url) == [str(AUTHENTICATION_ERROR_CODES["ENTRA_PROVIDER_ERROR"])]
        provider.assert_not_called()

    def test_provider_not_configured(self, instance, monkeypatch):
        for k in ("ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET"):
            monkeypatch.delenv(k, raising=False)
        response = _client(state="s", surface="app").get(reverse(CALLBACK), {"code": "c", "state": "s"})
        assert _err(response.url) == [str(AUTHENTICATION_ERROR_CODES["ENTRA_NOT_CONFIGURED"])]

    def test_instance_not_configured(self, db):
        response = _client(state="s", surface="app").get(reverse(CALLBACK), {"code": "c", "state": "s"})
        assert _err(response.url) == [str(AUTHENTICATION_ERROR_CODES["INSTANCE_NOT_CONFIGURED"])]

    def test_success_app_safe_next_path(self, instance, create_user):
        client = _client(state="s", surface="app", next_path="/my/page")
        with patch(PROVIDER) as provider:
            provider.return_value.authenticate.return_value = create_user
            response = client.get(reverse(CALLBACK), {"code": "c", "state": "s"})
        assert response.url == "http://app.example.com/my/page"
        assert client.session["_auth_user_id"] == str(create_user.id)

    def test_open_redirect_next_path_neutralised(self, instance, create_user):
        client = _client(state="s", surface="app", next_path="https://evil.example.org/x")
        with patch(PROVIDER) as provider:
            provider.return_value.authenticate.return_value = create_user
            response = client.get(reverse(CALLBACK), {"code": "c", "state": "s"})
        assert urlparse(response.url).netloc == "app.example.com"

    def test_space_surface_redirects_to_space_host(self, instance, create_user):
        client = _client()
        with patch(PROVIDER) as provider:
            provider.return_value.get_auth_url.return_value = "https://idp.example/authorize"
            init = client.get(reverse("space-entra-initiate"), {"next_path": "/issues"})
        assert init.status_code == 302
        assert client.session["entra_surface"] == "space"
        state = client.session["state"]
        with patch(PROVIDER) as provider:
            provider.return_value.authenticate.return_value = create_user
            response = client.get(reverse(CALLBACK), {"code": "c", "state": state})
        assert response.url.startswith("http://space.example.com")
        assert response.url.endswith("/issues")
        assert "//issues" not in response.url.split("://", 1)[1]
        assert client.session["device_info"]["domain"].startswith("http://space.example.com")

    def test_replay_fails(self, instance, create_user):
        client = _client(state="s", surface="app")
        params = {"code": "c", "state": "s"}
        with patch(PROVIDER) as provider:
            provider.return_value.authenticate.return_value = create_user
            assert not _err(client.get(reverse(CALLBACK), params).url)
        with patch(PROVIDER) as provider:
            response = client.get(reverse(CALLBACK), params)
        assert _err(response.url)
        provider.assert_not_called()

    def test_second_callback_with_same_state_fails_and_surface_cleared(self, instance, create_user):
        client = _client(state="s", surface="app")
        with patch(PROVIDER) as provider:
            provider.return_value.authenticate.return_value = create_user
            client.get(reverse(CALLBACK), {"code": "c", "state": "s"})
        assert "entra_surface" not in client.session
        assert _err(client.get(reverse(CALLBACK), {"code": "c", "state": "s"}).url)

    def test_surface_cleared_on_failure_after_state(self, instance):
        client = _client(state="s", surface="app")
        with patch(PROVIDER) as provider:
            provider.return_value.authenticate.side_effect = _err_exc()
            client.get(reverse(CALLBACK), {"code": "c", "state": "s"})
        assert "entra_surface" not in client.session

    def test_new_user_blocked_when_signup_disabled(self, instance, entra_env, monkeypatch):
        monkeypatch.setenv("ENABLE_SIGNUP", "0")

        def fake_user_data(self):
            self.user_data = {"email": "new@corp.example", "user": {"first_name": "N", "provider_id": "x"}}

        client = _client(state="s", surface="app")
        with (
            patch.object(EntraProvider, "set_token_data", lambda self: None),
            patch.object(EntraProvider, "set_user_data", fake_user_data),
        ):
            response = client.get(reverse(CALLBACK), {"code": "c", "state": "s"})
        assert _err(response.url) == [str(AUTHENTICATION_ERROR_CODES["SIGNUP_DISABLED"])]
        assert "_auth_user_id" not in client.session


@pytest.mark.contract
@pytest.mark.django_db
class TestEntraInitiate:
    def test_app_initiate_stores_surface(self, instance):
        client = _client()
        with patch(PROVIDER) as provider:
            provider.return_value.get_auth_url.return_value = "https://idp.example/authorize"
            response = client.get(reverse("entra-initiate"), {"next_path": "/a"})
        assert response.url == "https://idp.example/authorize"
        assert client.session["entra_surface"] == "app"
        assert client.session["state"] == provider.call_args.kwargs["state"]

    def test_instance_not_configured(self, db):
        response = Client().get(reverse("entra-initiate"))
        assert _err(response.url) == [str(AUTHENTICATION_ERROR_CODES["INSTANCE_NOT_CONFIGURED"])]

    def test_provider_not_configured(self, instance, monkeypatch):
        monkeypatch.delenv("ENTRA_TENANT_ID", raising=False)
        response = Client().get(reverse("entra-initiate"))
        assert _err(response.url) == [str(AUTHENTICATION_ERROR_CODES["ENTRA_NOT_CONFIGURED"])]


@pytest.mark.contract
@pytest.mark.django_db
class TestEntraDisabled:
    NOT_CONF = [str(AUTHENTICATION_ERROR_CODES["ENTRA_NOT_CONFIGURED"])]

    @pytest.mark.parametrize("name", ["entra-initiate", "space-entra-initiate"])
    def test_initiate_disabled(self, instance, monkeypatch, name):
        monkeypatch.setenv("IS_ENTRA_ENABLED", "0")
        with patch(PROVIDER) as provider:
            response = Client().get(reverse(name))
        assert _err(response.url) == self.NOT_CONF
        provider.assert_not_called()

    def test_callback_disabled(self, instance, monkeypatch):
        monkeypatch.setenv("IS_ENTRA_ENABLED", "0")
        client = _client(state="s", surface="app")
        with patch(PROVIDER) as provider:
            response = client.get(reverse(CALLBACK), {"code": "c", "state": "s"})
        assert _err(response.url) == self.NOT_CONF
        provider.assert_not_called()
        assert "_auth_user_id" not in client.session


@pytest.mark.contract
@pytest.mark.django_db
def test_instance_config_returns_entra_fields(instance, monkeypatch):
    monkeypatch.setenv("IS_ENTRA_ENABLED", "1")
    monkeypatch.setenv("ENTRA_PROVIDER_NAME", "Corp SSO")
    monkeypatch.setenv("SSO_ONLY_LOGIN_PAGE", "1")
    config = Client().get("/api/instances/").json()["config"]
    assert config["is_entra_enabled"] is True
    assert config["entra_provider_name"] == "Corp SSO"
    assert config["sso_only_login_page"] is True


@pytest.mark.contract
@pytest.mark.django_db
def test_instance_config_entra_defaults(instance, monkeypatch):
    for k in ("IS_ENTRA_ENABLED", "ENTRA_PROVIDER_NAME", "SSO_ONLY_LOGIN_PAGE"):
        monkeypatch.delenv(k, raising=False)
    config = Client().get("/api/instances/").json()["config"]
    assert config["is_entra_enabled"] is False
    assert config["entra_provider_name"] == "Microsoft"
    assert config["sso_only_login_page"] is False


@pytest.mark.contract
def test_sign_out_lands_with_no_redirect(db):
    resp = Client().post("/auth/sign-out/")
    assert resp.status_code == 302
    assert "no_redirect=1" in resp["Location"]
