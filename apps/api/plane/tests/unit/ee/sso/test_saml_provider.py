# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from plane.authentication.adapter.error import AuthenticationException
from plane.db.models import Account, User
from plane.ee.sso.config import config_key, get_sso_config, list_enabled_providers, seed_config
from plane.ee.sso.identity import subject_key
from plane.ee.sso.saml import (
    NAMEID_PERSISTENT,
    SamlProvider,
    acs_url,
    metadata_url,
    new_relay_token,
    normalize_cert,
    pop_relay,
    save_relay,
)
from plane.license.models import InstanceConfiguration
from plane.tests.unit.ee.sso.saml_helpers import build_saml_response, make_cert_and_key

IDP = "https://idp.example.com/meta"


def configure_saml(**fields):
    seed_config()
    base = {
        "ENABLED": "1",
        "IDP_ENTITY_ID": IDP,
        "IDP_SSO_URL": "https://idp.example.com/sso",
        "IDP_X509CERT": "MIIB",
    }
    base.update(fields)
    for field, value in base.items():
        row = InstanceConfiguration.objects.get(key=config_key("saml", field))
        row.value = value
        row.save()


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.delete_pattern("ee_sso_*")


@pytest.fixture(scope="module")
def keys():
    return make_cert_and_key()


@pytest.fixture
def saml(db, keys):
    configure_saml(IDP_X509CERT=keys[1])


def _acs_request(saml_response=""):
    request = RequestFactory().post("/auth/sso/saml/acs/", {"SAMLResponse": saml_response})
    request.META["HTTP_USER_AGENT"] = "pytest"
    return request


def _login_request():
    request = RequestFactory().get("/auth/sso/saml/")
    request.META["HTTP_USER_AGENT"] = "pytest"
    return request


def _response(keys, request, **kw):
    args = dict(
        acs_url=acs_url(request),
        idp_entity_id=IDP,
        sp_entity_id=metadata_url(request),
        in_response_to="_req1",
        name_id="persistent-id-1",
        key_pem=keys[0],
        cert_pem=keys[1],
    )
    args.update(kw)
    return build_saml_response(**args)


def _authenticate(keys, **kw):
    request = _acs_request()
    request.POST = request.POST.copy()
    request.POST["SAMLResponse"] = _response(keys, request, **kw)
    return SamlProvider(request).authenticate("_req1")


@pytest.mark.unit
@pytest.mark.django_db
def test_saml_requires_idp_fields_and_lists_with_protocol():
    seed_config()
    assert get_sso_config("saml") is None
    configure_saml()
    assert get_sso_config("saml")["IDP_SSO_URL"] == "https://idp.example.com/sso"
    assert {"id": "saml", "label": "SAML", "protocol": "saml"} in list_enabled_providers()


@pytest.mark.unit
@pytest.mark.django_db
def test_saml_missing_cert_is_not_configured():
    configure_saml(IDP_X509CERT="")
    assert get_sso_config("saml") is None


@pytest.mark.unit
def test_normalize_cert_strips_pem_armor_and_whitespace():
    pem = "-----BEGIN CERTIFICATE-----\nAAAA\nBBBB\n-----END CERTIFICATE-----\n"
    assert normalize_cert(pem) == "AAAABBBB"


@pytest.mark.unit
def test_relay_store_is_one_time():
    token = new_relay_token()
    save_relay(token, {"request_id": "_x"})
    assert pop_relay(token) == {"request_id": "_x"}
    assert pop_relay(token) is None
    assert pop_relay("") is None


@pytest.mark.unit
def test_login_url_requests_a_persistent_nameid_and_metadata_says_so(saml):
    provider = SamlProvider(_login_request())
    url = provider.login_url("tok")
    assert url.startswith("https://idp.example.com/sso?SAMLRequest=")
    assert "RelayState=tok" in url
    assert provider.request_id().startswith("ONELOGIN_")  # login_url() above generated the AuthnRequest
    assert NAMEID_PERSISTENT in provider.metadata_xml()


@pytest.mark.unit
def test_valid_signed_response_logs_in_by_persistent_nameid(saml, keys):
    user = _authenticate(keys)
    account = Account.objects.get(user=user)
    assert account.provider == "sso-saml"
    assert account.provider_account_id == subject_key(IDP, "persistent-id-1")
    assert (user.first_name, user.last_name) == ("An", "Nguyen")
    assert user.email.endswith("@sso.invalid")


@pytest.mark.unit
def test_same_nameid_is_the_same_user_on_the_next_login(saml, keys):
    first = _authenticate(keys)
    assert _authenticate(keys).id == first.id


@pytest.mark.unit
def test_email_like_nameid_never_links_an_existing_plane_user(saml, keys):
    victim = User.objects.create(email="a@b.com", username="victim")
    user = _authenticate(keys, name_id="a@b.com")  # persistent format, value looks like an e-mail
    assert user.id != victim.id
    assert not Account.objects.filter(user=victim).exists()


@pytest.mark.unit
@pytest.mark.parametrize(
    "name_id_format",
    [
        "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified",
        "urn:oasis:names:tc:SAML:2.0:nameid-format:transient",
    ],
)
def test_non_persistent_nameid_is_rejected(saml, keys, name_id_format):
    with pytest.raises(AuthenticationException) as exc:
        _authenticate(keys, name_id_format=name_id_format)
    assert exc.value.error_code == 6001


@pytest.mark.unit
@pytest.mark.parametrize(
    "override",
    [
        {"sign": False},  # unsigned
        {"in_response_to": "_other"},  # InResponseTo mismatch
        {"in_response_to": None},  # unsolicited: no InResponseTo at all
        {"sp_entity_id": "https://evil.example.com/"},  # wrong audience
        {"valid_for": -600},  # expired
    ],
)
def test_invalid_responses_rejected(saml, keys, override):
    with pytest.raises(AuthenticationException) as exc:
        _authenticate(keys, **override)
    assert exc.value.error_code == 6001


@pytest.mark.unit
def test_response_signed_by_other_key_rejected(saml, keys):
    other_key, other_cert = make_cert_and_key()
    with pytest.raises(AuthenticationException):
        _authenticate(keys, key_pem=other_key, cert_pem=other_cert)


@pytest.mark.unit
@pytest.mark.parametrize("post", [{}, {"SAMLResponse": "!!!not-base64!!!"}, {"SAMLResponse": "Z2FyYmFnZQ=="}])
def test_unparsable_response_is_provider_error_not_500(saml, post):
    request = RequestFactory().post("/auth/sso/saml/acs/", post)
    request.META["HTTP_USER_AGENT"] = "pytest"
    with pytest.raises(AuthenticationException) as exc:
        SamlProvider(request).authenticate("_req1")
    assert exc.value.error_code == 6001


@pytest.mark.unit
def test_custom_acs_url_is_used_for_destination_check(saml, keys):
    configure_saml(IDP_X509CERT=keys[1], CALLBACK_URL="https://sso.corp.com/auth/sso/saml/acs/")
    assert acs_url(_acs_request()) == "https://sso.corp.com/auth/sso/saml/acs/"
    assert _authenticate(keys).id


@pytest.mark.unit
def test_allow_signup_off_blocks_new_saml_users_but_not_linked_ones(saml, keys):
    user = _authenticate(keys)
    configure_saml(IDP_X509CERT=keys[1], ALLOW_SIGNUP="0")
    assert _authenticate(keys, assertion_id="_again").id == user.id  # already linked
    with pytest.raises(AuthenticationException) as exc:
        _authenticate(keys, name_id="someone-else")
    assert exc.value.error_code == 5015


@pytest.mark.unit
def test_assertion_replay_rejected(saml, keys):
    _authenticate(keys, assertion_id="_same")
    with pytest.raises(AuthenticationException) as exc:
        _authenticate(keys, assertion_id="_same")
    assert exc.value.error_code == 6001
